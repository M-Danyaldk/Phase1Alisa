from pathlib import Path
import logging
import re

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .curriculum import curriculum_payload
from .database import init_db
from .assessment_validation import extract_math_expression, normalize_math_text
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
from .services.tutor_emotional_support import (
    apply_emotional_support,
    build_emotional_choice_reply,
    build_emotional_support_plan,
    build_emotional_support_reply,
    build_safety_followup_reply,
    detect_emotional_support_choice,
    resolve_emotional_support_choice,
)
from .services.tutor_intent_classifier import NON_ANSWER_INTENTS, TutorIntentClassifier
from .services.tutor_math_normalizer import TutorMathNormalizer
from .services.tutor_math_response_guard import TutorMathResponseGuard
from .services.tutor_word_problem import (
    StructuredWordProblem,
    TutorWordProblemInterpreter,
    apply_word_problem_state,
    build_word_problem_clarification_reply,
    build_word_problem_start_reply,
)
from .services.tutor_subject_classifier import TutorSubjectClassifier
from .services.topic_resolver import TopicResolver
from .tutor_math_topic_lessons import apply_topic_lesson_state, build_topic_lesson_intro, topic_lesson
from .tutor_math_practice_bank import TutorMathPracticeQuestion, select_tutor_math_question
from .tutor_math_practice_support import (
    build_tutor_practice_support_reply,
    is_tutor_practice_answer_like,
    student_matches_expected_practice_answer,
)
from .tutoring_logic import (
    build_conversation_control_reply,
    build_subject_boundary_reply,
    build_chat_directives,
    build_new_problem_clarification_reply,
    build_resume_paused_problem_reply,
    build_switch_confirmation_reply,
    build_temporary_math_problem_reply,
    detect_action_intent,
    detect_off_subject_request,
    update_tutoring_state_after_reply,
)
from .utils.multi_step_progress import (
    advance_structured_math_problem,
    build_progress_tracker_directives,
    build_structured_roadmap_reply,
    build_structured_retry_reply,
    build_structured_step_focus_reply,
    build_structured_step_reply,
    current_step_expression,
    has_structured_math_problem,
    update_multi_step_progress,
)
from .utils.tutor_response import format_student_reply, looks_incomplete_response
from .utils.task_lifecycle import (
    abandon_active_task,
    can_resume_paused_task,
    complete_active_task,
    pause_active_task,
    reconcile_task_lifecycle,
    resume_latest_paused_task,
    transition_to_task,
)
from .utils.attempt_policy import (
    ensure_answer_attempt_registered,
    preserve_attempt_progress,
    preserve_tutor_practice_context,
    register_answer_attempt,
    reset_attempt_display,
)

settings = get_settings()
logger = logging.getLogger(__name__)
CHAT_HISTORY_PUBLIC_ERROR = 'Chat history could not be saved.'
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
        history_error = CHAT_HISTORY_PUBLIC_ERROR

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
    payload = payload.model_copy(update={'tutoring_state': reconcile_task_lifecycle(payload.tutoring_state)})
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
        history_error = CHAT_HISTORY_PUBLIC_ERROR

    effective_message = payload.message
    word_problem = StructuredWordProblem(original_text=payload.message)
    word_problem_candidate = False
    if payload.subject == 'Math':
        word_problem_interpreter = TutorWordProblemInterpreter()
        word_problem_input = payload.message
        pending_word_problem = (
            payload.tutoring_state.pending_new_problem
            if payload.tutoring_state.pending_input_kind == 'ambiguous_word_problem'
            else ''
        )
        if pending_word_problem:
            word_problem_input = f'{pending_word_problem} The requested result is: {payload.message}.'
        word_problem_candidate = word_problem_interpreter.is_candidate(payload.subject, word_problem_input)
        word_problem = await word_problem_interpreter.interpret_if_needed(payload.subject, word_problem_input)
        if word_problem.accepted and pending_word_problem:
            word_problem = word_problem.model_copy(update={'original_text': pending_word_problem})
        if word_problem.accepted:
            effective_message = word_problem.expression
        else:
            normalization = await TutorMathNormalizer().normalize_if_needed(payload.subject, payload.message, payload.tutoring_state)
            if normalization.normalized_expression:
                effective_message = normalization.normalized_expression

    intent_assist = await TutorIntentClassifier().classify_if_needed(
        payload.subject,
        effective_message,
        payload.history,
        payload.tutoring_state,
    )
    if intent_assist.label == 'answer_current_step' and intent_assist.answer:
        effective_message = intent_assist.answer
    elif intent_assist.label in {'new_problem', 'switch_request'} and intent_assist.normalized_expression:
        effective_message = intent_assist.normalized_expression

    subject_assist = await TutorSubjectClassifier().classify_if_needed(
        payload.subject,
        effective_message,
        payload.tutoring_state,
    )
    uncertain_subject_boundary = (
        payload.subject in {'Math', 'ELA', 'Writing'}
        and subject_assist.label == 'ambiguous'
        and subject_assist.confidence in {'medium', 'high'}
        and TutorSubjectClassifier().should_use_fallback(payload.subject, effective_message, payload.tutoring_state)
    )

    if (
        detect_off_subject_request(payload.subject, effective_message, payload.tutoring_state)
        or subject_assist.label == 'off_subject'
        or uncertain_subject_boundary
    ) and not word_problem_candidate and not intent_assist.needs_clarification and intent_assist.label not in {'emotion', 'pause', 'resume', 'meta_feedback'}:
        next_state = preserve_attempt_progress(payload.tutoring_state, payload.tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'student_answer': payload.message,
            'correctness_status': '',
        }))
        formatted_reply = build_subject_boundary_reply(payload.subject, next_state)
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
                    model='deterministic-subject-boundary',
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after subject boundary reply: %s', exc)
                history_error = CHAT_HISTORY_PUBLIC_ERROR
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
                    'model': 'deterministic-subject-boundary',
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model='deterministic-subject-boundary',
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )

    non_answer_intent = intent_assist.label in NON_ANSWER_INTENTS

    practice_choice = _tutor_practice_choice_intent(payload.tutoring_state, effective_message) if payload.subject == 'Math' else ''
    if practice_choice in {'yes', 'no', 'unclear'}:
        if practice_choice == 'yes':
            practice_question = select_tutor_math_question(
                prompt_student.grade,
                topic=payload.tutoring_state.tutor_practice_topic or resolved_topic,
                recent_question_ids=payload.tutoring_state.recent_tutor_practice_question_ids,
            )
            formatted_reply = _tutor_math_next_practice_reply(practice_question)
            next_state = _tutor_math_question_state(
                payload.tutoring_state,
                payload.subject,
                payload.message,
                practice_question,
            )
            result_model = 'deterministic-tutor-math-next-practice'
        elif practice_choice == 'no':
            formatted_reply = "No problem. Nice work today."
            next_state = payload.tutoring_state.model_copy(update={
                'current_subject': payload.subject,
                'active_problem': '',
                'current_step': '',
                'current_question': '',
                'expected_answer': '',
                'student_answer': payload.message,
                'correctness_status': '',
                'attempt_count': 0,
                'hint_given': False,
                'answer_revealed': False,
                'next_similar_question': '',
                'tutor_practice_question_id': '',
                'tutor_practice_grade': 0,
                'tutor_practice_topic': '',
                'tutor_practice_hint_1': '',
                'tutor_practice_hint_2': '',
                'tutor_practice_explanation': '',
                'problem_status': 'idle',
                'mode': 'solve',
                'status': 'finished',
                'memory_note': 'Tutor practice paused after student chose to stop.',
            })
            result_model = 'deterministic-tutor-math-practice-close'
        else:
            formatted_reply = "Do you want another practice question, or are you done for now?"
            next_state = payload.tutoring_state.model_copy(update={
                'current_subject': payload.subject,
                'student_answer': payload.message,
                'mode': 'awaiting_more_practice_choice',
                'status': 'waiting_for_student',
            })
            result_model = 'deterministic-tutor-math-practice-choice-clarify'
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
                    model=result_model,
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after tutor math practice choice: %s', exc)
                history_error = CHAT_HISTORY_PUBLIC_ERROR
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
                    'model': result_model,
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model=result_model,
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )

    if not non_answer_intent and _should_start_tutor_math_practice(payload, effective_message):
        practice_question = select_tutor_math_question(
            prompt_student.grade,
            topic=resolved_topic,
            recent_question_ids=payload.tutoring_state.recent_tutor_practice_question_ids,
        )
        formatted_reply = _tutor_math_starter_reply(practice_question)
        next_state = _tutor_math_question_state(payload.tutoring_state, payload.subject, payload.message, practice_question)
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
                    model='deterministic-tutor-math-starter',
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after tutor math starter: %s', exc)
                history_error = CHAT_HISTORY_PUBLIC_ERROR
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
                    'model': 'deterministic-tutor-math-starter',
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model='deterministic-tutor-math-starter',
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )

    router = LLMRouter()
    directives, active_task, current_step, tutoring_state = build_chat_directives(
        effective_message,
        payload.history,
        payload.tutoring_state,
        assisted_intent_label=intent_assist.label,
    )
    if intent_assist.label in {
        'greeting',
        'acknowledge',
        'continue_current',
        'related_question',
        'help_request',
        'emotion',
        'pause',
        'resume',
        'meta_feedback',
        'clarification_about_context',
    }:
        tutoring_state = preserve_attempt_progress(payload.tutoring_state, tutoring_state)
        tutoring_state = preserve_tutor_practice_context(payload.tutoring_state, tutoring_state)
    tutoring_state = tutoring_state.model_copy(update={'current_subject': payload.subject})
    previous_structured_problem_id = payload.tutoring_state.problem_id
    side_problem_active = bool(
        tutoring_state.paused_main_problem.strip()
        and tutoring_state.active_problem.strip()
        and tutoring_state.active_problem.strip() != tutoring_state.paused_main_problem.strip()
        and tutoring_state.mode == 'solve'
        and tutoring_state.status == 'solving'
    )
    if word_problem.accepted and not side_problem_active:
        tutoring_state = tutoring_state.model_copy(update={
            'pending_input_kind': '',
            'pending_new_problem': '',
            'mode': 'solve',
            'status': 'solving',
        })
        tutoring_state = update_multi_step_progress(effective_message, tutoring_state)
    elif tutoring_state.mode != 'clarify_new_problem' and not side_problem_active:
        tutoring_state = update_multi_step_progress(effective_message, tutoring_state)
    word_problem_started = bool(
        word_problem.accepted
        and (
            payload.tutoring_state.word_problem_schema.get('original_text') != word_problem.original_text
            or not payload.tutoring_state.active_task_id
            or payload.tutoring_state.problem_status in {'finished', 'idle'}
        )
    )
    if word_problem_started and not side_problem_active:
        tutoring_state = apply_word_problem_state(payload.tutoring_state, tutoring_state, word_problem)
    if has_structured_math_problem(tutoring_state) and not side_problem_active:
        active_task = tutoring_state.main_problem or active_task
        current_step = current_step_expression(tutoring_state) or current_step
    should_send_structured_roadmap = _should_send_structured_roadmap(
        payload.subject,
        payload.tutoring_state,
        tutoring_state,
        effective_message,
        previous_structured_problem_id,
    )
    matched_structured_step = _matching_structured_step(tutoring_state, effective_message) if payload.subject == 'Math' else None
    if matched_structured_step:
        tutoring_state = preserve_attempt_progress(payload.tutoring_state, tutoring_state).model_copy(update={
            'student_answer': payload.message,
            'correctness_status': '',
        })
    answer_checker = TutorAnswerChecker()
    direct_answer_check = (
        answer_checker.check_direct_math_statement(effective_message)
        if (
            payload.subject == 'Math'
            and not word_problem_started
            and not has_structured_math_problem(tutoring_state)
            and not _is_tutor_practice_question_state(payload.tutoring_state)
        )
        else None
    )
    if direct_answer_check and direct_answer_check.status != 'unclear' and not matched_structured_step:
        tutoring_state = ensure_answer_attempt_registered(payload.tutoring_state, tutoring_state)
        direct_attempt_count = tutoring_state.attempt_count
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
        if payload.tutoring_state.active_problem.strip():
            tutoring_state = tutoring_state.model_copy(update={
                'active_problem': payload.tutoring_state.active_problem,
            })
        direct_continuity_state = tutoring_state
        if payload.tutoring_state.active_problem.strip():
            direct_continuity_state = tutoring_state.model_copy(update={
                'active_problem': payload.tutoring_state.active_problem,
            })
        direct_substep_continuity = (
            direct_answer_check.is_wrong
            and direct_attempt_count >= 3
            and _is_substep_of_active_problem(direct_continuity_state)
        )
        if direct_substep_continuity:
            tutoring_state = direct_continuity_state
            formatted_reply = _substep_reveal_continue_reply(direct_answer_check, tutoring_state)
            result_model = 'deterministic-substep-continuity'
        elif direct_answer_check.is_correct and _is_substep_of_active_problem(direct_continuity_state):
            tutoring_state = direct_continuity_state
            formatted_reply = _substep_correct_finish_reply(direct_answer_check, tutoring_state)
            result_model = 'deterministic-substep-completion'
        else:
            formatted_reply = _direct_math_check_reply(direct_answer_check, direct_attempt_count)
            result_model = 'deterministic-math-check'
        if direct_answer_check.is_wrong and direct_attempt_count < 3:
            next_state = tutoring_state
        else:
            next_state = update_tutoring_state_after_reply(tutoring_state, effective_message, formatted_reply)
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
                    model=result_model,
                    tutoring_state=next_state.model_dump(),
                ))
                history_saved = True
            except Exception as exc:
                logger.warning('Chat history save failed after deterministic answer check: %s', exc)
                history_error = CHAT_HISTORY_PUBLIC_ERROR
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
                    'model': result_model,
                    'topic_source': topic_resolution['source'],
                    'assessed_level': _practice_level_label(topic_resolution.get('assessed_level')),
                },
            )
        return ChatResponse(
            reply=formatted_reply,
            provider='local',
            model=result_model,
            fallback_used=False,
            tutoring_state=next_state,
            thread_id=chat_thread_id,
            history_saved=history_saved,
            history_error=history_error,
            resolved_topic=resolved_topic,
            topic_source=topic_resolution['source'],
            assessed_level=_practice_level_label(topic_resolution.get('assessed_level')),
        )
    direct_help_expression = _direct_math_help_expression(effective_message) if payload.subject == 'Math' else ''
    if direct_help_expression and not matched_structured_step:
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
        tutoring_state = transition_to_task(
            payload.tutoring_state,
            tutoring_state,
            direct_help_expression,
            subject='Math',
            source='direct_expression',
            previous='pause',
        )
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
                history_error = CHAT_HISTORY_PUBLIC_ERROR
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
    if (
        tutoring_state.attempt_count > 0
        and (tutoring_state.current_question or current_step)
        and not _is_tutor_practice_question_state(tutoring_state)
        and not _is_tutor_practice_question_state(payload.tutoring_state)
    ):
        base_check_question = _answer_check_question(tutoring_state, current_step)
        if payload.subject == 'ELA':
            check_question = _reading_context_question(base_check_question, payload.history)
        elif payload.subject == 'Writing':
            check_question = _writing_context_question(base_check_question, payload.history)
        else:
            check_question = base_check_question
        answer_check = await answer_checker.check(
            subject=payload.subject,
            question=check_question,
            student_answer=effective_message,
            expected_answer=tutoring_state.expected_answer,
        )
        if check_question != base_check_question and payload.subject in {'ELA', 'Writing'}:
            tutoring_state = tutoring_state.model_copy(update={'current_question': check_question})
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
    homework_context_available = _homework_context_available(effective_message, payload.topic, payload.history)
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
    user = f"Recent chat:\n{history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or effective_message}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {payload.message}\n\nNormalized math if useful: {effective_message}\n\nRespond as Ms. Alisia using the required tutoring method."
    structured_progression = has_structured_math_problem(tutoring_state) and payload.subject == 'Math'
    action_intent = detect_action_intent(effective_message)
    emotional_choice = detect_emotional_support_choice(payload.message, payload.tutoring_state)
    special_local_reply = False
    if payload.tutoring_state.emotional_support_mode == 'safety':
        next_state = preserve_attempt_progress(payload.tutoring_state, payload.tutoring_state.model_copy(update={
            'student_answer': payload.message,
            'correctness_status': '',
            'mode': 'safety_support',
            'status': 'waiting_for_trusted_adult',
        }))
        formatted_reply = build_safety_followup_reply()
        result_provider = 'local'
        result_model = 'deterministic-safety-support-lock'
        result_fallback_used = False
        special_local_reply = True
    elif is_tutor_practice_answer_like(payload.tutoring_state, effective_message):
        practice_state = ensure_answer_attempt_registered(payload.tutoring_state, tutoring_state).model_copy(update={
            'current_subject': payload.subject,
        })
        formatted_reply, next_state = _tutor_practice_answer_reply(
            practice_state,
            effective_message,
            answer_check,
            action_intent,
        )
        result_provider = 'local'
        result_model = 'deterministic-tutor-math-practice-check'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.needs_clarification:
        next_state = preserve_attempt_progress(payload.tutoring_state, payload.tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'student_answer': payload.message,
            'correctness_status': '',
        }))
        formatted_reply = intent_assist.clarification_question
        result_provider = 'local'
        result_model = 'deterministic-semantic-clarification'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.label == 'emotion':
        emotion_plan = build_emotional_support_plan(payload.tutoring_state, payload.message, intent_assist.emotion)
        next_state = apply_emotional_support(payload.tutoring_state, payload.message, emotion_plan)
        formatted_reply = build_emotional_support_reply(emotion_plan, next_state)
        result_provider = 'local'
        result_model = 'deterministic-emotional-support'
        result_fallback_used = False
        special_local_reply = True
    elif emotional_choice:
        next_state = resolve_emotional_support_choice(payload.tutoring_state, emotional_choice)
        formatted_reply = build_emotional_choice_reply(next_state, emotional_choice)
        result_provider = 'local'
        result_model = f'deterministic-emotional-choice-{emotional_choice}'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.label in {'greeting', 'acknowledge', 'continue_current'}:
        next_state = preserve_attempt_progress(payload.tutoring_state, payload.tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'student_answer': payload.message,
            'correctness_status': '',
        }))
        formatted_reply = build_conversation_control_reply(
            next_state,
            intent_assist.label,
            prompt_student.name,
        )
        result_provider = 'local'
        result_model = f'deterministic-conversation-{intent_assist.label}'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.label == 'pause':
        next_state = pause_active_task(_preserved_interruption_state(payload.tutoring_state, payload.subject, payload.message))
        next_state = next_state.model_copy(update={'mode': 'paused', 'status': 'paused'})
        formatted_reply = _pause_interruption_reply(next_state)
        result_provider = 'local'
        result_model = 'deterministic-student-pause'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.label == 'resume':
        next_state = resume_latest_paused_task(payload.tutoring_state)
        formatted_reply = _resume_task_reply(next_state)
        result_provider = 'local'
        result_model = 'deterministic-task-resume'
        result_fallback_used = False
        special_local_reply = True
    elif intent_assist.label == 'topic_switch' and payload.subject == 'Math':
        next_state = _math_topic_switch_state(payload.tutoring_state, payload.message, intent_assist.requested_topic)
        formatted_reply = _math_topic_switch_reply(intent_assist.requested_topic)
        result_provider = 'local'
        result_model = 'deterministic-math-topic-switch'
        result_fallback_used = False
        special_local_reply = True
    elif _is_tutor_practice_question_state(payload.tutoring_state) and intent_assist.label in {'help_request', 'related_question'}:
        formatted_reply, next_state = build_tutor_practice_support_reply(
            payload.tutoring_state,
            payload.message,
            action_intent,
        )
        result_provider = 'local'
        result_model = 'deterministic-tutor-math-practice-support'
        result_fallback_used = False
        special_local_reply = True
    elif (
        _should_grade_tutor_practice(payload.tutoring_state, intent_assist.label)
        or is_tutor_practice_answer_like(payload.tutoring_state, effective_message)
    ):
        practice_state = ensure_answer_attempt_registered(payload.tutoring_state, tutoring_state).model_copy(update={
            'current_subject': payload.subject,
        })
        formatted_reply, next_state = _tutor_practice_answer_reply(
            practice_state,
            effective_message,
            answer_check,
            action_intent,
        )
        result_provider = 'local'
        result_model = 'deterministic-tutor-math-practice-check'
        result_fallback_used = False
        special_local_reply = True
    elif word_problem_candidate and not word_problem.accepted:
        formatted_reply = build_word_problem_clarification_reply()
        next_state = payload.tutoring_state.model_copy(update={
            'current_subject': 'Math',
            'student_answer': payload.message,
            'pending_input_kind': 'ambiguous_word_problem',
            'pending_new_problem': payload.message,
            'mode': 'clarify_word_problem',
            'status': 'waiting_for_student',
        })
        result_provider = 'local'
        result_model = 'deterministic-word-problem-clarification'
        result_fallback_used = False
        special_local_reply = True
    elif tutoring_state.mode == 'resume_paused_problem_notice':
        formatted_reply = build_resume_paused_problem_reply(tutoring_state)
        next_state = tutoring_state.model_copy(update={
            'mode': 'practice' if (tutoring_state.current_question or tutoring_state.current_step) else 'solve',
            'status': 'waiting_for_student' if (tutoring_state.current_question or tutoring_state.current_step) else 'solving',
            'paused_main_problem': '',
            'paused_current_step': '',
            'paused_current_question': '',
            'paused_expected_answer': '',
            'paused_completed_steps': [],
        })
        result_provider = 'local'
        result_model = 'deterministic-resume-paused-problem'
        result_fallback_used = False
        special_local_reply = True
    elif tutoring_state.mode == 'clarify_new_problem':
        formatted_reply = build_new_problem_clarification_reply(tutoring_state)
        next_state = tutoring_state
        result_provider = 'local'
        result_model = 'deterministic-new-problem-clarification'
        result_fallback_used = False
        special_local_reply = True
    elif (
        payload.subject == 'Math'
        and payload.tutoring_state.problem_status not in {'finished', 'idle'}
        and tutoring_state.paused_main_problem
        and can_resume_paused_task(tutoring_state)
        and tutoring_state.active_problem.strip()
        and tutoring_state.active_problem.strip() != tutoring_state.paused_main_problem.strip()
        and tutoring_state.mode == 'solve'
        and tutoring_state.status == 'solving'
        and not extract_math_expression(tutoring_state.active_problem)
    ):
        next_state = tutoring_state.model_copy(update={
            'current_subject': payload.subject,
            'active_problem': tutoring_state.paused_main_problem,
            'current_step': tutoring_state.paused_current_step or tutoring_state.current_step,
            'current_question': tutoring_state.paused_current_question or tutoring_state.current_question or tutoring_state.paused_current_step,
            'expected_answer': tutoring_state.paused_expected_answer or tutoring_state.expected_answer,
            'student_answer': payload.message,
            'correctness_status': '',
            'attempt_count': 0,
            'hint_given': False,
            'mode': 'practice' if (tutoring_state.paused_current_question or tutoring_state.paused_current_step or tutoring_state.current_question or tutoring_state.current_step) else 'solve',
            'status': 'waiting_for_student',
            'paused_main_problem': '',
            'paused_current_step': '',
            'paused_current_question': '',
            'paused_expected_answer': '',
            'paused_completed_steps': [],
        })
        formatted_reply = build_subject_boundary_reply(payload.subject, next_state)
        result_provider = 'local'
        result_model = 'deterministic-subject-boundary-temporary-guard'
        result_fallback_used = False
        special_local_reply = True
    elif (
        payload.subject == 'Math'
        and payload.tutoring_state.problem_status not in {'finished', 'idle'}
        and tutoring_state.paused_main_problem
        and can_resume_paused_task(tutoring_state)
        and tutoring_state.active_problem.strip()
        and tutoring_state.active_problem.strip() != tutoring_state.paused_main_problem.strip()
        and tutoring_state.mode == 'solve'
        and tutoring_state.status == 'solving'
    ):
        formatted_reply = build_temporary_math_problem_reply(tutoring_state.active_problem) or build_switch_confirmation_reply(tutoring_state, tutoring_state.active_problem)
        next_state = update_tutoring_state_after_reply(tutoring_state, effective_message, formatted_reply)
        if next_state.mode == 'resume_paused_problem_notice':
            resume_reply = build_resume_paused_problem_reply(next_state)
            if resume_reply.strip():
                formatted_reply = f'{formatted_reply}\n\n{resume_reply}'
            next_state = next_state.model_copy(update={
                'mode': 'practice' if (next_state.current_question or next_state.current_step) else 'solve',
                'status': 'waiting_for_student' if (next_state.current_question or next_state.current_step) else 'solving',
                'paused_main_problem': '',
                'paused_current_step': '',
                'paused_current_question': '',
                'paused_expected_answer': '',
                'paused_completed_steps': [],
            })
        result_provider = 'local'
        result_model = 'deterministic-temporary-math-problem-return'
        result_fallback_used = False
        special_local_reply = True
    elif word_problem_started and not has_structured_math_problem(tutoring_state):
        formatted_reply = build_word_problem_start_reply(word_problem)
        next_state = tutoring_state
        result_provider = 'local'
        result_model = 'deterministic-structured-word-problem'
        result_fallback_used = False
        special_local_reply = True
    elif should_send_structured_roadmap:
        formatted_reply = build_structured_roadmap_reply(tutoring_state)
        next_state = tutoring_state
        result_provider = 'local'
        result_model = 'deterministic-structured-roadmap'
        result_fallback_used = False
    elif structured_progression and action_intent in {'explain_again', 'clarify_prompt'}:
        formatted_reply = build_structured_step_focus_reply(
            tutoring_state,
            intro=(
                'No problem. Let me show exactly what this step is asking.'
                if action_intent == 'clarify_prompt'
                else 'No problem. Let me say it in a simpler way.'
            ),
        )
        next_state = tutoring_state
        result_provider = 'local'
        result_model = f'deterministic-structured-{action_intent}'
        result_fallback_used = False
    elif matched_structured_step and matched_structured_step.step_id == tutoring_state.current_step_id:
        formatted_reply = build_structured_step_focus_reply(
            tutoring_state,
            intro="Yes, that is the right step to solve next.",
        )
        next_state = tutoring_state
        result_provider = 'local'
        result_model = 'deterministic-structured-step-selection'
        result_fallback_used = False
    elif matched_structured_step:
        formatted_reply = _structured_future_step_redirect_reply(tutoring_state, matched_structured_step)
        next_state = tutoring_state
        result_provider = 'local'
        result_model = 'deterministic-structured-step-redirect'
        result_fallback_used = False
    elif structured_progression and answer_check and answer_check.is_correct:
        next_state = advance_structured_math_problem(tutoring_state, answer_check.expected_answer or tutoring_state.expected_answer)
        formatted_reply = build_structured_step_reply(tutoring_state, next_state)
        result_provider = 'local'
        result_model = 'deterministic-structured-step-completion'
        result_fallback_used = False
    elif structured_progression and answer_check and answer_check.is_wrong and tutoring_state.attempt_count in {1, 2}:
        formatted_reply = build_structured_retry_reply(tutoring_state, tutoring_state.attempt_count)
        next_state = tutoring_state
        result_provider = 'local'
        result_model = f'deterministic-structured-step-hint-{tutoring_state.attempt_count}'
        result_fallback_used = False
    elif structured_progression and answer_check and answer_check.is_wrong and tutoring_state.attempt_count >= 3:
        next_state = advance_structured_math_problem(tutoring_state, answer_check.expected_answer or tutoring_state.expected_answer)
        formatted_reply = build_structured_step_reply(tutoring_state, next_state, reveal=True)
        result_provider = 'local'
        result_model = 'deterministic-structured-step-reveal'
        result_fallback_used = False
    elif (
        answer_check
        and answer_check.is_correct
        and payload.subject == 'Math'
        and _is_substep_of_active_problem(tutoring_state, current_step)
    ):
        formatted_reply = _substep_correct_finish_reply(answer_check, tutoring_state, current_step)
        result_provider = 'local'
        result_model = 'deterministic-substep-completion'
        result_fallback_used = False
    elif answer_check and answer_check.is_correct and payload.subject == 'Math':
        formatted_reply = _correct_math_answer_reply(answer_check, tutoring_state, current_step)
        result_provider = 'local'
        result_model = 'deterministic-current-math-check'
        result_fallback_used = False
    elif answer_check and payload.subject != 'Math' and (answer_check.expected_answer or answer_check.feedback_note or answer_check.status in {'correct', 'incorrect', 'partially_correct'}):
        formatted_reply = _text_answer_check_reply(answer_check, tutoring_state, current_step)
        result_provider = 'local'
        result_model = f'deterministic-{payload.subject.lower()}-text-check'
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
    math_response_guard = TutorMathResponseGuard()
    math_guard_result = None
    if payload.subject == 'Math':
        math_guard_result = math_response_guard.validate(
            formatted_reply,
            tutoring_state,
            intent_label=intent_assist.label,
            source=result_model,
        )
        formatted_reply = math_guard_result.text
    if not special_local_reply and not (
        tutoring_state.mode not in {'clarify_new_problem', 'resume_paused_problem_notice'}
        and not should_send_structured_roadmap
        and structured_progression
        and answer_check
        and (
            answer_check.is_correct
            or (answer_check.is_wrong and tutoring_state.attempt_count in {1, 2})
            or (answer_check.is_wrong and tutoring_state.attempt_count >= 3)
        )
    ):
        next_state = update_tutoring_state_after_reply(tutoring_state, effective_message, formatted_reply)
        if next_state.mode == 'resume_paused_problem_notice':
            resume_reply = build_resume_paused_problem_reply(next_state)
            if resume_reply.strip():
                formatted_reply = f'{formatted_reply}\n\n{resume_reply}'
            next_state = next_state.model_copy(update={
                'mode': 'practice' if (next_state.current_question or next_state.current_step) else 'solve',
                'status': 'waiting_for_student' if (next_state.current_question or next_state.current_step) else 'solving',
                'paused_main_problem': '',
                'paused_current_step': '',
                'paused_current_question': '',
                'paused_expected_answer': '',
                'paused_completed_steps': [],
            })
    if intent_assist.label in {'greeting', 'acknowledge', 'continue_current', 'related_question', 'help_request', 'meta_feedback'}:
        next_state = preserve_tutor_practice_context(payload.tutoring_state, next_state)
    next_state = reconcile_task_lifecycle(next_state)
    if math_guard_result is not None:
        next_state = math_response_guard.apply_metadata(next_state, math_guard_result, result_model)
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
            history_error = CHAT_HISTORY_PUBLIC_ERROR
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


def _should_start_tutor_math_practice(payload: ChatRequest, effective_message: str) -> bool:
    if payload.subject != 'Math':
        return False
    if extract_math_expression(effective_message):
        return False
    state = payload.tutoring_state
    if _has_active_student_math_flow(state):
        return False
    if state.status not in {'', 'idle', 'ready_for_mini_checkin'} and state.mode != 'opening_checkin':
        return False
    if state.mode not in {'', 'solve', 'opening_checkin'}:
        return False
    student_text = ' '.join(str(effective_message or '').lower().split())
    if not student_text:
        return False
    if any(marker in student_text for marker in (
        'homework',
        'worksheet',
        'upload',
        'photo',
        'explain',
        'help me with',
        'solve',
    )):
        return False
    return _history_has_opening_math_prompt(payload.history) or state.mode == 'opening_checkin' or state.status == 'ready_for_mini_checkin'


def _has_active_student_math_flow(state: TutoringState) -> bool:
    return bool(
        state.problem_id
        or state.main_problem.strip()
        or state.active_problem.strip()
        or state.current_step.strip()
        or state.current_question.strip()
        or state.pending_new_problem.strip()
        or state.paused_main_problem.strip()
        or state.ordered_steps
        or state.problem_status in {'in_progress', 'awaiting_step', 'tutor_practice'}
        or state.mode in {
            'practice',
            'clarify_new_problem',
            'helper_branch',
            'queued_followup',
            'resume_paused_problem',
            'resume_paused_problem_notice',
            'tutor_practice_question',
        }
    )


def _tutor_practice_choice_intent(state: TutoringState, effective_message: str) -> str:
    if state.mode != 'awaiting_more_practice_choice' or state.status != 'waiting_for_student':
        return ''
    if extract_math_expression(effective_message):
        return ''
    text = ' '.join(str(effective_message or '').lower().split())
    if not text:
        return 'unclear'
    yes_markers = (
        'y',
        'ye',
        'ya',
        'yah',
        'yes',
        'yes please',
        'yeah',
        'yep',
        'yup',
        'ok',
        'okay',
        'please',
        'sure',
        'give me one',
        'another',
        'another one',
        'more',
        'more practice',
        'start',
        'continue',
        'try one',
        'one more',
    )
    no_markers = (
        'n',
        'nah',
        'no',
        'no thanks',
        'no thank you',
        'nope',
        'done',
        'stop',
        'not now',
        'thats all',
        "that's all",
        'finish',
        'finished',
        'end',
    )
    if any(_choice_marker_matches(text, marker) for marker in no_markers):
        return 'no'
    if any(_choice_marker_matches(text, marker) for marker in yes_markers):
        return 'yes'
    return 'unclear'


def _choice_marker_matches(text: str, marker: str) -> bool:
    if text == marker:
        return True
    return bool(re.search(rf'(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])', text))


def _history_has_opening_math_prompt(history: list) -> bool:
    if not history:
        return False
    last = history[-1]
    if getattr(last, 'role', '') != 'msalisia':
        return False
    text = ' '.join(str(getattr(last, 'content', '') or '').lower().split())
    if not text:
        return False
    mood_markers = (
        'how are you',
        'how are you doing',
        'how are you feeling',
        'before we start',
    )
    quick_markers = (
        'quick math',
        'quick thing',
        'quick question',
        'know how to help',
    )
    return any(marker in text for marker in mood_markers) and any(marker in text for marker in quick_markers)


def _tutor_math_starter_reply(question: TutorMathPracticeQuestion) -> str:
    return (
        "That's good to hear. Let's start with one quick Math question.\n\n"
        f"**Question:** {_display_tutor_math_question(question.question)}"
    )


def _tutor_math_next_practice_reply(question: TutorMathPracticeQuestion) -> str:
    return (
        "Sure. Try this one:\n\n"
        f"**Question:** {_display_tutor_math_question(question.question)}"
    )


def _tutor_math_question_state(
    state: TutoringState,
    subject: str,
    student_message: str,
    practice_question: TutorMathPracticeQuestion,
) -> TutoringState:
    recent_practice_ids = _next_recent_tutor_practice_ids(
        state.recent_tutor_practice_question_ids,
        practice_question.id,
    )
    next_state = state.model_copy(update={
        'current_subject': subject,
        'active_problem': practice_question.question,
        'current_step': practice_question.question,
        'current_question': practice_question.question,
        'expected_answer': practice_question.expected_answer,
        'student_answer': student_message,
        'correctness_status': '',
        'skill': practice_question.skill,
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'tutor_practice_question_id': practice_question.id,
        'tutor_practice_grade': practice_question.grade,
        'tutor_practice_topic': practice_question.topic,
        'tutor_practice_hint_1': practice_question.hint_1,
        'tutor_practice_hint_2': practice_question.hint_2,
        'tutor_practice_explanation': practice_question.worked_explanation,
        'recent_tutor_practice_question_ids': recent_practice_ids,
        'final_answer': '',
        'mode': 'tutor_practice_question',
        'status': 'waiting_for_student',
        'problem_status': 'tutor_practice',
        'memory_note': f'Tutor practice question: {practice_question.question}',
    })
    return transition_to_task(
        state,
        next_state,
        practice_question.question,
        subject=subject,
        topic=practice_question.topic,
        source='practice_bank',
        previous='abandon',
    )


def _is_tutor_practice_question_state(state: TutoringState) -> bool:
    return (
        state.mode == 'tutor_practice_question'
        and state.status == 'waiting_for_student'
        and bool(state.current_question.strip())
        and bool(state.expected_answer.strip())
    )


def _should_grade_tutor_practice(state: TutoringState, intent_label: str) -> bool:
    return _is_tutor_practice_question_state(state) and intent_label == 'answer_current_step'


def _tutor_practice_answer_reply(
    state: TutoringState,
    student_answer: str,
    answer_check,
    action_intent: str,
) -> tuple[str, TutoringState]:
    if action_intent == 'hint':
        hint = state.tutor_practice_hint_2 if state.hint_given and state.tutor_practice_hint_2 else state.tutor_practice_hint_1
        hint = hint or 'Try one small step and then check the numbers again.'
        reply = (
            "Sure. Here's one hint.\n\n"
            f"{hint}\n\n"
            f"Try this same question:\n{_display_tutor_math_question(state.current_question)}"
        )
        return reply, state.model_copy(update={
            'student_answer': student_answer,
            'hint_given': True,
            'status': 'waiting_for_student',
        })

    local_check = answer_check or TutorAnswerChecker()._check_math(
        state.current_question,
        student_answer,
        state.expected_answer,
    )
    attempt_count = state.attempt_count if state.attempt_count > 0 else min(state.attempt_count + 1, 1)
    if local_check.is_correct or student_matches_expected_practice_answer(state, student_answer):
        expected = state.expected_answer or local_check.expected_answer
        explanation = state.tutor_practice_explanation or f'The answer is {expected}.'
        reply = (
            "Yes, that's correct!\n\n"
            f"{_display_tutor_math_question(explanation)}\n\n"
            "Would you like another practice question?"
        )
        return reply, _finished_tutor_practice_state(state, student_answer, 'correct', expected)

    if attempt_count <= 1:
        hint = state.tutor_practice_hint_1 or 'Look at the numbers carefully and try one small step.'
        reply = (
            "Good try.\n\n"
            f"**Hint:** {hint}\n\n"
            f"Try this same question again:\n{_display_tutor_math_question(state.current_question)}"
        )
        return reply, state.model_copy(update={
            'student_answer': student_answer,
            'correctness_status': 'incorrect',
            'attempt_count': 1,
            'hint_given': True,
            'answer_revealed': False,
            'status': 'waiting_for_student',
        })

    if attempt_count == 2:
        hint = state.tutor_practice_hint_2 or state.tutor_practice_hint_1 or 'Try writing the calculation one step at a time.'
        reply = (
            "You're close. Let's use one stronger hint.\n\n"
            f"**Hint:** {hint}\n\n"
            f"Try one more time:\n{_display_tutor_math_question(state.current_question)}"
        )
        return reply, state.model_copy(update={
            'student_answer': student_answer,
            'correctness_status': 'incorrect',
            'attempt_count': 2,
            'hint_given': True,
            'answer_revealed': False,
            'status': 'waiting_for_student',
        })

    expected = state.expected_answer or local_check.expected_answer
    explanation = state.tutor_practice_explanation or f'The answer is {expected}.'
    reply = (
        "Nice effort. Let's finish this one together.\n\n"
        f"{_display_tutor_math_question(explanation)}\n\n"
        "Would you like another practice question?"
    )
    return reply, _finished_tutor_practice_state(state, student_answer, 'incorrect', expected, revealed=True)


def _finished_tutor_practice_state(
    state: TutoringState,
    student_answer: str,
    correctness_status: str,
    expected_answer: str,
    revealed: bool = False,
) -> TutoringState:
    finished_state = state.model_copy(update={
        'active_problem': '',
        'current_step': '',
        'current_question': '',
        'expected_answer': '',
        'student_answer': student_answer,
        'correctness_status': correctness_status,
        'attempt_count': state.attempt_count,
        'hint_given': state.hint_given,
        'answer_revealed': revealed,
        'final_answer': expected_answer,
        'problem_status': 'finished',
        'mode': 'awaiting_more_practice_choice',
        'status': 'waiting_for_student',
        'memory_note': f'Finished tutor practice question: {state.current_question}',
    })
    return complete_active_task(finished_state)


def _next_recent_tutor_practice_ids(previous_ids: list[str] | tuple[str, ...] | None, question_id: str) -> list[str]:
    clean_ids = [str(item) for item in (previous_ids or ()) if str(item).strip() and str(item) != question_id]
    clean_ids.append(question_id)
    return clean_ids[-10:]


def _preserved_interruption_state(state: TutoringState, subject: str, student_message: str) -> TutoringState:
    return state.model_copy(update={
        'current_subject': subject,
        'student_answer': student_message,
        'correctness_status': '',
        'hint_given': state.hint_given,
        'answer_revealed': state.answer_revealed,
    })


def _emotion_interruption_reply(emotion: str, state: TutoringState) -> str:
    plan = build_emotional_support_plan(state, state.student_answer, emotion)
    return build_emotional_support_reply(plan, state)


def _pause_interruption_reply(state: TutoringState) -> str:
    if state.current_question or state.current_step or state.active_problem:
        return 'Of course. Your Math problem is saved. Come back when you are ready, and we can continue from the same place.'
    return 'Of course. Take the time you need, and come back when you are ready.'


def _resume_task_reply(state: TutoringState) -> str:
    problem = state.main_problem or state.active_problem
    question = state.current_question or state.current_step
    if problem and question:
        return f"Welcome back. Let's continue your saved Math problem.\n\n**Problem:** {problem}\n\n**Current step:** {question}"
    if problem:
        return f"Welcome back. Let's continue your saved Math problem:\n\n{problem}"
    return "Welcome back. Your earlier Math problem is already finished, so we can start something new."


def _math_topic_switch_state(state: TutoringState, student_message: str, requested_topic: str) -> TutoringState:
    lesson = topic_lesson(requested_topic)
    if lesson:
        return apply_topic_lesson_state(state, student_message, lesson)

    abandoned = abandon_active_task(state)
    return TutoringState(
        active_task_id=abandoned.active_task_id,
        task_records=abandoned.task_records,
        current_subject='Math',
        student_answer=student_message,
        skill=requested_topic,
        recent_tutor_practice_question_ids=list(state.recent_tutor_practice_question_ids),
        problem_status='idle',
        mode='solve',
        status='idle',
        memory_note=f'Student requested Math topic: {requested_topic}.',
    )


def _math_topic_switch_reply(requested_topic: str) -> str:
    lesson = topic_lesson(requested_topic)
    if lesson:
        return build_topic_lesson_intro(lesson)

    labels = {
        'fraction': 'fractions',
        'decimal': 'decimals',
        'multiplication': 'multiplication',
        'division': 'division',
        'addition': 'addition',
        'subtraction': 'subtraction',
        'geometry': 'geometry',
    }
    label = labels.get(requested_topic, requested_topic or 'that Math topic')
    return (
        f'Sure—we can move to {label}. The earlier practice question will not count against you.\n\n'
        f'Send me your {label} question, or say **give me a {label} question**.'
    )


def _display_tutor_math_question(question: str) -> str:
    text = str(question or '').strip()
    text = re.sub(r'(?<=\d)\s+x\s+(?=\d)', ' × ', text, flags=re.IGNORECASE)
    return text.replace(' / ', ' ÷ ')


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
    previous_question = _normalize_math_match_text(state.current_question or state.current_step or '')
    current_question = _normalize_math_match_text(answer_check.checked_expression or '')
    if answer_check.is_correct:
        return state.attempt_count
    attempt_state = state
    if not previous_question or not current_question or previous_question != current_question:
        attempt_state = reset_attempt_display(state).model_copy(update={
            'current_question': answer_check.checked_expression or state.current_question,
        })
    return register_answer_attempt(attempt_state).attempt_count


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


def _text_answer_check_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    prompt = _clean_text_retry_prompt(state.current_question or current_step or state.current_step or 'that question')
    expected = (answer_check.expected_answer or state.expected_answer or '').strip()
    note = (answer_check.feedback_note or '').strip()

    if answer_check.is_correct:
        if note:
            return f"Yes, that's correct!\n\n{note}\n\nNice work. Let's keep going one small step at a time."
        return "Yes, that's correct!\n\nNice work. Let's keep going one small step at a time."

    if state.attempt_count <= 1:
        hint = note or 'Take one more look at the question and try to make your answer a little clearer.'
        return f"Good try.\n\n{hint}\n\nTry this same question again:\n{prompt}"

    if state.attempt_count == 2:
        hint = note or 'You are close. Add a clearer reason, detail, or full sentence in your answer.'
        return f"Good try.\n\n{hint}\n\nTry the same question one more time:\n{prompt}"

    if expected:
        return (
            "Let's finish this one together.\n\n"
            f"A strong answer would be: {expected}\n\n"
            f"{note or 'Now you can use that idea in the next step.'}"
        )

    return (
        "Let's finish this one together.\n\n"
        f"{note or 'A stronger answer needs clearer words, a complete idea, or better support.'}\n\n"
        "Now let's keep going one small step at a time."
    )


def _clean_text_retry_prompt(prompt: str) -> str:
    cleaned = str(prompt or '').strip()
    if 'finish this sentence' in cleaned.lower():
        stem_match = re.search(r'["“]([^"”]*\.{3}[^"”]*)["”]', cleaned)
        if stem_match:
            return f'Try finishing this sentence:\n"{stem_match.group(1).strip()}"'
    for marker in (
        'Try this same question again:',
        'Try the same question one more time:',
        'Try this same question again',
        'Try the same question one more time',
    ):
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[-1].strip()
    cleaned = cleaned.strip(' "\'')
    return cleaned or 'that question'


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


def _substep_correct_finish_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'that answer'
    step_expression = (
        answer_check.checked_expression
        or extract_math_expression(state.current_question or current_step or state.current_step)
        or _display_math_expression_from_state(state, current_step)
        or 'this step'
    )
    active_expression = extract_math_expression(state.active_problem) or state.active_problem.strip()
    completion = _multiplication_completion(active_expression, step_expression, expected)
    step_display = _display_ascii_math_expression(step_expression)
    if completion:
        return (
            "Yes, that's correct!\n\n"
            f"{step_display} = {expected}.\n\n"
            f"{completion}\n\n"
            "Nice work finishing the original problem."
        )
    active_display = _display_ascii_math_expression(active_expression)
    if active_display:
        return (
            "Yes, that's correct!\n\n"
            f"{step_display} = {expected}.\n\n"
            f"Now finish the original problem: {active_display}."
        )
    return _correct_math_answer_reply(answer_check, state, current_step)


def _answer_check_question(state: TutoringState, current_step: str = '') -> str:
    if has_structured_math_problem(state):
        return current_step_expression(state) or state.current_question or current_step
    return '\n'.join(
        part
        for part in [
            state.current_question or current_step,
            state.active_problem,
        ]
        if part
    )


def _reading_context_question(question: str, history: list) -> str:
    clean_question = str(question or '').strip()
    if not clean_question or '"' in clean_question or '“' in clean_question:
        return clean_question
    lower_question = clean_question.lower()
    reading_starters = ('who ', 'what ', 'where ', 'when ', 'why ', 'how ', 'which ')
    if not (lower_question.startswith(reading_starters) or 'main idea' in lower_question or 'infer' in lower_question):
        return clean_question

    for item in reversed(history or []):
        content = str(getattr(item, 'content', '') or '').strip()
        lower = content.lower()
        if ('quick question' in lower or clean_question.lower() in lower) and re.search(r'["“][^"”]+["”]', content):
            return f'{content}\n\nCurrent question: {clean_question}'
    return clean_question


def _writing_context_question(question: str, history: list) -> str:
    clean_question = str(question or '').strip()
    if not clean_question or '"' in clean_question or '“' in clean_question:
        return clean_question
    if 'finish this sentence' not in clean_question.lower():
        return clean_question

    for item in reversed(history or []):
        content = str(getattr(item, 'content', '') or '').strip()
        lower = content.lower()
        if 'finish this sentence' in lower and re.search(r'["“][^"”]*\.{3}[^"”]*["”]', content):
            return f'{content}\n\nCurrent question: {clean_question}'
    return clean_question


def _display_math_expression_from_state(state: TutoringState, current_step: str = '') -> str:
    if has_structured_math_problem(state):
        expression = current_step_expression(state) or state.current_expression or state.main_problem
        if expression:
            return _display_ascii_math_expression(expression)
    for value in (state.current_question, current_step, state.current_step, state.active_problem):
        expression = extract_math_expression(value)
        if expression:
            return _display_ascii_math_expression(expression)
    return ''


def _is_substep_of_active_problem(state: TutoringState, current_step: str = '') -> bool:
    if has_structured_math_problem(state):
        return bool(state.main_problem and state.current_step_id)
    if state.problem_kind == 'word_problem' and not state.ordered_steps:
        return False
    active = (state.active_problem or '').strip().lower().rstrip('?')
    step = (state.current_question or current_step or state.current_step or '').strip().lower().rstrip('?')
    if not active or not step or active == step:
        return False
    return bool(extract_math_expression(active) or extract_math_expression(step))


def _display_ascii_math_expression(expression: str) -> str:
    return (
        str(expression or '')
        .replace('*', 'x')
        .replace('\u00d7', 'x')
        .replace('Ã—', 'x')
        .replace('Ãƒâ€”', 'x')
        .replace('/', '/')
        .replace('\u00f7', '/')
        .replace('Ã·', '/')
        .replace('ÃƒÂ·', '/')
        .strip()
    )


def _should_send_structured_roadmap(
    subject: str,
    previous_state: TutoringState,
    current_state: TutoringState,
    effective_message: str,
    previous_structured_problem_id: str,
) -> bool:
    if subject != 'Math' or not has_structured_math_problem(current_state):
        return False
    incoming_problem = _normalized_full_math_problem(effective_message)
    current_problem = _normalized_full_math_problem(current_state.main_problem)
    fresh_structured_entry = bool(
        current_state.problem_id
        and current_state.problem_id != previous_structured_problem_id
        and current_state.current_step_index == 0
        and current_state.problem_status == 'awaiting_step'
        and incoming_problem
        and incoming_problem == current_problem
    )
    if fresh_structured_entry:
        return True
    if current_state.attempt_count != 0:
        return False
    if current_state.problem_id != previous_structured_problem_id:
        return True
    if not previous_state.main_problem.strip() or not current_state.main_problem.strip():
        return False
    previous_problem = _normalized_full_math_problem(previous_state.main_problem)
    if not incoming_problem or incoming_problem != previous_problem or incoming_problem != current_problem:
        return False
    return bool(
        previous_state.completed_steps
        or previous_state.completed_step_results
        or previous_state.step_results
        or previous_state.current_step_index > 0
        or previous_state.problem_status == 'finished'
    )


def _normalized_full_math_problem(text: str) -> str:
    normalized = normalize_math_text(text)
    expression = extract_math_expression(normalized) or normalized
    expression = re.sub(r'(?<![\d/])(-?\d+)\s*/\s*(-?\d+)(?![\d/])', r'\1/\2', expression)
    expression = re.sub(r'\s+', ' ', expression).strip()
    return expression


def _normalize_math_match_text(text: str) -> str:
    normalized = normalize_math_text(text)
    expression = extract_math_expression(normalized) or normalized
    expression = re.sub(r'\s+', '', expression)
    return expression.strip().rstrip('?')


def _matching_structured_step(state: TutoringState, message: str):
    if not has_structured_math_problem(state):
        return None
    message_expression = _normalize_math_match_text(message)
    if not message_expression or not any(operator in message_expression for operator in '+-*/()'):
        return None
    for step in state.ordered_steps:
        if _normalize_math_match_text(step.expression) == message_expression:
            return step
    return None


def _structured_future_step_redirect_reply(state: TutoringState, matched_step) -> str:
    current_reply = build_structured_step_focus_reply(
        state,
        intro=f'{matched_step.label} is part of the roadmap, but it comes later.',
    )
    if not current_reply:
        return ''
    return (
        f"{current_reply}\n\n"
        "Let's finish the current step first, then we will move to that later step."
    )


def _parse_simple_int_expression(expression: str) -> tuple[int, str, int] | None:
    match = re.search(r'(-?\d+)\s*([+xX*/\-/\u00f7\u00d7])\s*(-?\d+)', str(expression or ''))
    if not match:
        return None
    operator = match.group(2)
    if operator in {'x', 'X', '*', '\u00d7'}:
        operator = '*'
    elif operator in {'/', '\u00f7'}:
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


def _multiplication_completion(active_expression: str, step_expression: str, step_answer: str) -> str:
    active = _parse_simple_int_expression(active_expression)
    step = _parse_simple_int_expression(step_expression)
    if not active or not step:
        return ''
    active_left, active_operator, active_right = active
    step_left, step_operator, step_right = step
    if active_operator != '*' or step_operator != '*' or active_right != step_right:
        return ''
    other_part = active_left - step_left
    if other_part <= 0:
        return ''
    other_product = other_part * active_right
    total = active_left * active_right
    return f"Now finish {_display_ascii_math_expression(active_expression)}: {other_product} + {step_answer} = {total}.\n\nFinal answer: {total}"


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
    match = re.search(r'(-?\d+(?:\.\d+)?)\s*([xX\u00d7*+\-/\u00f7])\s*(-?\d+(?:\.\d+)?)', message)
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
    multiplication_match = re.match(r'^\s*(\d+)\s*\u00d7\s*(\d+)\s*$', expression)
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
        if operator in {'\u00f7', '/'}:
            return (
                f"Think of {expression} as sharing into equal groups.\n\nHow many groups of {right} fit into {left}?",
                f"Try skip-counting by {right} until you reach {left}, then count how many jumps you made.",
            )
        if operator == '\u00d7':
            return (
                f"Think of {expression} as {left} equal groups of {right}.\n\nWhat is the first group worth?",
                f"You can skip-count by {right}, {left} times. Try counting those jumps carefully.",
            )

    return (
        f"Look at {expression} one operation at a time.\n\nWhat operation should we do first?",
        f"Use the operation in {expression} carefully, then compare your result to your answer.\n\nTry the calculation one more time.",
    )


def _display_direct_math_expression(left: str, operator: str, right: str) -> str:
    clean_operator = {'x': '×', 'X': '×', '*': '×', '/': '÷', '\u00f7': '÷'}.get(operator, operator)
    return f'{left} {clean_operator} {right}'


def _parse_display_math_expression(expression: str) -> tuple[int, str, int] | None:
    match = re.match(r'^\s*(-?\d+)\s*([+\u2212\-\u00d7xX*/\u00f7])\s*(-?\d+)\s*$', expression)
    if not match:
        return None
    operator = {'x': '\u00d7', 'X': '\u00d7', '*': '\u00d7', '/': '\u00f7', '\u2212': '-'}.get(match.group(2), match.group(2))
    return int(match.group(1)), operator, int(match.group(3))


def _similar_direct_math_problem(expression: str) -> str:
    parsed = _parse_display_math_expression(expression)
    if not parsed:
        return '45 x 4'
    left, operator, right = parsed
    if operator == '+':
        return f'{left + 2} + {right + 1}'
    if operator == '-':
        return f'{max(left + 3, right + 4)} - {right + 1}'
    if operator == '\u00f7':
        divisor = max(abs(right), 2)
        quotient = max(abs(left // divisor) + 1, 2)
        return f'{divisor * quotient} / {divisor}'
    if operator == '\u00d7':
        return f'{left + 1} × {right}'
    return '45 x 4'


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
            'score_summary': f'{review_count}/{total} answer{"s" if review_count != 1 else ""} ready for review',
            'celebration_title': 'Great work!',
            'celebration_message': f'You just finished your {subject} check-in!',
            'next_step_message': f'Up next, Ms. Alisia will look at your work and help with {practice_next}.',
            'encouragement': 'Nice effort. Ms. Alisia will look at your work gently and help with the next step.',
            'badge_label': 'Review Ready',
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
