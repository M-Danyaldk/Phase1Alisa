from pathlib import Path
import logging

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .curriculum import curriculum_payload
from .database import init_db
from .models import AssessmentRequest, AssessmentResult, ChatRequest, ChatResponse, ChildAssessmentResult, HomeworkFeedbackResponse, StudentProfile
from .prompts import compact_chat_system_prompt
from .routers.chat_history import router as chat_history_router
from .routes.admin import router as admin_router
from .routes.auth import router as auth_router
from .routes.billing import router as billing_router
from .routes.child_profiles import router as child_profiles_router
from .routes.child_reports import router as child_reports_router
from .routes.data_deletion import router as data_deletion_router
from .routes.internal_email import router as internal_email_router
from .routes.homework import parent_router as parent_homework_router
from .routes.homework import router as homework_router
from .routes.problem_reports import router as problem_reports_router
from .routes.session_activity import router as session_activity_router
from .routes.student_dashboard import router as student_dashboard_router
from .routes.student_auth import router as student_auth_router
from .routes.waitlist import router as waitlist_router
from .routes.voice import router as voice_router
from .routes.referrals import internal_router as internal_referrals_router
from .routes.referrals import router as referrals_router
from .schemas.chat_history import ChatMessageCreateRequest, ChatThreadCreateRequest
from .services.access_control import require_child_access, require_parent_access, require_student_child_access
from .services.assessment_service import evaluate_assessment
from .services.app_data_service import AppDataService
from .services.chat_store import ChatStore
from .services.homework_service import HomeworkService
from .services.learning_memory_service import LearningMemoryService
from .services.llm.router import LLMRouter
from .services.learning_profile_service import LearningProfileService
from .services.monitoring_service import MonitoringService
from .services.session_activity_service import SessionActivityService
from .services.tutor_answer_checker import TutorAnswerChecker
from .services.topic_resolver import TopicResolver
from .tutoring_logic import build_chat_directives, update_tutoring_state_after_reply
from .utils.multi_step_progress import build_progress_tracker_directives, update_multi_step_progress
from .utils.tutor_response import format_student_reply, looks_incomplete_response

settings = get_settings()
logger = logging.getLogger(__name__)
MonitoringService().configure()
app = FastAPI(title='MsAlisia Phase 1 MVP API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list(), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(child_profiles_router)
app.include_router(child_reports_router)
app.include_router(data_deletion_router)
app.include_router(internal_email_router)
app.include_router(homework_router)
app.include_router(parent_homework_router)
app.include_router(problem_reports_router)
app.include_router(session_activity_router)
app.include_router(student_dashboard_router)
app.include_router(student_auth_router)
app.include_router(chat_history_router)
app.include_router(waitlist_router)
app.include_router(voice_router)
app.include_router(referrals_router)
app.include_router(internal_referrals_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    await MonitoringService().capture_exception(request, exc)
    return JSONResponse(
        status_code=500,
        content={'detail': 'Something went wrong. Please try again or contact support if it continues.'},
    )

@app.on_event('startup')
def startup() -> None:
    init_db()
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok', 'phase': 'Phase 1 MVP', 'primary_llm': settings.primary_llm_provider, 'fallback_llm': settings.fallback_llm_provider}


@app.get('/api/curriculum')
def curriculum() -> dict:
    return curriculum_payload()


@app.post('/api/students')
async def save_student(student: StudentProfile, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> dict:
    await require_parent_access(authorization, x_access_mode)
    student_id = await AppDataService().save_student(student)
    return {'ok': True, 'student_id': student_id}


@app.get('/api/students')
async def list_students(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> dict:
    await require_parent_access(authorization, x_access_mode)
    return {'students': await AppDataService().list_students(limit=50)}


@app.post('/api/chat', response_model=ChatResponse)
async def chat(payload: ChatRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChatResponse:
    child_user = await require_child_access(authorization, payload.child_id, x_access_mode)
    if payload.child_id:
        await SessionActivityService().ensure_can_tutor(child_user['id'], payload.child_id)
        await SessionActivityService().record_activity(
            child_user['id'],
            payload.child_id,
            subject=payload.subject,
            topic=payload.topic,
            event_type='message_sent',
        )
    assessment_context = await LearningProfileService().context_for_child_subject(payload.child_id, payload.subject)
    topic_resolution = TopicResolver().resolve(
        subject=payload.subject,
        topic=payload.topic,
        topic_source=payload.topic_source,
        assessment_context=assessment_context,
    )
    resolved_topic = topic_resolution['topic']
    prompt_student = _student_with_assessed_level(payload.student, payload.subject, assessment_context)
    learning_memory_service = LearningMemoryService()
    prior_memory = await learning_memory_service.relevant_for_child_subject(
        payload.child_id,
        payload.subject,
        topic=resolved_topic,
        student_message=payload.message,
        working_level=(assessment_context or {}).get('assessed_level'),
    )
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
                topic=resolved_topic,
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
                topic=resolved_topic,
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
    homework_context_available = _homework_context_available(payload.message, payload.topic, payload.history)
    directives = [
        f'The currently selected subject is {payload.subject}. Stay in this subject unless the student clearly asks to switch to another subject.',
        'Lead the activity with one clear next step. Do not ask broad questions like "What would you like to work on?" when assessment, homework, or current task context is available.',
        'Ask only one question at a time. Do not include multiple open-ended questions in one reply.',
        'Use assessment results when available: start from the assessed working level, recommended topic, or recommended next step before starting unrelated practice.',
        *(['Homework context is present. Start from the uploaded homework summary, typed problem, or suggested next step. Do not ask the student to re-explain an already uploaded assignment.'] if homework_context_available else []),
        'After the current problem is finished, you may end with one short same-subject practice question or mini-check when helpful. Do not add a new practice question before the current step is settled.',
        'Use compact tutor chat: 5-7 short lines maximum for normal help.',
        'For direct math questions, include the main step, calculation, and **Final answer:**.',
        'Use Markdown bold only for short labels such as **Step 1:** and **Final answer:**.',
        'Do not use * for multiplication. Use × for multiplication and ÷ for division.',
        'Do not end with an unfinished sentence or a heading without content.',
        *build_progress_tracker_directives(tutoring_state),
        *learning_memory_service.memory_directives(prior_memory),
        *directives,
    ]
    system = compact_chat_system_prompt(prompt_student, payload.subject, resolved_topic, directives, active_task, assessment_context)
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
                topic=resolved_topic,
                provider=result.provider,
                model=result.model,
                tutoring_state=next_state.model_dump(),
            ))
            history_saved = True
        except Exception as exc:
            logger.warning('Chat history save failed after LLM response: %s', exc)
            history_error = str(exc)
    if payload.child_id:
        await SessionActivityService().exchange_complete(
            child_user['id'],
            payload.child_id,
            subject=payload.subject,
            topic=resolved_topic,
        )
        await learning_memory_service.record_exchange_summary(
            parent_id=child_user['id'],
            child_id=payload.child_id,
            subject=payload.subject,
            topic=resolved_topic,
            grade_level=f'Grade {prompt_student.grade}',
            working_level=(assessment_context or {}).get('assessed_level'),
            student_message=payload.message,
            assistant_text=formatted_reply,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            source='session',
            metadata={
                'provider': result.provider,
                'model': result.model,
                'topic_source': topic_resolution['source'],
                'assessed_level': topic_resolution.get('assessed_level'),
            },
        )
    return ChatResponse(
        reply=formatted_reply,
        provider=result.provider,
        model=result.model,
        fallback_used=result.fallback_used,
        tutoring_state=next_state,
        thread_id=chat_thread_id,
        history_saved=history_saved,
        history_error=history_error,
        resolved_topic=resolved_topic,
        topic_source=topic_resolution['source'],
        assessed_level=topic_resolution.get('assessed_level'),
    )


@app.post('/api/assessments/evaluate', response_model=ChildAssessmentResult)
async def assessments(payload: AssessmentRequest, authorization: str = Header(default='')) -> ChildAssessmentResult:
    student_access = await require_student_child_access(authorization, payload.child_id)
    child = student_access.get('child') or {}
    sanitized_student = _student_from_child_for_assessment(payload.student, child)
    sanitized_payload = payload.model_copy(update={
        'student': sanitized_student,
        'grade': sanitized_student.grade,
        'child_id': student_access['child_id'],
    })
    result = await evaluate_assessment(sanitized_payload, parent_id=student_access['id'])
    return _child_safe_assessment_result(result)


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
    access_user = await require_child_access(authorization, child_id, x_access_mode)
    try:
        student = StudentProfile.model_validate_json(student_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail='Invalid student payload') from exc

    upload = await HomeworkService().upload_for_child_session(parent_id=access_user['id'], child_id=child_id, file=file)
    feedback = upload.ai_validation_summary or 'Your homework was uploaded. Ms. Alisia will help one step at a time.'
    if upload.suggested_next_step:
        feedback = f'{feedback}\n\nNext step: {upload.suggested_next_step}'
    return HomeworkFeedbackResponse(feedback=feedback, provider=upload.provider or 'local', model=upload.model or 'rules')


@app.get('/api/future-modules')
def future_modules() -> dict:
    modules = ['Voice Learning', 'Mobile App', 'Teacher Portal', 'School/LMS Integrations', 'Advanced Analytics', 'Additional K-12 Enrichment', 'Advanced Handwriting AI', 'Science', 'Social Studies', 'Test Prep']
    return {'modules': [{'name': name, 'status': 'Coming Soon'} for name in modules]}


def _student_with_assessed_level(student: StudentProfile, subject: str, assessment_context: dict | None) -> StudentProfile:
    assessed_level = (assessment_context or {}).get('assessed_level')
    if not assessed_level:
        return student
    updates = {}
    if subject == 'Math':
        updates['math_level'] = assessed_level
    elif subject == 'ELA':
        updates['ela_level'] = assessed_level
    elif subject == 'Writing':
        updates['writing_level'] = assessed_level
    return student.model_copy(update=updates) if updates else student


def _homework_context_available(message: str, topic: str, history: list) -> bool:
    searchable = ' '.join([
        message or '',
        topic or '',
        ' '.join(str(getattr(item, 'content', '')) for item in (history or [])[-6:]),
    ]).lower()
    return any(marker in searchable for marker in (
        'homework',
        'worksheet',
        'uploaded',
        'upload',
        'photo',
        'assignment',
        'ms. alisia looked at',
    ))


def _student_from_child_for_assessment(student: StudentProfile, child: dict) -> StudentProfile:
    child_name = child.get('name') or student.name
    grade = _grade_number(child.get('grade_level')) or student.grade
    return student.model_copy(update={'name': child_name, 'grade': grade})


def _grade_number(value: object) -> int | None:
    if isinstance(value, int):
        return value if 3 <= value <= 12 else None
    text = str(value or '')
    digits = ''.join(character for character in text if character.isdigit())
    if not digits:
        return None
    grade = int(digits)
    return grade if 3 <= grade <= 12 else None


def _child_safe_assessment_result(result: AssessmentResult) -> ChildAssessmentResult:
    subject = _subject_label(result.subject)
    performance_label = _child_safe_performance_label(result.score_label)
    strengths = _child_safe_strengths(result.strengths, subject)
    practice_next = _child_safe_next_step(result)
    score_summary = f'Next focus: {practice_next}'
    celebration_title = 'Check-in complete'
    celebration_message = f'You completed your {subject} check-in.'
    next_step_message = f'Next, Ms. Alisia will help you practice {practice_next} one step at a time.'
    encouragement = "Glad you completed it. We'll work on this together one step at a time."
    message = f'{celebration_message} {encouragement}'
    return ChildAssessmentResult(
        subject=result.subject,
        child_message=message,
        estimated_level='Learning path ready',
        score_label=performance_label,
        strengths=strengths,
        learning_gaps=[],
        recommended_progression=[next_step_message],
        recommended_next_topics=[practice_next] if practice_next else [],
        parent_summary=message,
        celebration_title=celebration_title,
        celebration_message=celebration_message,
        performance_label=performance_label,
        score_summary=score_summary,
        strengths_for_child=strengths,
        practice_next=practice_next,
        next_step_message=next_step_message,
        badge_label='Check-in Complete',
        encouragement=encouragement,
    )


def _subject_label(subject: str) -> str:
    return 'Reading' if subject == 'ELA' else subject


def _child_safe_performance_label(score_label: str | None) -> str:
    text = _clean_child_safe_text(score_label or '')
    lower = text.lower()
    if not text:
        return 'Learning Path Ready'
    if any(word in lower for word in ('excellent', 'advanced', 'strong', 'master', 'great')):
        return 'Ready for the Next Step'
    if any(word in lower for word in ('ready', 'proficient', 'on track', 'solid')):
        return 'Ready for the Next Step'
    if any(word in lower for word in ('progress', 'develop', 'practice', 'review', 'emerging')):
        return 'Ready for Practice'
    return 'Learning Path Ready'


def _child_safe_strengths(strengths: list[str], subject: str) -> list[str]:
    safe = [_clean_child_safe_text(item) for item in strengths]
    safe = [item for item in safe if item]
    if safe:
        return safe[:2]
    return ['You finished the check-in.', f'Ms. Alisia knows what to practice next in {subject}.']


def _child_safe_next_step(result: AssessmentResult) -> str:
    candidates = [
        *(result.recommended_next_topics or []),
        *(result.recommended_progression or []),
        *(result.learning_gaps or []),
    ]
    for item in candidates:
        safe = _clean_child_safe_text(item)
        if safe:
            return safe
    return f'{_subject_label(result.subject)} practice'


def _clean_child_safe_text(value: object) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    replacements = {
        'weaknesses': 'skills to practice',
        'weakness': 'skill to practice',
        'weak': 'ready to practice',
        'failed': 'needs another try',
        'failure': 'needs another try',
        'deficient': 'still growing',
        'diagnostic': 'learning',
        'clinical': 'learning',
        'below grade level': 'ready for guided practice',
        'below level': 'ready for guided practice',
        'learning gaps': 'practice topics',
        'learning gap': 'practice topic',
    }
    for old, new in replacements.items():
        text = text.replace(old, new).replace(old.title(), new)
    return text[:160]
