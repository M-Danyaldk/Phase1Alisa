from pathlib import Path
import logging
import re

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .curriculum import curriculum_payload
from .database import init_db
from .assessment_validation import extract_math_expression
from .assessment_selector import previous_versions_from_assessments, select_next_assessment_version
from .models import AssessmentNextRequest, AssessmentRequest, AssessmentResult, AssessmentSelectionResponse, ChatOpeningRequest, ChatOpeningResponse, ChatRequest, ChatResponse, ChildAssessmentResult, HomeworkFeedbackResponse, StudentProfile, TutoringState
from .prompts import compact_chat_system_prompt, tutor_opening_system_prompt
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


@app.post('/api/chat/opening', response_model=ChatOpeningResponse)
async def chat_opening(payload: ChatOpeningRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChatOpeningResponse:
    child_user = await require_child_access(authorization, payload.child_id, x_access_mode)
    if payload.child_id:
        await SessionActivityService().ensure_can_tutor(child_user['id'], payload.child_id)
        await SessionActivityService().record_activity(
            child_user['id'],
            payload.child_id,
            subject=payload.subject,
            topic=payload.topic,
            event_type='activity',
        )
    child_profile = child_user.get('child') or {}
    assessment_context = await LearningProfileService().context_for_child_subject(payload.child_id, payload.subject)
    topic_resolution = TopicResolver().resolve(
        subject=payload.subject,
        topic=payload.topic,
        topic_source=payload.topic_source,
        assessment_context=assessment_context,
    )
    resolved_topic = topic_resolution['topic']
    prompt_student = _student_with_assessed_level(_student_from_child(payload.student, child_profile), payload.subject, assessment_context)
    system = tutor_opening_system_prompt(prompt_student, payload.subject, resolved_topic, assessment_context)
    user = (
        'Write the first visible message for this new student tutoring session. '
        'Ask how the child is doing before beginning learning. '
        'You may mention that after they answer, you will ask one quick learning question to know how to help today. '
        'Do not invent any mood, memory, homework, hobby, or prior performance.'
    )
    result = await LLMRouter().generate(system=system, user=user, purpose='opening')
    opening = _safe_opening_reply(format_student_reply(result.text), prompt_student.name)

    chat_thread_id: str | None = None
    history_saved = False
    history_error: str | None = None
    try:
        chat_store = ChatStore()
        thread = await chat_store.create_thread(child_user['id'], ChatThreadCreateRequest(
            child_id=payload.child_id,
            subject=payload.subject,
            topic=resolved_topic,
            title=_session_title(payload.subject, resolved_topic),
        ))
        chat_thread_id = thread['id']
        await chat_store.store_message(child_user['id'], ChatMessageCreateRequest(
            thread_id=chat_thread_id,
            child_id=payload.child_id,
            role='msalisia',
            content=opening,
            subject=payload.subject,
            topic=resolved_topic,
            provider=result.provider,
            model=result.model,
            tutoring_state=TutoringState().model_dump(),
        ))
        history_saved = True
    except Exception as exc:
        logger.warning('Chat opening history save failed: %s', exc)
        history_error = str(exc)

    return ChatOpeningResponse(
        reply=opening,
        provider=result.provider,
        model=result.model,
        fallback_used=result.fallback_used,
        thread_id=chat_thread_id,
        history_saved=history_saved,
        history_error=history_error,
        resolved_topic=resolved_topic,
        topic_source=topic_resolution['source'],
        assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
    )


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
    child_profile = child_user.get('child') or {}
    assessment_context = await LearningProfileService().context_for_child_subject(payload.child_id, payload.subject)
    topic_resolution = TopicResolver().resolve(
        subject=payload.subject,
        topic=payload.topic,
        topic_source=payload.topic_source,
        assessment_context=assessment_context,
    )
    resolved_topic = topic_resolution['topic']
    prompt_student = _student_with_assessed_level(_student_from_child(payload.student, child_profile), payload.subject, assessment_context)
    learning_memory_service = LearningMemoryService()
    prior_memory = await learning_memory_service.relevant_for_child_subject(
        payload.child_id,
        payload.subject,
        topic=resolved_topic,
        student_message=payload.message,
        working_level=_practice_level_label((assessment_context or {}).get('assessed_level')),
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
                title=_session_title(payload.subject, resolved_topic),
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
    answer_checker = TutorAnswerChecker()
    direct_answer_check = answer_checker.check_direct_math_statement(payload.message) if payload.subject == 'Math' else None
    if direct_answer_check and direct_answer_check.status != 'unclear':
        direct_attempt_count = _direct_math_attempt_count(payload.tutoring_state, direct_answer_check)
        tutoring_state = tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'current_step': direct_answer_check.checked_expression,
            'current_question': direct_answer_check.checked_expression,
            'student_answer': payload.message,
            'correctness_status': direct_answer_check.status,
            'expected_answer': direct_answer_check.expected_answer,
            'attempt_count': direct_attempt_count,
            'hint_given': direct_answer_check.is_wrong and direct_attempt_count < 3,
            'answer_revealed': direct_answer_check.is_wrong and direct_attempt_count >= 3,
            'mode': 'practice' if direct_answer_check.is_wrong and direct_attempt_count < 3 else tutoring_state.mode,
            'status': 'waiting_for_student' if direct_answer_check.is_wrong and direct_attempt_count < 3 else tutoring_state.status,
        })
        formatted_reply = _direct_math_check_reply(direct_answer_check, direct_attempt_count)
        if direct_answer_check.is_wrong and direct_attempt_count < 3:
            next_state = tutoring_state
        else:
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
                    provider='local',
                    model='deterministic-math-check',
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after deterministic answer check: %s', exc)
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
                working_level=_practice_level_label((assessment_context or {}).get('assessed_level')),
                student_message=payload.message,
                assistant_text=formatted_reply,
                tutoring_state=next_state,
                thread_id=chat_thread_id,
                source='session',
                metadata={
                    'provider': 'local',
                    'model': 'deterministic-math-check',
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model='deterministic-math-check',
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )
    direct_help_expression = _direct_math_help_expression(payload.message) if payload.subject == 'Math' else ''
    if direct_help_expression:
        tutoring_state = tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'active_problem': direct_help_expression,
            'current_step': direct_help_expression,
            'current_question': direct_help_expression,
            'student_answer': payload.message,
            'correctness_status': '',
            'expected_answer': '',
            'attempt_count': 0,
            'hint_given': True,
            'answer_revealed': False,
            'mode': 'practice',
            'status': 'waiting_for_student',
        })
        formatted_reply = _direct_math_help_reply(direct_help_expression)
        next_state = tutoring_state
        if chat_store and chat_user_id and chat_thread_id:
            try:
                await chat_store.store_message(chat_user_id, ChatMessageCreateRequest(
                    thread_id=chat_thread_id,
                    child_id=payload.child_id,
                    role='msalisia',
                    content=formatted_reply,
                    subject=payload.subject,
                    topic=resolved_topic,
                    provider='local',
                    model='deterministic-math-help',
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after deterministic math help: %s', exc)
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
                working_level=_practice_level_label((assessment_context or {}).get('assessed_level')),
                student_message=payload.message,
                assistant_text=formatted_reply,
                tutoring_state=next_state,
                thread_id=chat_thread_id,
                source='session',
                metadata={
                    'provider': 'local',
                    'model': 'deterministic-math-help',
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model='deterministic-math-help',
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )
    answer_check = None
    if tutoring_state.attempt_count > 0 and (tutoring_state.current_question or current_step):
        answer_check = await answer_checker.check(
            subject=payload.subject,
            question=_answer_check_question(tutoring_state, current_step),
            student_answer=payload.message,
            expected_answer=tutoring_state.expected_answer,
        )
        tutoring_state = tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'student_answer': payload.message,
            'correctness_status': answer_check.status,
            'expected_answer': answer_check.expected_answer or tutoring_state.expected_answer,
            'hint_given': answer_check.is_wrong and tutoring_state.attempt_count == 1,
            'answer_revealed': answer_check.is_wrong and tutoring_state.attempt_count >= 3,
        })
        if answer_check.is_correct:
            directives.append('Backend answer check: correct. Praise briefly, then give one small next step or one new same-topic question.')
        elif tutoring_state.attempt_count == 1:
            directives.append('Backend answer check: wrong or unclear on first attempt. Give one helpful hint only. Do not reveal the final answer. Ask the student to try the same question again.')
        elif tutoring_state.attempt_count == 2:
            directives.append('Backend answer check: wrong or unclear on second attempt. Give a stronger hint or one worked sub-step. Do not reveal the final answer. Ask the student to try once more.')
        else:
            if _is_substep_of_active_problem(tutoring_state, current_step):
                directives.append('Backend answer check: wrong or unclear on third attempt for a sub-step of the active problem. Reveal this step answer warmly, explain it simply, then continue and finish the original active problem.')
                directives.append('Do not give one similar new practice question until the original active problem has a clear final answer.')
            else:
                directives.append('Backend answer check: wrong or unclear on third attempt. Reveal the answer warmly, explain it simply, then give one similar new practice question. Do not ask the same question again.')
            if answer_check.expected_answer:
                directives.append(f'Correct answer to explain: {answer_check.expected_answer}')
        if answer_check.feedback_note:
            directives.append(f'Answer-check note: {answer_check.feedback_note}')
    homework_context_available = _homework_context_available(payload.message, payload.topic, payload.history)
    directives = [
        f'The currently selected subject is {payload.subject}. Stay in this subject unless the student clearly asks to switch to another subject.',
        'Lead the activity with one clear next step. Do not ask broad questions like "What would you like to work on?" when recent check-in results, homework, or current task context is available.',
        'Ask only one question at a time. Do not include multiple open-ended questions in one reply.',
        'Use recent check-in results when available: start from the practice focus, recommended topic, or recommended next step before starting unrelated practice.',
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
    user = f"Recent chat:\n{history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or payload.message}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {payload.message}\n\nRespond as Ms. Alisia using the required tutoring method."
    if answer_check and answer_check.is_correct and payload.subject == 'Math':
        formatted_reply = _correct_math_answer_reply(answer_check, tutoring_state, current_step)
        result_provider = 'local'
        result_model = 'deterministic-current-math-check'
        result_fallback_used = False
    elif (
        answer_check
        and answer_check.is_wrong
        and payload.subject == 'Math'
        and tutoring_state.attempt_count >= 3
        and _is_substep_of_active_problem(tutoring_state, current_step)
    ):
        formatted_reply = _substep_reveal_continue_reply(answer_check, tutoring_state, current_step)
        result_provider = 'local'
        result_model = 'deterministic-substep-continuity'
        result_fallback_used = False
    else:
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
        result_provider = result.provider
        result_model = result.model
        result_fallback_used = result.fallback_used
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
                provider=result_provider,
                model=result_model,
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
            working_level=_practice_level_label((assessment_context or {}).get('assessed_level')),
            student_message=payload.message,
            assistant_text=formatted_reply,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            source='session',
            metadata={
                'provider': result_provider,
                'model': result_model,
                'topic_source': topic_resolution['source'],
                'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
            },
        )
    return ChatResponse(
        reply=formatted_reply,
        provider=result_provider,
        model=result_model,
        fallback_used=result_fallback_used,
        tutoring_state=next_state,
        thread_id=chat_thread_id,
        history_saved=history_saved,
        history_error=history_error,
        resolved_topic=resolved_topic,
        topic_source=topic_resolution['source'],
        assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
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


@app.post('/api/assessments/next', response_model=AssessmentSelectionResponse)
async def next_assessment(payload: AssessmentNextRequest, authorization: str = Header(default='')) -> AssessmentSelectionResponse:
    student_access = await require_student_child_access(authorization, payload.child_id)
    child = student_access.get('child') or {}
    grade = _grade_number(child.get('grade_level')) or 4
    previous_assessments = await AppDataService().list_assessments_for_child(student_access['child_id'], limit=100)
    previous_versions = previous_versions_from_assessments(previous_assessments, subject=payload.subject, grade=grade)
    selection = select_next_assessment_version(payload.subject, grade, previous_versions, child_id=student_access['child_id'])
    questions = [
        {'id': question.id, 'prompt': question.question}
        for question in selection.assessment_version.questions
    ]
    return AssessmentSelectionResponse(
        subject=payload.subject,
        grade=grade,
        assessment_version=selection.assessment_version.version,
        question_ids=list(selection.question_ids),
        questions=questions,
    )


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
        feedback = f'{feedback}\n\nUp next: {upload.suggested_next_step}'
    return HomeworkFeedbackResponse(feedback=feedback, provider=upload.provider or 'local', model=upload.model or 'rules')


@app.get('/api/future-modules')
def future_modules() -> dict:
    modules = ['Voice Learning', 'Mobile App', 'Teacher Portal', 'School/LMS Integrations', 'Advanced Analytics', 'Additional K-12 Enrichment', 'Advanced Handwriting AI', 'Science', 'Social Studies', 'Test Prep']
    return {'modules': [{'name': name, 'status': 'Coming Soon'} for name in modules]}


def _student_with_assessed_level(student: StudentProfile, subject: str, assessment_context: dict | None) -> StudentProfile:
    assessed_level = (assessment_context or {}).get('assessed_level')
    if not assessed_level:
        return student
    working_focus = _practice_focus_label(assessed_level)
    safe_level = f'Grade {student.grade} practice focus: {working_focus}' if working_focus else f'Grade {student.grade} learning path ready'
    updates = {}
    if subject == 'Math':
        updates['math_level'] = safe_level
    elif subject == 'ELA':
        updates['ela_level'] = safe_level
    elif subject == 'Writing':
        updates['writing_level'] = safe_level
    return student.model_copy(update=updates) if updates else student


def _student_from_child(student: StudentProfile, child: dict | None) -> StudentProfile:
    if not child:
        return student
    grade = _grade_number(child.get('grade_level')) or student.grade
    updates = {
        'name': child.get('name') or student.name,
        'grade': grade,
        'subjects': _subjects_from_child(child) or student.subjects,
        'learning_goals': child.get('learning_goals') or student.learning_goals,
        'difficulty_level': child.get('difficulty_level') or student.difficulty_level,
        'parent_notes': child.get('parent_notes') or student.parent_notes,
        'confidence': child.get('difficulty_level') or student.confidence,
        'focus_notes': child.get('learning_goals') or student.focus_notes,
    }
    return student.model_copy(update=updates)


def _practice_level_label(value: object) -> str | None:
    focus = _practice_focus_label(value)
    return f'Practice focus: {focus}' if focus else None


def _session_title(subject: str, topic: str | None) -> str:
    label = _subject_label(subject)
    clean_topic = _session_topic_label(subject, topic)
    return f'{label} Practice - {clean_topic}'


def _safe_opening_reply(text: str, student_name: str | None = None) -> str:
    cleaned = ' '.join(str(text or '').split()).strip()
    if cleaned and len(cleaned) <= 420:
        return cleaned
    name = (student_name or '').strip() or 'there'
    return f'Hi {name}, I am glad you are here. Before we start, how are you feeling today? Then I can ask one quick thing so I know how to help.'


def _session_topic_label(subject: str, topic: str | None) -> str:
    text = ' '.join(str(topic or '').split()).strip(' .,:;-')
    if len(text) < 3 or not re.search(r'[A-Za-z]', text):
        if subject == 'Math':
            return 'Multiplication'
        if subject == 'ELA':
            return 'Reading Vocabulary'
        if subject == 'Writing':
            return 'Sentence Writing'
        return 'Guided Practice'
    return text[:48]


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
    return _student_from_child(student, child)


def _subjects_from_child(child: dict) -> list[str]:
    subjects = child.get('subjects') or []
    if isinstance(subjects, list):
        return [str(subject) for subject in subjects if subject]
    if isinstance(subjects, str):
        return [subject for subject in ['Math', 'ELA', 'Writing'] if subject in subjects]
    return []


def _direct_math_attempt_count(state: TutoringState, answer_check) -> int:
    previous_question = (state.current_question or state.current_step or '').strip()
    current_question = (answer_check.checked_expression or '').strip()
    if answer_check.is_correct:
        return state.attempt_count
    if previous_question and current_question and previous_question == current_question:
        return min(state.attempt_count + 1, 3)
    return 1


def _direct_math_check_reply(answer_check, attempt_count: int = 0) -> str:
    expression = answer_check.checked_expression or 'That problem'
    expected = answer_check.expected_answer or 'the answer'
    similar_problem = _similar_direct_math_problem(expression)
    if answer_check.is_correct:
        return (
            f"Yes, that's correct!\n\n"
            f"{expression} = {expected}.\n\n"
            f"Nice work. Want to try one more? What is {similar_problem}?"
        )
    if attempt_count <= 1:
        first_hint, _ = _direct_math_hint_steps(expression)
        return (
            "Not quite yet. Let's try one small hint.\n\n"
            f"{first_hint}"
        )
    if attempt_count == 2:
        _, stronger_hint = _direct_math_hint_steps(expression)
        return (
            "You're close. Let's try it a different way.\n\n"
            f"{stronger_hint}"
        )
    return (
        "Nice effort. Let's finish it together.\n\n"
        f"{expression} = {expected}.\n\n"
        f"Try one similar problem: what is {similar_problem}?"
    )


def _correct_math_answer_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'that answer'
    expression = _display_math_expression_from_state(state, current_step)
    if expression:
        return f"Yes, that's correct!\n\n{expression} = {expected}.\n\nNice work. Let's keep going one small step at a time."
    return f"Yes, that's correct!\n\nThe answer is {expected}.\n\nNice work. Let's keep going one small step at a time."


def _substep_reveal_continue_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'the answer'
    step_expression = (
        answer_check.checked_expression
        or extract_math_expression(state.current_question or current_step or state.current_step)
        or _display_math_expression_from_state(state, current_step)
        or 'this step'
    )
    active_expression = extract_math_expression(state.active_problem) or state.active_problem.strip()
    step_display = _display_ascii_math_expression(step_expression)
    active_display = _display_ascii_math_expression(active_expression)
    next_step = _remaining_multiplication_step(active_expression, step_expression, expected)
    if next_step:
        return (
            "Nice effort. Let's finish this original problem before trying a new one.\n\n"
            f"{step_display} = {expected}.\n\n"
            f"Now come back to {active_display}: {next_step}"
        )
    if active_display:
        return (
            "Nice effort. Let's finish this original problem before trying a new one.\n\n"
            f"{step_display} = {expected}.\n\n"
            f"Now come back to {active_display}. What is the next small step?"
        )
    return (
        "Nice effort. Let's finish this step before trying a new one.\n\n"
        f"{step_display} = {expected}.\n\n"
        "What is the next small step?"
    )


def _answer_check_question(state: TutoringState, current_step: str = '') -> str:
    return '\n'.join(
        part
        for part in [
            state.current_question or current_step,
            state.active_problem,
        ]
        if part
    )


def _display_math_expression_from_state(state: TutoringState, current_step: str = '') -> str:
    for value in (state.current_question, current_step, state.current_step, state.active_problem):
        expression = extract_math_expression(value)
        if expression:
            return expression.replace('*', 'Ã—').replace('/', 'Ã·')
    return ''


def _is_substep_of_active_problem(state: TutoringState, current_step: str = '') -> bool:
    active = (state.active_problem or '').strip().lower().rstrip('?')
    step = (state.current_question or current_step or state.current_step or '').strip().lower().rstrip('?')
    if not active or not step or active == step:
        return False
    return bool(extract_math_expression(active) or extract_math_expression(step))


def _display_ascii_math_expression(expression: str) -> str:
    return (
        str(expression or '')
        .replace('*', 'x')
        .replace('×', 'x')
        .replace('Ã—', 'x')
        .replace('Ãƒâ€”', 'x')
        .replace('/', '÷')
        .replace('Ã·', '÷')
        .replace('ÃƒÂ·', '÷')
        .strip()
    )


def _parse_simple_int_expression(expression: str) -> tuple[int, str, int] | None:
    match = re.search(r'(-?\d+)\s*([+xX*/\-/÷×])\s*(-?\d+)', str(expression or ''))
    if not match:
        return None
    operator = match.group(2)
    if operator in {'x', 'X', '*', '×'}:
        operator = '*'
    elif operator in {'/', '÷'}:
        operator = '/'
    return int(match.group(1)), operator, int(match.group(3))


def _remaining_multiplication_step(active_expression: str, step_expression: str, step_answer: str) -> str:
    active = _parse_simple_int_expression(active_expression)
    step = _parse_simple_int_expression(step_expression)
    if not active or not step:
        return ''
    active_left, active_operator, active_right = active
    step_left, step_operator, step_right = step
    if active_operator != '*' or step_operator != '*' or active_right != step_right:
        return ''
    remainder = active_left - step_left
    if remainder <= 0:
        return ''
    return f"{_display_ascii_math_expression(active_expression)} = {step_answer} + ({remainder} x {active_right}).\n\nWhat is {remainder} x {active_right}?"


def _direct_math_help_expression(message: str) -> str:
    text = message.lower()
    help_markers = (
        'help me',
        'step by step',
        'show me',
        'explain',
        'solve',
        'i do not know',
        "i don't know",
        'i dont know',
        'stuck',
    )
    if not any(marker in text for marker in help_markers):
        return ''
    match = re.search(r'(-?\d+(?:\.\d+)?)\s*([xX×*+\-/÷])\s*(-?\d+(?:\.\d+)?)', message)
    if not match:
        return ''
    return _display_direct_math_expression(match.group(1), match.group(2), match.group(3))


def _direct_math_help_reply(expression: str) -> str:
    first_hint, _ = _direct_math_hint_steps(expression)
    return (
        f"Let's solve {expression} together step by step.\n\n"
        f"{first_hint}"
    )


def _direct_math_hint_steps(expression: str) -> tuple[str, str]:
    multiplication_match = re.match(r'^\s*(\d+)\s*×\s*(\d+)\s*$', expression)
    if multiplication_match:
        left = int(multiplication_match.group(1))
        right = int(multiplication_match.group(2))
        base = (left // 10) * 10
        remainder = left - base
        if base > 0 and remainder > 0:
            base_product = base * right
            remainder_product = remainder * right
            return (
                f"Break {expression} into easier parts. Start with {base} × {right}.\n\n"
                f"What is {base} × {right}?",
                f"{base} × {right} = {base_product}, and {remainder} × {right} = {remainder_product}.\n\n"
                f"Now try adding {base_product} + {remainder_product}.",
            )

    parsed = _parse_display_math_expression(expression)
    if parsed:
        left, operator, right = parsed
        if operator == '+':
            return (
                f"Start by lining up the numbers in {expression}.\n\nWhat do you get when you add the ones first?",
                f"Add the ones first, then the tens. Now try putting those parts together for {expression}.",
            )
        if operator == '-':
            return (
                f"Start with the number before the minus sign in {expression}.\n\nWhat happens when you take away {right}?",
                f"Subtract in small parts if that helps. Now try the subtraction again for {expression}.",
            )
        if operator in {'÷', '/'}:
            return (
                f"Think of {expression} as sharing into equal groups.\n\nHow many groups of {right} fit into {left}?",
                f"Try skip-counting by {right} until you reach {left}, then count how many jumps you made.",
            )
        if operator == '×':
            return (
                f"Think of {expression} as {left} equal groups of {right}.\n\nWhat is the first group worth?",
                f"You can skip-count by {right}, {left} times. Try counting those jumps carefully.",
            )

    return (
        f"Look at {expression} one operation at a time.\n\nWhat operation should we do first?",
        f"Use the operation in {expression} carefully, then compare your result to your answer.\n\nTry the calculation one more time.",
    )


def _display_direct_math_expression(left: str, operator: str, right: str) -> str:
    clean_operator = {'x': '×', 'X': '×', '*': '×', '/': '÷', '÷': '÷'}.get(operator, operator)
    return f'{left} {clean_operator} {right}'


def _parse_display_math_expression(expression: str) -> tuple[int, str, int] | None:
    match = re.match(r'^\s*(-?\d+)\s*([+−\-×xX*/÷])\s*(-?\d+)\s*$', expression)
    if not match:
        return None
    operator = {'x': '×', 'X': '×', '*': '×', '/': '÷', '−': '-'}.get(match.group(2), match.group(2))
    return int(match.group(1)), operator, int(match.group(3))


def _similar_direct_math_problem(expression: str) -> str:
    parsed = _parse_display_math_expression(expression)
    if not parsed:
        return '45 × 4'
    left, operator, right = parsed
    if operator == '+':
        return f'{left + 2} + {right + 1}'
    if operator == '-':
        return f'{max(left + 3, right + 4)} - {right + 1}'
    if operator == '÷':
        divisor = max(abs(right), 2)
        quotient = max(abs(left // divisor) + 1, 2)
        return f'{divisor * quotient} ÷ {divisor}'
    if operator == '×':
        return f'{left + 1} × {right}'
    return '45 × 4'


def _grade_number(value: object) -> int | None:
    if isinstance(value, int):
        return value if 3 <= value <= 12 else None
    text = str(value or '')
    digits = ''.join(character for character in text if character.isdigit())
    if not digits:
        return None
    grade = int(digits)
    return grade if 3 <= grade <= 12 else None


def _practice_focus_label(value: object) -> str:
    text = str(value or '').strip()
    if not text or 'not assessed' in text.lower():
        return ''
    if text.lower().startswith('grade '):
        parts = text.split(maxsplit=2)
        text = parts[2] if len(parts) >= 3 else ''
        text = text.lstrip(' -:–—').strip()
    return text or 'Foundational practice'


def _child_safe_assessment_result(result: AssessmentResult) -> ChildAssessmentResult:
    subject = _subject_label(result.subject)
    practice_next = _child_safe_next_step(result)
    feedback = _child_score_feedback(result, subject, practice_next)
    performance_label = feedback['performance_label']
    strengths = _child_safe_strengths(result.strengths, subject)
    score_summary = feedback['score_summary']
    celebration_title = feedback['celebration_title']
    celebration_message = feedback['celebration_message']
    next_step_message = feedback['next_step_message']
    encouragement = feedback['encouragement']
    badge_label = feedback['badge_label']
    message = f'{celebration_message} {encouragement}'
    return ChildAssessmentResult(
        subject=result.subject,
        child_message=message,
        assessment_version=result.assessment_version,
        assessment_question_ids=result.assessment_question_ids,
        question_results=result.question_results,
        correct_count=result.correct_count,
        total_questions=result.total_questions,
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
        badge_label=badge_label,
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


def _child_score_feedback(result: AssessmentResult, subject: str, practice_next: str) -> dict[str, str]:
    total = result.total_questions or len(result.question_results)
    correct = result.correct_count
    if total <= 0:
        performance_label = _child_safe_performance_label(result.score_label)
        return {
            'performance_label': performance_label,
            'score_summary': f'Next focus: {practice_next}',
            'celebration_title': 'Great work!',
            'celebration_message': f'You just finished your {subject} check-in!',
            'next_step_message': f'Up next, Ms. Alisia will help you practice {practice_next} one step at a time.',
            'encouragement': 'Nice work. Ms. Alisia will choose a helpful next step.',
            'badge_label': 'All Done!',
        }

    review_count = len([item for item in result.question_results if item.status == 'needs_review'])
    incorrect_count = len([item for item in result.question_results if item.status == 'incorrect'])
    partial_count = len([item for item in result.question_results if item.status == 'partially_correct'])
    score_text = f'{correct}/{total} correct'

    if correct == total:
        return {
            'performance_label': 'Ready for the Next Step',
            'score_summary': f'Score: {score_text}',
            'celebration_title': 'Great work!',
            'celebration_message': f'You got all {total} {subject} questions correct.',
            'next_step_message': f'Up next, Ms. Alisia will give you a new {subject} practice step.',
            'encouragement': 'Great job. You got every question right.',
            'badge_label': 'All Correct',
        }

    if review_count and not incorrect_count and not partial_count:
        return {
            'performance_label': 'Ready for a Closer Look',
            'score_summary': f'{review_count}/{total} answer{"s" if review_count != 1 else ""} ready for Ms. Alisia',
            'celebration_title': 'Great work!',
            'celebration_message': f'You just finished your {subject} check-in!',
            'next_step_message': f'Up next, Ms. Alisia will look at your work and help with {practice_next}.',
            'encouragement': 'Nice effort. Ms. Alisia will look at your work gently and help with the next step.',
            'badge_label': 'Nice Start',
        }

    if correct >= max(1, total - 1):
        return {
            'performance_label': 'Strong Start',
            'score_summary': f'Score: {score_text}',
            'celebration_title': 'Nice work',
            'celebration_message': f'You got {correct} out of {total} {subject} questions correct.',
            'next_step_message': f'Up next, Ms. Alisia will help you practice {practice_next} one step at a time.',
            'encouragement': 'You did well. We found one skill to practice next.',
            'badge_label': 'Strong Work',
        }

    if correct > 0:
        return {
            'performance_label': 'Ready for Practice',
            'score_summary': f'Score: {score_text}',
            'celebration_title': 'Good effort',
            'celebration_message': f'You got {correct} out of {total} {subject} questions correct.',
            'next_step_message': f'Up next, Ms. Alisia will help you practice {practice_next} one step at a time.',
            'encouragement': 'You have a good starting point. We will build the next skill together.',
            'badge_label': 'Practice Ready',
        }

    return {
        'performance_label': 'Ready for Practice',
        'score_summary': f'Score: {score_text}',
        'celebration_title': 'Good effort',
        'celebration_message': f'You just finished your {subject} check-in!',
        'next_step_message': f'Up next, Ms. Alisia will help you practice {practice_next} one step at a time.',
        'encouragement': 'This gives us a clear place to start. Ms. Alisia will help one small step at a time.',
        'badge_label': 'Practice Ready',
    }


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
