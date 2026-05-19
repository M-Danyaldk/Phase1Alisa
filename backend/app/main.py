from pathlib import Path
import logging

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .curriculum import CURRICULUM
from .database import init_db
from .models import AssessmentRequest, AssessmentResult, ChatRequest, ChatResponse, HomeworkFeedbackResponse, StudentProfile
from .prompts import compact_chat_system_prompt, homework_prompt
from .routers.chat_history import router as chat_history_router
from .routes.auth import router as auth_router
from .routes.billing import router as billing_router
from .routes.child_profiles import router as child_profiles_router
from .routes.child_reports import router as child_reports_router
from .routes.student_dashboard import router as student_dashboard_router
from .routes.student_auth import router as student_auth_router
from .schemas.chat_history import ChatMessageCreateRequest, ChatThreadCreateRequest
from .services.access_control import require_child_access
from .services.assessment_service import evaluate_assessment
from .services.app_data_service import AppDataService
from .services.chat_store import ChatStore
from .services.llm.router import LLMRouter
from .services.tutor_answer_checker import TutorAnswerChecker
from .tutoring_logic import build_chat_directives, update_tutoring_state_after_reply
from .utils.multi_step_progress import build_progress_tracker_directives, update_multi_step_progress
from .utils.tutor_response import format_student_reply, looks_incomplete_response

settings = get_settings()
logger = logging.getLogger(__name__)
app = FastAPI(title='MsAlisia Phase 1 MVP API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list(), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(child_profiles_router)
app.include_router(child_reports_router)
app.include_router(student_dashboard_router)
app.include_router(student_auth_router)
app.include_router(chat_history_router)

@app.on_event('startup')
def startup() -> None:
    init_db()
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok', 'phase': 'Phase 1 MVP', 'primary_llm': settings.primary_llm_provider, 'fallback_llm': settings.fallback_llm_provider}


@app.get('/api/curriculum')
def curriculum() -> dict:
    return {'grades': [3, 4, 5, 6], 'subjects': CURRICULUM}


@app.post('/api/students')
async def save_student(student: StudentProfile) -> dict:
    student_id = await AppDataService().save_student(student)
    return {'ok': True, 'student_id': student_id}


@app.get('/api/students')
async def list_students() -> dict:
    return {'students': await AppDataService().list_students(limit=50)}


@app.post('/api/chat', response_model=ChatResponse)
async def chat(payload: ChatRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChatResponse:
    child_user = await require_child_access(authorization, payload.child_id, x_access_mode)
    chat_store: ChatStore | None = None
    chat_user_id: str | None = child_user['id']
    chat_thread_id: str | None = payload.thread_id
    history_saved = False
    history_error: str | None = None
    try:
        chat_store = ChatStore()
        if not chat_thread_id:
            thread = await chat_store.create_thread(chat_user_id, ChatThreadCreateRequest(
                child_id=payload.child_id,
                subject=payload.subject,
                topic=payload.topic,
                title=payload.message.strip()[:48] or None,
            ))
            chat_thread_id = thread['id']
        if chat_thread_id:
            await chat_store.store_message(chat_user_id, ChatMessageCreateRequest(
                thread_id=chat_thread_id,
                child_id=payload.child_id,
                role='student',
                content=payload.message,
                subject=payload.subject,
                topic=payload.topic,
                tutoring_state=payload.tutoring_state.model_dump(),
            ))
    except Exception as exc:
        logger.warning('Chat history setup failed before LLM response: %s', exc)
        chat_store = None
        chat_user_id = None
        chat_thread_id = payload.thread_id
        history_error = str(exc)

    router = LLMRouter()
    directives, active_task, current_step, tutoring_state = build_chat_directives(payload.message, payload.history, payload.tutoring_state)
    tutoring_state = tutoring_state.model_copy(update={'current_subject': payload.subject})
    tutoring_state = update_multi_step_progress(payload.message, tutoring_state)
    answer_check = None
    if tutoring_state.attempt_count > 0 and (tutoring_state.current_question or current_step):
        answer_check = await TutorAnswerChecker().check(
            subject=payload.subject,
            question=tutoring_state.current_question or current_step,
            student_answer=payload.message,
            expected_answer=tutoring_state.expected_answer,
        )
        tutoring_state = tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'student_answer': payload.message,
            'correctness_status': answer_check.status,
            'expected_answer': answer_check.expected_answer or tutoring_state.expected_answer,
            'hint_given': answer_check.is_wrong and tutoring_state.attempt_count == 1,
            'answer_revealed': answer_check.is_wrong and tutoring_state.attempt_count >= 2,
        })
        if answer_check.is_correct:
            directives.append('Backend answer check: correct. Praise briefly, then give one small next step or one new same-topic question.')
        elif tutoring_state.attempt_count == 1:
            directives.append('Backend answer check: wrong or unclear on first attempt. Give one helpful hint only. Do not reveal the final answer. Ask the student to try the same question again.')
        else:
            directives.append('Backend answer check: wrong or unclear on second attempt. Give the correct answer, explain it simply, then give one similar new practice question. Do not ask the same question again.')
            if answer_check.expected_answer:
                directives.append(f'Correct answer to explain: {answer_check.expected_answer}')
        if answer_check.feedback_note:
            directives.append(f'Answer-check note: {answer_check.feedback_note}')
    directives = [
        f'The currently selected subject is {payload.subject}. Stay in this subject unless the student clearly asks to switch to another subject.',
        'After the current problem is finished, you may end with one short same-subject practice question or mini-check when helpful. Do not add a new practice question before the current step is settled.',
        'Use compact tutor chat: 5-7 short lines maximum for normal help.',
        'For direct math questions, include the main step, calculation, and **Final answer:**.',
        'Use Markdown bold only for short labels such as **Step 1:** and **Final answer:**.',
        'Do not use * for multiplication. Use × for multiplication and ÷ for division.',
        'Do not end with an unfinished sentence or a heading without content.',
        *build_progress_tracker_directives(tutoring_state),
        *directives,
    ]
    system = compact_chat_system_prompt(payload.student, payload.subject, payload.topic, directives, active_task)
    history = '\n'.join([f'{item.role}: {item.content}' for item in payload.history[-4:]])
    state_summary = (
        f"Mode: {tutoring_state.mode}; "
        f"Attempt count: {tutoring_state.attempt_count}; "
        f"Correctness: {tutoring_state.correctness_status or 'not checked'}; "
        f"Memory: {tutoring_state.memory_note or 'none'}"
    )
    user = f"Recent chat:\n{history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or payload.message}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {payload.message}\n\nRespond as Ms Alisia using the required tutoring method."
    result = await router.generate(system=system, user=user, purpose='chat')
    formatted_reply = format_student_reply(result.text)
    if looks_incomplete_response(formatted_reply, payload.message):
        continuation_user = (
            f'{user}\n\n'
            f'Previous incomplete answer:\n{formatted_reply}\n\n'
            'Finish the answer briefly and include the final answer. Do not restart.'
        )
        continuation = await router.generate(system=system, user=continuation_user, purpose='chat')
        result.provider = continuation.provider
        result.model = continuation.model
        result.fallback_used = result.fallback_used or continuation.fallback_used
        formatted_reply = format_student_reply(f'{formatted_reply}\n\n{continuation.text}')
    next_state = update_tutoring_state_after_reply(tutoring_state, payload.message, formatted_reply)
    if chat_store and chat_user_id and chat_thread_id:
        try:
            await chat_store.store_message(chat_user_id, ChatMessageCreateRequest(
                thread_id=chat_thread_id,
                child_id=payload.child_id,
                role='msalisia',
                content=formatted_reply,
                subject=payload.subject,
                topic=payload.topic,
                provider=result.provider,
                model=result.model,
                tutoring_state=next_state.model_dump(),
            ))
            history_saved = True
        except Exception as exc:
            logger.warning('Chat history save failed after LLM response: %s', exc)
            history_error = str(exc)
    return ChatResponse(reply=formatted_reply, provider=result.provider, model=result.model, fallback_used=result.fallback_used, tutoring_state=next_state, thread_id=chat_thread_id, history_saved=history_saved, history_error=history_error)


@app.post('/api/assessments/evaluate', response_model=AssessmentResult)
async def assessments(payload: AssessmentRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> AssessmentResult:
    await require_child_access(authorization, payload.child_id, x_access_mode)
    return await evaluate_assessment(payload)


@app.post('/api/homework/lightweight-feedback', response_model=HomeworkFeedbackResponse)
async def homework_feedback(
    student_json: str = Form(...),
    child_id: str = Form(...),
    subject: str = Form(...),
    note: str = Form(''),
    file: UploadFile = File(...),
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> HomeworkFeedbackResponse:
    await require_child_access(authorization, child_id, x_access_mode)
    try:
        student = StudentProfile.model_validate_json(student_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail='Invalid student payload') from exc

    upload_info = await AppDataService().upload_homework_file(file)
    safe_name = upload_info['file_name']
    if 'content' in upload_info:
        upload_dir = Path(settings.uploads_path) / 'homework'
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved_path = upload_dir / upload_info['stored_name']
        saved_path.write_bytes(upload_info['content'])

    router = LLMRouter()
    system = homework_prompt(student, subject, note, safe_name)
    user = (
        f'The file "{safe_name}" was uploaded successfully for {student.name}. '
        'Give honest Phase 1 homework or handwriting support based on the note only. '
        'Do not pretend to inspect the file contents. '
        'Mention that deeper file analysis will be added in the next phase.'
    )
    result = await router.generate(system=system, user=user, purpose='homework')
    return HomeworkFeedbackResponse(feedback=result.text, provider=result.provider, model=result.model)


@app.get('/api/admin/overview')
async def admin_overview(x_admin_token: str = Header(default='')) -> dict:
    if not settings.admin_token_valid(x_admin_token):
        raise HTTPException(status_code=403, detail='You do not have permission to view this page.')
    app_data = AppDataService()
    return {
        'students': await app_data.list_students(limit=10),
        'assessments': await app_data.list_assessments(limit=10),
        'llm_events': await app_data.list_llm_events(limit=20),
    }


@app.get('/api/future-modules')
def future_modules() -> dict:
    modules = ['Voice Learning', 'Mobile App', 'Teacher Portal', 'School/LMS Integrations', 'Advanced Analytics', 'Full K-12 Expansion', 'Advanced Handwriting AI', 'Science', 'Social Studies', 'Test Prep']
    return {'modules': [{'name': name, 'status': 'Coming Soon'} for name in modules]}
