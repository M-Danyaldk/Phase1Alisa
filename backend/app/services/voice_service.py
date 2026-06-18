import base64
import json
import logging
import re
import time
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile

from ..assessment_validation import extract_math_expression, normalize_math_text
from ..config import get_settings
from ..models import ChatHistoryItem, StudentProfile, TutoringState
from ..prompts import compact_chat_system_prompt
from ..schemas.chat_history import ChatMessageCreateRequest, ChatThreadCreateRequest
from ..schemas.voice import VoiceMessageResponse
from .access_control import child_billing_access_state
from .chat_store import ChatStore
from .learning_memory_service import LearningMemoryService
from .learning_profile_service import LearningProfileService
from .llm.router import LLMRouter
from .session_activity_service import SessionActivityService
from .topic_resolver import TopicResolver
from .tutor_answer_checker import TutorAnswerChecker
from .tutor_intent_classifier import TutorIntentClassifier
from .tutor_math_normalizer import TutorMathNormalizer
from .tutor_subject_classifier import TutorSubjectClassifier
from ..tutoring_logic import (
    build_subject_boundary_reply,
    build_chat_directives,
    build_new_problem_clarification_reply,
    build_resume_paused_problem_reply,
    build_switch_confirmation_reply,
    detect_action_intent,
    detect_off_subject_request,
    update_tutoring_state_after_reply,
)
from ..utils.multi_step_progress import (
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
from ..utils.tutor_response import format_student_reply, looks_incomplete_response

logger = logging.getLogger(__name__)
CHAT_HISTORY_PUBLIC_ERROR = 'Chat history could not be saved.'

VOICE_FALLBACK_MESSAGE = 'No problem - we will use chat instead!'
UNCLEAR_TRANSCRIPT_MESSAGE = 'I could not hear that clearly. Could you try again?'
MAX_AUDIO_BYTES = 12 * 1024 * 1024


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


def _reading_context_question(question: str, history: list[ChatHistoryItem] | None) -> str:
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


def _writing_context_question(question: str, history: list[ChatHistoryItem] | None) -> str:
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


class VoiceService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def synthesize_nudge(self, parent_id: str, child: dict, message: str) -> VoiceMessageResponse:
        timings: dict[str, int] = {}
        total_start = time.perf_counter()
        child_id = child['id']
        await self._ensure_voice_allowed(child_id, child.get('name'))
        await SessionActivityService().ensure_can_tutor(parent_id, child_id)
        try:
            audio_bytes = await self._timed(timings, 'tts_ms', self._synthesize(message))
        except Exception as exc:
            logger.warning('OpenAI TTS nudge failed for child %s: %s', child_id, exc)
            timings['total_ms'] = self._elapsed_ms(total_start)
            return VoiceMessageResponse(
                assistant_text=message,
                fallback_to_chat=True,
                error_message=VOICE_FALLBACK_MESSAGE,
                provider='openai',
                model=self.settings.openai_tts_model or 'gpt-4o-mini-tts',
                timings=timings,
                metadata={'voice_mode': True, 'nudge': True},
            )
        timings['total_ms'] = self._elapsed_ms(total_start)
        return VoiceMessageResponse(
            assistant_text=message,
            assistant_audio_base64=base64.b64encode(audio_bytes).decode('ascii'),
            audio_mime_type='audio/mpeg',
            fallback_to_chat=False,
            provider='openai',
            model=self.settings.openai_tts_model or 'gpt-4o-mini-tts',
            tts_model=self.settings.openai_tts_model,
            timings=timings,
            metadata={'voice_mode': True, 'nudge': True},
        )

    async def handle_message(
        self,
        parent_id: str,
        child: dict,
        audio: UploadFile,
        student: StudentProfile,
        subject: str,
        topic: str = 'general practice',
        topic_source: str = 'manual',
        history: list[ChatHistoryItem] | None = None,
        tutoring_state: TutoringState | None = None,
        thread_id: str | None = None,
    ) -> VoiceMessageResponse:
        timings: dict[str, int] = {}
        total_start = time.perf_counter()
        child_id = child['id']

        await self._ensure_voice_allowed(child_id, child.get('name'))
        await SessionActivityService().ensure_can_tutor(parent_id, child_id)

        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=422, detail='Audio is required.')
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail='Voice message is too long. Please try a shorter recording.')

        transcript = await self._timed(timings, 'stt_ms', self._transcribe(audio_bytes, audio.content_type or 'application/octet-stream'))
        if not transcript:
            timings['total_ms'] = self._elapsed_ms(total_start)
            return VoiceMessageResponse(
                assistant_text=UNCLEAR_TRANSCRIPT_MESSAGE,
                fallback_to_chat=True,
                error_message=UNCLEAR_TRANSCRIPT_MESSAGE,
                provider='deepgram',
                model='stt',
                timings=timings,
            )

        await SessionActivityService().record_activity(
            parent_id,
            child_id,
            subject=subject,
            topic=topic,
            event_type='message_sent',
        )

        chat_result = await self._timed(
            timings,
            'llm_ms',
            self._generate_tutoring_response(
                parent_id=parent_id,
                child=child,
                student=student,
                subject=subject,
                topic=topic,
                topic_source=topic_source,
                transcript=transcript,
                history=history or [],
                tutoring_state=tutoring_state or TutoringState(),
                thread_id=thread_id,
            ),
        )

        audio_base64 = None
        audio_mime_type = None
        tts_error = None
        try:
            tts_bytes = await self._timed(timings, 'tts_ms', self._synthesize(chat_result['assistant_text']))
            audio_base64 = base64.b64encode(tts_bytes).decode('ascii')
            audio_mime_type = 'audio/mpeg'
        except Exception as exc:
            logger.warning('OpenAI TTS failed for child %s: %s', child_id, exc)
            tts_error = VOICE_FALLBACK_MESSAGE

        await SessionActivityService().exchange_complete(
            parent_id,
            child_id,
            subject=subject,
            topic=chat_result.get('resolved_topic') or topic,
        )

        timings['total_ms'] = self._elapsed_ms(total_start)
        return VoiceMessageResponse(
            transcript=transcript,
            assistant_text=chat_result['assistant_text'],
            assistant_audio_base64=audio_base64,
            audio_mime_type=audio_mime_type,
            thread_id=chat_result.get('thread_id'),
            chat_message_id=chat_result.get('assistant_message_id'),
            voice_session_id=chat_result.get('thread_id'),
            fallback_to_chat=bool(tts_error),
            error_message=tts_error,
            provider=chat_result.get('provider') or 'unknown',
            model=chat_result.get('model') or 'unknown',
            tts_model=self.settings.openai_tts_model if audio_base64 else None,
            tutoring_state=chat_result['tutoring_state'],
            history_saved=chat_result.get('history_saved', False),
            history_error=chat_result.get('history_error'),
            resolved_topic=chat_result.get('resolved_topic'),
            topic_source=chat_result.get('topic_source'),
            assessed_level=chat_result.get('assessed_level'),
            timings=timings,
            metadata={'voice_mode': True, 'raw_audio_stored': False},
        )

    async def _ensure_voice_allowed(self, child_id: str, child_name: str | None) -> None:
        billing_state = await child_billing_access_state(child_id, child_name=child_name)
        if not billing_state.get('access_allowed'):
            raise HTTPException(status_code=403, detail=billing_state.get('child_blocked_message') or VOICE_FALLBACK_MESSAGE)
        if not billing_state.get('voice_allowed'):
            raise HTTPException(status_code=403, detail='Voice learning is available on Chat + Audio plans.')

    async def _transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        if not self.settings.deepgram_api_key:
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE)
        params = {
            'model': 'nova-2',
            'language': 'en-US',
            'punctuate': 'true',
            'smart_format': 'true',
            'filler_words': 'false',
            'utterances': 'false',
        }
        headers = {
            'Authorization': f'Token {self.settings.deepgram_api_key}',
            'Content-Type': content_type,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.settings.deepgram_api_url, params=params, headers=headers, content=audio_bytes)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning('Deepgram STT failed: %s', exc)
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE) from exc
        data = response.json()
        transcript = (
            (((data.get('results') or {}).get('channels') or [{}])[0].get('alternatives') or [{}])[0].get('transcript') or ''
        )
        return ' '.join(str(transcript).split()).strip()

    async def _generate_tutoring_response(
        self,
        parent_id: str,
        child: dict,
        student: StudentProfile,
        subject: str,
        topic: str,
        topic_source: str,
        transcript: str,
        history: list[ChatHistoryItem],
        tutoring_state: TutoringState,
        thread_id: str | None,
    ) -> dict:
        child_id = child['id']
        assessment_context = await LearningProfileService().context_for_child_subject(child_id, subject)
        learning_memory_service = LearningMemoryService()
        topic_resolution = TopicResolver().resolve(
            subject=subject,
            topic=topic,
            topic_source=topic_source,
            assessment_context=assessment_context,
        )
        resolved_topic = topic_resolution['topic']
        prior_memory = await learning_memory_service.relevant_for_child_subject(
            child_id,
            subject,
            topic=resolved_topic,
            student_message=transcript,
            working_level=(assessment_context or {}).get('assessed_level'),
        )
        prompt_student = self._student_with_assessed_level(self._student_from_child(student, child), subject, assessment_context)

        chat_store: ChatStore | None = None
        chat_thread_id = thread_id
        history_saved = False
        history_error = None
        assistant_message_id = None
        try:
            chat_store = ChatStore()
            if not chat_thread_id:
                thread = await chat_store.create_thread(parent_id, ChatThreadCreateRequest(
                    child_id=child_id,
                    subject=subject,
                    topic=resolved_topic,
                    title=transcript[:48] or None,
                ))
                chat_thread_id = thread['id']
            if chat_thread_id:
                await chat_store.store_message(parent_id, ChatMessageCreateRequest(
                    thread_id=chat_thread_id,
                    child_id=child_id,
                    role='student',
                    content=transcript,
                    subject=subject,
                    topic=resolved_topic,
                    tutoring_state={**tutoring_state.model_dump(), 'voice_mode': True},
                ))
        except Exception as exc:
            logger.warning('Voice chat history setup failed before LLM response: %s', exc)
            chat_store = None
            history_error = CHAT_HISTORY_PUBLIC_ERROR

        effective_transcript = transcript
        if subject == 'Math':
            normalization = await TutorMathNormalizer().normalize_if_needed(subject, transcript, tutoring_state)
            if normalization.normalized_expression:
                effective_transcript = normalization.normalized_expression

        subject_assist = await TutorSubjectClassifier().classify_if_needed(
            subject,
            effective_transcript,
            tutoring_state,
        )
        uncertain_subject_boundary = (
            subject in {'Math', 'ELA', 'Writing'}
            and subject_assist.label == 'ambiguous'
            and subject_assist.confidence in {'medium', 'high'}
            and TutorSubjectClassifier().should_use_fallback(subject, effective_transcript, tutoring_state)
        )

        if detect_off_subject_request(subject, effective_transcript, tutoring_state) or subject_assist.label == 'off_subject' or uncertain_subject_boundary:
            final_state = tutoring_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'attempt_count': 0,
                'hint_given': False,
                'correctness_status': '',
            })
            formatted_reply = build_subject_boundary_reply(subject, final_state)
            result_provider = 'local'
            result_model = 'deterministic-subject-boundary'
            if chat_store and chat_thread_id:
                try:
                    message = await chat_store.store_message(parent_id, ChatMessageCreateRequest(
                        thread_id=chat_thread_id,
                        child_id=child_id,
                        role='msalisia',
                        content=formatted_reply,
                        subject=subject,
                        topic=resolved_topic,
                        provider=result_provider,
                        model=result_model,
                        tutoring_state={**final_state.model_dump(), 'voice_mode': True},
                    ))
                    assistant_message_id = message.get('id')
                    history_saved = True
                except Exception as exc:
                    logger.warning('Voice chat history save failed after subject boundary reply: %s', exc)
                    history_error = CHAT_HISTORY_PUBLIC_ERROR

            await learning_memory_service.record_exchange_summary(
                parent_id=parent_id,
                child_id=child_id,
                subject=subject,
                topic=resolved_topic,
                grade_level=child.get('grade_level'),
                working_level=(assessment_context or {}).get('assessed_level'),
                student_message=transcript,
                assistant_text=formatted_reply,
                tutoring_state=final_state,
                thread_id=chat_thread_id,
                source='voice_session',
                metadata={
                    'provider': result_provider,
                    'model': result_model,
                    'topic_source': topic_resolution['source'],
                    'assessed_level': topic_resolution.get('assessed_level'),
                    'voice_mode': True,
                },
            )

            return {
                'assistant_text': formatted_reply,
                'provider': result_provider,
                'model': result_model,
                'tutoring_state': final_state,
                'thread_id': chat_thread_id,
                'assistant_message_id': assistant_message_id,
                'history_saved': history_saved,
                'history_error': history_error,
                'resolved_topic': resolved_topic,
                'topic_source': topic_resolution['source'],
                'assessed_level': topic_resolution.get('assessed_level'),
            }

        intent_assist = await TutorIntentClassifier().classify_if_needed(
            subject,
            effective_transcript,
            history,
            tutoring_state,
        )
        directives, active_task, current_step, next_state = build_chat_directives(
            effective_transcript,
            history,
            tutoring_state,
            assisted_intent_label=intent_assist.label,
        )
        next_state = next_state.model_copy(update={'current_subject': subject})
        previous_structured_problem_id = tutoring_state.problem_id
        side_problem_active = bool(
            next_state.paused_main_problem.strip()
            and next_state.active_problem.strip()
            and next_state.active_problem.strip() != next_state.paused_main_problem.strip()
            and next_state.mode == 'solve'
            and next_state.status == 'solving'
        )
        if next_state.mode != 'clarify_new_problem' and not side_problem_active:
            next_state = update_multi_step_progress(effective_transcript, next_state)
        if has_structured_math_problem(next_state) and not side_problem_active:
            active_task = next_state.main_problem or active_task
            current_step = current_step_expression(next_state) or current_step
        should_send_structured_roadmap = _should_send_structured_roadmap(
            subject,
            tutoring_state,
            next_state,
            effective_transcript,
            previous_structured_problem_id,
        )
        matched_structured_step = _matching_structured_step(next_state, effective_transcript) if subject == 'Math' else None
        if matched_structured_step:
            next_state = next_state.model_copy(update={
                'student_answer': transcript,
                'attempt_count': 0,
                'correctness_status': '',
                'hint_given': False,
                'answer_revealed': False,
            })
        answer_check = None
        if next_state.attempt_count > 0 and (next_state.current_question or current_step):
            base_check_question = _answer_check_question(next_state, current_step)
            if subject == 'ELA':
                check_question = _reading_context_question(base_check_question, history)
            elif subject == 'Writing':
                check_question = _writing_context_question(base_check_question, history)
            else:
                check_question = base_check_question
            answer_check = await TutorAnswerChecker().check(
                subject=subject,
                question=check_question,
                student_answer=effective_transcript,
                expected_answer=next_state.expected_answer,
            )
            if check_question != base_check_question and subject in {'ELA', 'Writing'}:
                next_state = next_state.model_copy(update={'current_question': check_question})
            next_state = next_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': answer_check.status,
                'expected_answer': answer_check.expected_answer or next_state.expected_answer,
                'hint_given': answer_check.is_wrong and next_state.attempt_count == 1,
                'answer_revealed': answer_check.is_wrong and next_state.attempt_count >= 3,
            })
            if answer_check.is_correct:
                directives.append('Backend answer check: correct. Praise briefly, then give one small next step or one new same-topic question.')
            elif next_state.attempt_count == 1:
                directives.append('Backend answer check: wrong or unclear on first attempt. Give one helpful hint only. Do not reveal the final answer. Ask the student to try the same question again.')
            elif next_state.attempt_count == 2:
                directives.append('Backend answer check: wrong or unclear on second attempt. Give a stronger hint or one worked sub-step. Do not reveal the final answer. Ask the student to try once more.')
            else:
                if _is_substep_of_active_problem(next_state, current_step):
                    directives.append('Backend answer check: wrong or unclear on third attempt for a sub-step of the active problem. Reveal this step answer warmly, explain it simply, then continue and finish the original active problem.')
                    directives.append('Do not give one similar new practice question until the original active problem has a clear final answer.')
                else:
                    directives.append('Backend answer check: wrong or unclear on third attempt. Reveal the answer warmly, explain it simply, then give one similar new practice question. Do not ask the same question again.')
                if answer_check.expected_answer:
                    directives.append(f'Correct answer to explain: {answer_check.expected_answer}')
            if answer_check.feedback_note:
                directives.append(f'Answer-check note: {answer_check.feedback_note}')

        directives = [
            f'The currently selected subject is {subject}. Stay in this subject unless the student clearly asks to switch to another subject.',
            'This message came from voice input. Reply naturally for spoken audio: warm, calm, and concise.',
            'Lead the spoken activity with one clear next step. Do not ask broad questions when recent check-in results, homework, or current task context is available.',
            'Ask only one question at a time. Do not include multiple open-ended questions in one spoken reply.',
            'Use recent check-in results when available: start from the practice focus, recommended topic, or recommended next step before starting unrelated practice.',
            'After the current problem is finished, you may end with one short same-subject practice question or mini-check when helpful. Do not add a new practice question before the current step is settled.',
            'Use compact tutor chat: 5-7 short lines maximum for normal help.',
            'For direct math questions, include the main step, calculation, and **Final answer:**.',
            'Use Markdown bold only for short labels such as **Step 1:** and **Final answer:**.',
            'Do not use * for multiplication. Use x for multiplication and / for division.',
            'Do not end with an unfinished sentence or a heading without content.',
            *build_progress_tracker_directives(next_state),
            *learning_memory_service.memory_directives(prior_memory),
            *directives,
        ]
        system = compact_chat_system_prompt(prompt_student, subject, resolved_topic, directives, active_task, assessment_context)
        recent_history = '\n'.join([f'{item.role}: {item.content}' for item in history[-4:]])
        state_summary = (
            f"Mode: {next_state.mode}; "
            f"Attempt count: {next_state.attempt_count}; "
            f"Correctness: {next_state.correctness_status or 'not checked'}; "
            f"Memory: {next_state.memory_note or 'none'}"
        )
        user = f"Recent chat:\n{recent_history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or effective_transcript}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {transcript}\n\nNormalized math if useful: {effective_transcript}\n\nRespond as Ms. Alisia using the required tutoring method."
        structured_progression = has_structured_math_problem(next_state) and subject == 'Math'
        action_intent = detect_action_intent(effective_transcript)
        special_local_reply = False
        if next_state.mode == 'resume_paused_problem_notice':
            final_state = next_state.model_copy(update={
                'mode': 'practice' if (next_state.current_question or next_state.current_step) else 'solve',
                'status': 'waiting_for_student' if (next_state.current_question or next_state.current_step) else 'solving',
                'paused_main_problem': '',
                'paused_current_step': '',
                'paused_current_question': '',
                'paused_expected_answer': '',
                'paused_completed_steps': [],
            })
            formatted_reply = build_resume_paused_problem_reply(next_state)
            result_provider = 'local'
            result_model = 'deterministic-resume-paused-problem'
            special_local_reply = True
        elif next_state.mode == 'clarify_new_problem':
            final_state = next_state
            formatted_reply = build_new_problem_clarification_reply(next_state)
            result_provider = 'local'
            result_model = 'deterministic-new-problem-clarification'
            special_local_reply = True
        elif (
            subject == 'Math'
            and tutoring_state.problem_status not in {'finished', 'idle'}
            and next_state.paused_main_problem
            and next_state.active_problem.strip()
            and next_state.active_problem.strip() != next_state.paused_main_problem.strip()
            and next_state.mode == 'solve'
            and next_state.status == 'solving'
        ):
            final_state = next_state
            formatted_reply = build_switch_confirmation_reply(next_state, next_state.active_problem)
            result_provider = 'local'
            result_model = 'deterministic-switch-confirmation'
            special_local_reply = True
        elif should_send_structured_roadmap:
            final_state = next_state
            formatted_reply = build_structured_roadmap_reply(next_state)
            result_provider = 'local'
            result_model = 'deterministic-structured-roadmap'
        elif structured_progression and action_intent in {'explain_again', 'clarify_prompt'}:
            final_state = next_state
            formatted_reply = build_structured_step_focus_reply(
                next_state,
                intro=(
                    'No problem. Let me show exactly what this step is asking.'
                    if action_intent == 'clarify_prompt'
                    else 'No problem. Let me say it in a simpler way.'
                ),
            )
            result_provider = 'local'
            result_model = f'deterministic-structured-{action_intent}'
        elif matched_structured_step and matched_structured_step.step_id == next_state.current_step_id:
            final_state = next_state
            formatted_reply = build_structured_step_focus_reply(
                next_state,
                intro='Yes, that is the right step to solve next.',
            )
            result_provider = 'local'
            result_model = 'deterministic-structured-step-selection'
        elif matched_structured_step:
            final_state = next_state
            formatted_reply = _structured_future_step_redirect_reply(next_state, matched_structured_step)
            result_provider = 'local'
            result_model = 'deterministic-structured-step-redirect'
        elif structured_progression and answer_check and answer_check.is_correct:
            final_state = advance_structured_math_problem(next_state, answer_check.expected_answer or next_state.expected_answer)
            formatted_reply = build_structured_step_reply(next_state, final_state)
            result_provider = 'local'
            result_model = 'deterministic-structured-step-completion'
        elif structured_progression and answer_check and answer_check.is_wrong and next_state.attempt_count in {1, 2}:
            final_state = next_state
            formatted_reply = build_structured_retry_reply(next_state, next_state.attempt_count)
            result_provider = 'local'
            result_model = f'deterministic-structured-step-hint-{next_state.attempt_count}'
        elif structured_progression and answer_check and answer_check.is_wrong and next_state.attempt_count >= 3:
            final_state = advance_structured_math_problem(next_state, answer_check.expected_answer or next_state.expected_answer)
            formatted_reply = build_structured_step_reply(next_state, final_state, reveal=True)
            result_provider = 'local'
            result_model = 'deterministic-structured-step-reveal'
        elif (
            answer_check
            and answer_check.is_correct
            and subject == 'Math'
            and _is_substep_of_active_problem(next_state, current_step)
        ):
            formatted_reply = _substep_correct_finish_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = 'deterministic-substep-completion'
        elif answer_check and answer_check.is_correct and subject == 'Math':
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = 'deterministic-current-math-check'
        elif answer_check and subject != 'Math' and (answer_check.expected_answer or answer_check.feedback_note or answer_check.status in {'correct', 'incorrect', 'partially_correct'}):
            formatted_reply = _text_answer_check_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = f'deterministic-{subject.lower()}-text-check'
        elif (
            answer_check
            and answer_check.is_wrong
            and subject == 'Math'
            and next_state.attempt_count >= 3
            and _is_substep_of_active_problem(next_state, current_step)
        ):
            formatted_reply = _substep_reveal_continue_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = 'deterministic-substep-continuity'
        else:
            result = await LLMRouter().generate(system=system, user=user, purpose='chat')
            formatted_reply = format_student_reply(result.text)
            if looks_incomplete_response(formatted_reply, transcript):
                continuation_user = (
                    f'{user}\n\n'
                    f'Previous incomplete answer:\n{formatted_reply}\n\n'
                    'Finish the answer briefly and include the final answer. Do not restart.'
                )
                continuation = await LLMRouter().generate(system=system, user=continuation_user, purpose='chat')
                result.provider = continuation.provider
                result.model = continuation.model
                result.fallback_used = result.fallback_used or continuation.fallback_used
                formatted_reply = format_student_reply(f'{formatted_reply}\n\n{continuation.text}')
            result_provider = result.provider
            result_model = result.model
        if not special_local_reply and not (
            next_state.mode not in {'clarify_new_problem', 'resume_paused_problem_notice'}
            and not should_send_structured_roadmap
            and structured_progression
            and answer_check
            and (
                answer_check.is_correct
                or (answer_check.is_wrong and next_state.attempt_count in {1, 2})
                or (answer_check.is_wrong and next_state.attempt_count >= 3)
            )
        ):
            final_state = update_tutoring_state_after_reply(next_state, effective_transcript, formatted_reply)
            if final_state.mode == 'resume_paused_problem_notice':
                resume_reply = build_resume_paused_problem_reply(final_state)
                if resume_reply.strip():
                    formatted_reply = f'{formatted_reply}\n\n{resume_reply}'
                final_state = final_state.model_copy(update={
                    'mode': 'practice' if (final_state.current_question or final_state.current_step) else 'solve',
                    'status': 'waiting_for_student' if (final_state.current_question or final_state.current_step) else 'solving',
                    'paused_main_problem': '',
                    'paused_current_step': '',
                    'paused_current_question': '',
                    'paused_expected_answer': '',
                    'paused_completed_steps': [],
                })

        if chat_store and chat_thread_id:
            try:
                message = await chat_store.store_message(parent_id, ChatMessageCreateRequest(
                    thread_id=chat_thread_id,
                    child_id=child_id,
                    role='msalisia',
                    content=formatted_reply,
                    subject=subject,
                    topic=resolved_topic,
                    provider=result_provider,
                    model=result_model,
                    tutoring_state={**final_state.model_dump(), 'voice_mode': True},
                ))
                assistant_message_id = message.get('id')
                history_saved = True
            except Exception as exc:
                logger.warning('Voice chat history save failed after LLM response: %s', exc)
                history_error = CHAT_HISTORY_PUBLIC_ERROR

        await learning_memory_service.record_exchange_summary(
            parent_id=parent_id,
            child_id=child_id,
            subject=subject,
            topic=resolved_topic,
            grade_level=child.get('grade_level'),
            working_level=(assessment_context or {}).get('assessed_level'),
            student_message=transcript,
            assistant_text=formatted_reply,
            tutoring_state=final_state,
            thread_id=chat_thread_id,
            source='voice_session',
            metadata={
                'provider': result_provider,
                'model': result_model,
                'topic_source': topic_resolution['source'],
                'assessed_level': topic_resolution.get('assessed_level'),
                'voice_mode': True,
            },
        )

        return {
            'assistant_text': formatted_reply,
            'provider': result_provider,
            'model': result_model,
            'tutoring_state': final_state,
            'thread_id': chat_thread_id,
            'assistant_message_id': assistant_message_id,
            'history_saved': history_saved,
            'history_error': history_error,
            'resolved_topic': resolved_topic,
            'topic_source': topic_resolution['source'],
            'assessed_level': topic_resolution.get('assessed_level'),
        }

    async def _synthesize(self, text: str) -> bytes:
        if not self.settings.openai_api_key:
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE)
        payload = {
            'model': self.settings.openai_tts_model or 'gpt-4o-mini-tts',
            'voice': self.settings.openai_tts_voice or 'nova',
            'input': text,
            'response_format': 'mp3',
        }
        headers = {
            'Authorization': f'Bearer {self.settings.openai_api_key}',
            'Content-Type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(self.settings.openai_tts_api_url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning('OpenAI TTS request failed: %s', exc)
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE) from exc
        return response.content

    async def _timed(self, timings: dict[str, int], key: str, awaitable):
        start = time.perf_counter()
        try:
            return await awaitable
        finally:
            timings[key] = self._elapsed_ms(start)

    def _elapsed_ms(self, start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _student_from_child(self, student: StudentProfile, child: dict) -> StudentProfile:
        return student.model_copy(update={
            'name': child.get('name') or student.name,
            'grade': self._grade_number(child.get('grade_level')) or student.grade,
            'subjects': self._subjects(child) or student.subjects,
            'learning_goals': child.get('learning_goals') or student.learning_goals,
            'difficulty_level': child.get('difficulty_level') or student.difficulty_level,
            'parent_notes': child.get('parent_notes') or student.parent_notes,
            'confidence': child.get('difficulty_level') or student.confidence,
            'focus_notes': child.get('learning_goals') or student.focus_notes,
        })

    def _student_with_assessed_level(self, student: StudentProfile, subject: str, assessment_context: dict | None) -> StudentProfile:
        assessed_level = (assessment_context or {}).get('assessed_level')
        if not assessed_level:
            return student
        working_focus = self._practice_focus_label(assessed_level)
        safe_level = f'Practice focus: {working_focus}' if working_focus else 'Learning path ready'
        updates = {}
        if subject == 'Math':
            updates['math_level'] = safe_level
        elif subject == 'ELA':
            updates['ela_level'] = safe_level
        elif subject == 'Writing':
            updates['writing_level'] = safe_level
        return student.model_copy(update=updates) if updates else student

    def _practice_focus_label(self, value: object) -> str:
        text = str(value or '').strip()
        if not text or 'not assessed' in text.lower():
            return ''
        if text.lower().startswith('grade '):
            parts = text.split(maxsplit=2)
            text = parts[2] if len(parts) >= 3 else ''
            text = text.lstrip(' -:–—').strip()
        return text or 'Foundational practice'

    def _grade_number(self, value: object) -> int | None:
        text = str(value or '')
        digits = ''.join(character for character in text if character.isdigit())
        if not digits:
            return None
        grade = int(digits)
        return grade if 3 <= grade <= 12 else None

    def _subjects(self, child: dict) -> list[str]:
        subjects = child.get('subjects') or []
        if isinstance(subjects, list):
            return [str(subject) for subject in subjects if subject]
        if isinstance(subjects, str):
            return [subject for subject in ['Math', 'ELA', 'Writing'] if subject in subjects]
        return []


def parse_voice_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
