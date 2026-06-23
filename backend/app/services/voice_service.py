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
from .tutor_answer_attempt_feedback import prepend_attempt_feedback
from .tutor_emotional_support import (
    apply_emotional_support,
    build_emotional_choice_reply,
    build_emotional_support_plan,
    build_emotional_support_reply,
    build_safety_followup_reply,
    detect_emotional_support_choice,
    resolve_emotional_support_choice,
)
from .tutor_intent_classifier import NON_ANSWER_INTENTS, TutorIntentClassifier
from .tutor_question_type_router import infer_active_question_type
from .tutor_math_normalizer import TutorMathNormalizer
from .tutor_math_response_guard import TutorMathResponseGuard
from .tutor_progressive_hints import build_progressive_hint_reply, build_progressive_hint_reply_with_fallback
from .tutor_student_arithmetic import (
    StudentArithmeticTask,
    apply_student_arithmetic_state,
    build_student_arithmetic_start_reply,
    parse_student_arithmetic_task,
)
from .tutor_word_problem import (
    StructuredWordProblem,
    TutorWordProblemInterpreter,
    apply_word_problem_state,
    build_word_problem_clarification_reply,
    build_word_problem_start_reply,
)
from .tutor_subject_classifier import TutorSubjectClassifier
from ..tutor_math_practice_bank import TutorMathPracticeQuestion, select_tutor_math_question
from ..tutor_math_practice_support import (
    build_tutor_practice_support_reply,
    is_tutor_practice_answer_like,
)
from ..tutor_math_topic_lessons import apply_topic_lesson_state, build_topic_lesson_intro, topic_lesson
from ..tutoring_logic import (
    build_conversation_control_reply,
    build_subject_boundary_reply,
    build_subject_switch_reply,
    build_chat_directives,
    build_new_problem_clarification_reply,
    build_resume_paused_problem_reply,
    build_switch_confirmation_reply,
    build_temporary_math_problem_reply,
    detect_action_intent,
    detect_off_subject_request,
    resolve_explicit_subject_switch,
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
from ..utils.tutor_response import contextual_unit_feedback, ensure_contextual_final_answer, format_contextual_math_answer, format_student_reply, looks_incomplete_response
from ..utils.task_lifecycle import (
    complete_active_task,
    pause_active_task,
    reconcile_task_lifecycle,
    sync_active_task,
    transition_to_task,
)
from ..utils.attempt_policy import ensure_answer_attempt_registered, preserve_attempt_progress, preserve_tutor_practice_context
from ..utils.tutor_flow_alignment import align_tutor_practice_transition
from ..utils.tutor_surface_parity import (
    correct_math_answer_reply as shared_correct_math_answer_reply,
    continuation_choice_intent as shared_continuation_choice_intent,
    continuation_explanation_reply as shared_continuation_explanation_reply,
    finish_with_continuation_choice as shared_finish_with_continuation_choice,
    has_active_student_math_flow as shared_has_active_student_math_flow,
    history_content as shared_history_content,
    history_has_opening_math_prompt as shared_history_has_opening_math_prompt,
    history_role as shared_history_role,
    is_tutor_practice_question_state as shared_is_tutor_practice_question_state,
    math_fallback_reply as shared_math_fallback_reply,
    opening_math_starter_intro as shared_opening_math_starter_intro,
    opening_math_starter_override as shared_opening_math_starter_override,
    should_start_tutor_math_practice as shared_should_start_tutor_math_practice,
    text_answer_check_reply as shared_text_answer_check_reply,
    tutor_math_next_practice_reply as shared_tutor_math_next_practice_reply,
    tutor_math_question_state as shared_tutor_math_question_state,
    tutor_math_starter_reply as shared_tutor_math_starter_reply,
    tutor_practice_answer_reply as shared_tutor_practice_answer_reply,
    tutor_practice_choice_intent as shared_tutor_practice_choice_intent,
)

logger = logging.getLogger(__name__)
CHAT_HISTORY_PUBLIC_ERROR = 'Chat history could not be saved.'

VOICE_FALLBACK_MESSAGE = 'No problem - we will use chat instead!'
UNCLEAR_TRANSCRIPT_MESSAGE = 'I could not hear that clearly. Could you try again?'
MAX_AUDIO_BYTES = 12 * 1024 * 1024


def _correct_math_answer_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    return shared_correct_math_answer_reply(
        answer_check,
        state,
        current_step,
        display_expression=_display_math_expression_from_state,
    )


def _word_problem_reveal_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'the answer'
    expected_display = format_contextual_math_answer(state, expected)
    expression = (_display_math_expression_from_state(state, current_step) or 'this problem').replace(' x ', ' × ')
    return (
        "Nice effort. Let's finish this one together.\n\n"
        f"{expression} = {expected_display}.\n\n"
        f"**Final answer:** {expected_display}."
    )


def _text_answer_check_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    return shared_text_answer_check_reply(answer_check, state, current_step)


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


def _should_start_tutor_math_practice(
    subject: str,
    state: TutoringState,
    history: list[ChatHistoryItem],
    effective_message: str,
) -> bool:
    return shared_should_start_tutor_math_practice(subject, state, history, effective_message)


def _is_opening_checkin_turn(state: TutoringState) -> bool:
    return (
        state.mode == 'opening_checkin'
        or state.status == 'ready_for_mini_checkin'
    ) and not (
        state.current_question.strip()
        or state.current_step.strip()
        or state.active_problem.strip()
        or state.main_problem.strip()
    )


def _should_override_opening_with_tutor_practice(state: TutoringState, intent_label: str, emotion: str = '') -> bool:
    return _is_opening_checkin_turn(state) and shared_opening_math_starter_override(intent_label, emotion)


def _opening_tutor_practice_intro(state: TutoringState, intent_label: str, emotion: str = '') -> str:
    if not _is_opening_checkin_turn(state):
        return ''
    return shared_opening_math_starter_intro(intent_label, emotion)


def _should_run_answer_evaluation(
    current_state: TutoringState,
    previous_state: TutoringState,
    current_step: str,
    intent_label: str,
) -> bool:
    if current_state.attempt_count <= 0:
        return False
    if not (current_state.current_question or current_step):
        return False
    if _is_tutor_practice_question_state(current_state) or _is_tutor_practice_question_state(previous_state):
        return False
    if _is_opening_checkin_turn(current_state):
        return False
    if infer_active_question_type(current_state) in {'continuation_choice', 'emotion_support'}:
        return False
    return intent_label not in NON_ANSWER_INTENTS


def _has_active_student_math_flow(state: TutoringState) -> bool:
    return shared_has_active_student_math_flow(state)


def _tutor_practice_choice_intent(state: TutoringState, effective_message: str, intent_label: str = '') -> str:
    return shared_tutor_practice_choice_intent(state, effective_message, intent_label)


def _continuation_choice_intent(state: TutoringState, effective_message: str, intent_label: str = '') -> str:
    return shared_continuation_choice_intent(state, effective_message, intent_label)


def _continuation_explanation_reply(state: TutoringState) -> str:
    return shared_continuation_explanation_reply(state)


def _math_fallback_reply(state: TutoringState) -> str:
    return shared_math_fallback_reply(state)


def _finish_with_continuation_choice(
    state: TutoringState,
    *,
    student_answer: str,
    correctness_status: str,
    final_answer: str,
    origin_problem: str,
    origin_type: str,
    origin_explanation: str,
    revealed: bool = False,
    memory_note: str = '',
) -> TutoringState:
    return shared_finish_with_continuation_choice(
        state,
        student_answer=student_answer,
        correctness_status=correctness_status,
        final_answer=final_answer,
        origin_problem=origin_problem,
        origin_type=origin_type,
        origin_explanation=origin_explanation,
        revealed=revealed,
        memory_note=memory_note,
    )


def _finish_single_step_word_problem(
    state: TutoringState,
    *,
    student_answer: str,
    correctness_status: str,
    final_answer: str,
    revealed: bool = False,
) -> TutoringState:
    finished_state = state.model_copy(update={
        'active_problem': '',
        'current_step': '',
        'current_question': '',
        'expected_answer': '',
        'student_answer': student_answer,
        'correctness_status': correctness_status,
        'answer_revealed': revealed,
        'final_answer': final_answer,
        'problem_status': 'finished',
        'mode': 'solve',
        'status': 'idle',
        'memory_note': f'Finished word problem: {state.active_problem or state.main_problem}',
    })
    return complete_active_task(finished_state)


def _choice_marker_matches(text: str, marker: str) -> bool:
    if text == marker:
        return True
    return bool(re.search(rf'(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])', text))


def _history_role(item: ChatHistoryItem | dict) -> str:
    return shared_history_role(item)


def _history_content(item: ChatHistoryItem | dict) -> str:
    return shared_history_content(item)


def _history_has_opening_math_prompt(history: list[ChatHistoryItem]) -> bool:
    return shared_history_has_opening_math_prompt(history)


def _tutor_math_starter_reply(question: TutorMathPracticeQuestion, intro_text: str = '') -> str:
    return shared_tutor_math_starter_reply(
        question,
        _display_tutor_math_question,
        rich_text=False,
        intro_text=intro_text,
    )


def _tutor_math_next_practice_reply(question: TutorMathPracticeQuestion) -> str:
    return shared_tutor_math_next_practice_reply(question, _display_tutor_math_question, rich_text=False)


def _tutor_math_question_state(
    state: TutoringState,
    subject: str,
    student_message: str,
    practice_question: TutorMathPracticeQuestion,
) -> TutoringState:
    return shared_tutor_math_question_state(
        state,
        subject,
        student_message,
        practice_question,
        source_label='Tutor practice question',
        source='voice_practice_bank',
    )


def _is_tutor_practice_question_state(state: TutoringState) -> bool:
    return shared_is_tutor_practice_question_state(state)


def _is_locked_conceptual_math_state(state: TutoringState) -> bool:
    return state.problem_kind in {
        'fraction_comparison',
        'decimal_comparison',
        'percent_comparison',
        'number_comparison',
        'equivalent_fraction',
    }


def _is_locked_student_arithmetic_state(state: TutoringState) -> bool:
    return state.problem_kind in {'arithmetic_single_step', 'arithmetic_multi_step'}


def _tutor_practice_answer_reply(
    state: TutoringState,
    student_answer: str,
    answer_check,
    action_intent: str,
) -> tuple[str, TutoringState]:
    return shared_tutor_practice_answer_reply(
        state,
        student_answer,
        answer_check,
        action_intent,
        display_question=_display_tutor_math_question,
    )


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


def _display_tutor_math_question(question: str) -> str:
    text = str(question or '').strip()
    text = re.sub(r'(?<=\d)\s+x\s+(?=\d)', ' x ', text, flags=re.IGNORECASE)
    return text.replace(' / ', ' divided by ')


def _substep_reveal_continue_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'the answer'
    if state.problem_kind == 'word_problem' and not state.ordered_steps:
        expected_display = format_contextual_math_answer(state, expected)
        expression = _display_math_expression_from_state(state, current_step)
        return (
            "Nice effort. Let's finish this problem together.\n\n"
            f"{expression} = {expected_display}.\n\n"
            f"**Final answer:** {expected_display}."
        )
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
    if state.problem_kind == 'word_problem' and not state.ordered_steps:
        return _correct_math_answer_reply(answer_check, state, current_step)
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
    if _is_locked_student_arithmetic_state(state):
        return False
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

        current_state = tutoring_state or TutoringState()
        transition_allowed = current_state.mode != 'safety_support' and current_state.emotional_support_mode != 'safety'
        activity_subject = resolve_explicit_subject_switch(transcript) if transition_allowed else None
        activity_subject = activity_subject or subject
        activity_topic = topic if activity_subject == subject else 'general practice'

        await SessionActivityService().record_activity(
            parent_id,
            child_id,
            subject=activity_subject,
            topic=activity_topic,
            event_type='message_sent',
        )

        chat_result = await self._timed(
            timings,
            'llm_ms',
            self._generate_tutoring_response(
                parent_id=parent_id,
                child=child,
                student=student,
                subject=activity_subject,
                topic=topic,
                topic_source=topic_source,
                transcript=transcript,
                history=history or [],
                tutoring_state=current_state,
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
            subject=chat_result.get('resolved_subject') or activity_subject,
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
            resolved_subject=chat_result.get('resolved_subject') or activity_subject,
            subject_changed=chat_result.get('subject_changed', False),
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
        transition_allowed = tutoring_state.mode != 'safety_support' and tutoring_state.emotional_support_mode != 'safety'
        resolved_subject = resolve_explicit_subject_switch(transcript) if transition_allowed else None
        prior_subject = tutoring_state.current_subject or subject
        subject_changed = bool(resolved_subject and (resolved_subject != subject or prior_subject != resolved_subject))
        if resolved_subject:
            subject = resolved_subject
            if subject_changed:
                topic = ''
                topic_source = 'default'
                history = []
                tutoring_state = TutoringState(current_subject=resolved_subject)
                thread_id = None
        tutoring_state = reconcile_task_lifecycle(tutoring_state)
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
        word_problem = StructuredWordProblem(original_text=transcript)
        word_problem_candidate = False
        student_arithmetic_task = StudentArithmeticTask()
        if subject == 'Math':
            student_arithmetic_task = parse_student_arithmetic_task(transcript)
            if not student_arithmetic_task.accepted:
                word_problem_interpreter = TutorWordProblemInterpreter()
                word_problem_input = transcript
                pending_word_problem = (
                    tutoring_state.pending_new_problem
                    if tutoring_state.pending_input_kind == 'ambiguous_word_problem'
                    else ''
                )
                if pending_word_problem:
                    word_problem_input = f'{pending_word_problem} The requested result is: {transcript}.'
                word_problem_candidate = word_problem_interpreter.is_candidate(subject, word_problem_input)
                word_problem = await word_problem_interpreter.interpret_if_needed(subject, word_problem_input)
                if word_problem.accepted and pending_word_problem:
                    word_problem = word_problem.model_copy(update={'original_text': pending_word_problem})
                if word_problem.accepted:
                    effective_transcript = word_problem.expression
                else:
                    normalization = await TutorMathNormalizer().normalize_if_needed(subject, transcript, tutoring_state)
                    if normalization.normalized_expression:
                        effective_transcript = normalization.normalized_expression

        intent_assist = await TutorIntentClassifier().classify_if_needed(
            subject,
            effective_transcript,
            history,
            tutoring_state,
        )
        continuation_explain_requested = (
            subject == 'Math'
            and _continuation_choice_intent(tutoring_state, effective_transcript, intent_assist.label) == 'explain'
        )
        if intent_assist.label == 'answer_current_step' and intent_assist.answer:
            effective_transcript = intent_assist.answer
        elif intent_assist.label in {'new_problem', 'switch_request'} and intent_assist.normalized_expression:
            effective_transcript = intent_assist.normalized_expression

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

        if (
            detect_off_subject_request(subject, effective_transcript, tutoring_state)
            or subject_assist.label == 'off_subject'
            or uncertain_subject_boundary
        ) and not continuation_explain_requested and not word_problem_candidate and not intent_assist.needs_clarification and intent_assist.label not in {'help_request', 'related_question', 'emotion', 'pause', 'resume', 'meta_feedback'}:
            final_state = preserve_attempt_progress(tutoring_state, tutoring_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': '',
            }))
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
                'resolved_subject': subject,
                'subject_changed': subject_changed,
            }

        continuation_choice = _continuation_choice_intent(tutoring_state, effective_transcript, intent_assist.label) if subject == 'Math' else ''
        if continuation_choice in {'yes', 'no', 'explain', 'unclear'}:
            if continuation_choice == 'yes':
                practice_question = select_tutor_math_question(
                    prompt_student.grade,
                    topic=tutoring_state.tutor_practice_topic or resolved_topic,
                    recent_question_ids=tutoring_state.recent_tutor_practice_question_ids,
                )
                formatted_reply = _tutor_math_next_practice_reply(practice_question)
                final_state = _tutor_math_question_state(tutoring_state, subject, transcript, practice_question)
                result_model = 'deterministic-voice-tutor-math-next-practice'
            elif continuation_choice == 'no':
                formatted_reply = 'No problem. Nice work today.'
                final_state = tutoring_state.model_copy(update={
                    'current_subject': subject,
                    'active_problem': '',
                    'current_step': '',
                    'current_question': '',
                    'expected_answer': '',
                    'student_answer': transcript,
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
                    'continuation_origin_problem': '',
                    'continuation_origin_answer': '',
                    'continuation_origin_type': '',
                    'continuation_origin_explanation': '',
                })
                result_model = 'deterministic-voice-tutor-math-practice-close'
            elif continuation_choice == 'explain':
                formatted_reply = _continuation_explanation_reply(tutoring_state)
                final_state = tutoring_state.model_copy(update={
                    'current_subject': subject,
                    'student_answer': transcript,
                    'mode': 'awaiting_more_practice_choice',
                    'status': 'waiting_for_student',
                })
                result_model = 'deterministic-voice-tutor-math-practice-explain'
            else:
                formatted_reply = 'Would you like another practice question, a quick explanation of this one, or are you done for now?'
                final_state = tutoring_state.model_copy(update={
                    'current_subject': subject,
                    'student_answer': transcript,
                    'mode': 'awaiting_more_practice_choice',
                    'status': 'waiting_for_student',
                })
                result_model = 'deterministic-voice-tutor-math-practice-choice-clarify'
            result_provider = 'local'
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
                    logger.warning('Voice chat history save failed after tutor math practice choice: %s', exc)
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
                'resolved_subject': subject,
                'subject_changed': subject_changed,
            }

        opening_starter_override = _should_override_opening_with_tutor_practice(tutoring_state, intent_assist.label, intent_assist.emotion)
        if (intent_assist.label not in NON_ANSWER_INTENTS or opening_starter_override) and _should_start_tutor_math_practice(subject, tutoring_state, history, effective_transcript):
            practice_question = select_tutor_math_question(
                prompt_student.grade,
                topic=resolved_topic,
                recent_question_ids=tutoring_state.recent_tutor_practice_question_ids,
            )
            formatted_reply = _tutor_math_starter_reply(
                practice_question,
                intro_text=_opening_tutor_practice_intro(tutoring_state, intent_assist.label, intent_assist.emotion),
            )
            final_state = _tutor_math_question_state(tutoring_state, subject, transcript, practice_question)
            result_provider = 'local'
            result_model = 'deterministic-voice-tutor-math-starter'
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
                    logger.warning('Voice chat history save failed after tutor math starter: %s', exc)
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
                'resolved_subject': subject,
                'subject_changed': subject_changed,
            }

        directives, active_task, current_step, next_state = build_chat_directives(
            effective_transcript,
            history,
            tutoring_state,
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
            next_state = preserve_attempt_progress(tutoring_state, next_state)
            next_state = preserve_tutor_practice_context(tutoring_state, next_state)
        next_state = next_state.model_copy(update={'current_subject': subject})
        previous_structured_problem_id = tutoring_state.problem_id
        side_problem_active = bool(
            next_state.paused_main_problem.strip()
            and next_state.active_problem.strip()
            and next_state.active_problem.strip() != next_state.paused_main_problem.strip()
            and next_state.mode == 'solve'
            and next_state.status == 'solving'
        )
        if word_problem.accepted and not side_problem_active:
            next_state = next_state.model_copy(update={
                'pending_input_kind': '',
                'pending_new_problem': '',
                'mode': 'solve',
                'status': 'solving',
            })
            next_state = update_multi_step_progress(effective_transcript, next_state)
        elif next_state.mode != 'clarify_new_problem' and not side_problem_active:
            if not _is_locked_student_arithmetic_state(tutoring_state):
                next_state = update_multi_step_progress(effective_transcript, next_state)
        word_problem_started = bool(
            word_problem.accepted
            and (
                tutoring_state.word_problem_schema.get('original_text') != word_problem.original_text
                or not tutoring_state.active_task_id
                or tutoring_state.problem_status in {'finished', 'idle'}
            )
        )
        if word_problem_started and not side_problem_active:
            next_state = apply_word_problem_state(tutoring_state, next_state, word_problem)
        student_arithmetic_started = bool(
            student_arithmetic_task.accepted
            and not side_problem_active
            and not word_problem_started
            and (
                not tutoring_state.active_task_id
                or tutoring_state.problem_status in {'finished', 'idle'}
                or (
                    _is_tutor_practice_question_state(tutoring_state)
                    and intent_assist.label in {'new_problem', 'switch_request'}
                )
            )
        )
        if student_arithmetic_started:
            next_state = apply_student_arithmetic_state(tutoring_state, next_state, student_arithmetic_task)
        next_state = align_tutor_practice_transition(tutoring_state, next_state)
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
            next_state = preserve_attempt_progress(tutoring_state, next_state).model_copy(update={
                'student_answer': transcript,
                'correctness_status': '',
            })
        if student_arithmetic_started and not matched_structured_step:
            formatted_reply = build_student_arithmetic_start_reply(student_arithmetic_task)
            final_state = next_state
            result_provider = 'local'
            result_model = f'deterministic-{student_arithmetic_task.question_type}-start'
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
                    logger.warning('Voice chat history save failed after student arithmetic start: %s', exc)
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
                'resolved_subject': subject,
                'subject_changed': subject_changed,
            }
        answer_check = None
        if (
            subject == 'Math'
            and _is_locked_student_arithmetic_state(next_state)
            and intent_assist.label == 'answer_current_step'
        ):
            next_state = ensure_answer_attempt_registered(tutoring_state, next_state)
        if _should_run_answer_evaluation(
            next_state,
            tutoring_state,
            current_step,
            intent_assist.label,
        ):
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
        recent_history = '\n'.join([f'{_history_role(item)}: {_history_content(item)}' for item in history[-4:]])
        state_summary = (
            f"Mode: {next_state.mode}; "
            f"Attempt count: {next_state.attempt_count}; "
            f"Correctness: {next_state.correctness_status or 'not checked'}; "
            f"Memory: {next_state.memory_note or 'none'}"
        )
        user = f"Recent chat:\n{recent_history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or effective_transcript}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {transcript}\n\nNormalized math if useful: {effective_transcript}\n\nRespond as Ms. Alisia using the required tutoring method."
        structured_progression = has_structured_math_problem(next_state) and subject == 'Math'
        action_intent = detect_action_intent(effective_transcript)
        emotional_choice = detect_emotional_support_choice(transcript, tutoring_state)
        opening_starter_override = _should_override_opening_with_tutor_practice(tutoring_state, intent_assist.label, intent_assist.emotion)
        special_local_reply = False
        if subject_changed:
            final_state = tutoring_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'mode': 'solve',
                'status': 'idle',
                'memory_note': f'Started a fresh {subject} subject session.',
            })
            formatted_reply = build_subject_switch_reply(subject)
            result_provider = 'local'
            result_model = 'deterministic-voice-subject-switch'
            special_local_reply = True
        elif tutoring_state.emotional_support_mode == 'safety':
            final_state = preserve_attempt_progress(tutoring_state, tutoring_state.model_copy(update={
                'student_answer': transcript,
                'correctness_status': '',
                'mode': 'safety_support',
                'status': 'waiting_for_trusted_adult',
            }))
            formatted_reply = build_safety_followup_reply()
            result_provider = 'local'
            result_model = 'deterministic-voice-safety-support-lock'
            special_local_reply = True
        elif is_tutor_practice_answer_like(tutoring_state, effective_transcript):
            practice_state = ensure_answer_attempt_registered(tutoring_state, tutoring_state).model_copy(update={
                'current_subject': subject,
            })
            formatted_reply, final_state = _tutor_practice_answer_reply(
                practice_state,
                effective_transcript,
                answer_check,
                action_intent,
            )
            final_state = sync_active_task(final_state)
            result_provider = 'local'
            result_model = 'deterministic-voice-tutor-math-practice-check'
            special_local_reply = True
        elif intent_assist.needs_clarification:
            final_state = preserve_attempt_progress(tutoring_state, tutoring_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': '',
            }))
            formatted_reply = intent_assist.clarification_question
            result_provider = 'local'
            result_model = 'deterministic-voice-semantic-clarification'
            special_local_reply = True
        elif intent_assist.label == 'emotion' and not opening_starter_override:
            emotion_plan = build_emotional_support_plan(tutoring_state, transcript, intent_assist.emotion)
            final_state = apply_emotional_support(tutoring_state, transcript, emotion_plan)
            formatted_reply = build_emotional_support_reply(emotion_plan, final_state)
            result_provider = 'local'
            result_model = 'deterministic-voice-emotional-support'
            special_local_reply = True
        elif emotional_choice:
            final_state = resolve_emotional_support_choice(tutoring_state, emotional_choice)
            formatted_reply = build_emotional_choice_reply(final_state, emotional_choice)
            result_provider = 'local'
            result_model = f'deterministic-voice-emotional-choice-{emotional_choice}'
            special_local_reply = True
        elif intent_assist.label in {'greeting', 'acknowledge', 'continue_current'}:
            final_state = preserve_attempt_progress(tutoring_state, tutoring_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': '',
            }))
            formatted_reply = build_conversation_control_reply(
                final_state,
                intent_assist.label,
                student.name,
            )
            result_provider = 'local'
            result_model = f'deterministic-voice-conversation-{intent_assist.label}'
            special_local_reply = True
        elif intent_assist.label == 'topic_switch' and subject == 'Math':
            lesson = topic_lesson(intent_assist.requested_topic)
            if lesson:
                final_state = apply_topic_lesson_state(tutoring_state, transcript, lesson)
                formatted_reply = build_topic_lesson_intro(lesson)
            else:
                final_state = preserve_attempt_progress(tutoring_state, tutoring_state.model_copy(update={
                    'current_subject': subject,
                    'student_answer': transcript,
                    'correctness_status': '',
                    'skill': intent_assist.requested_topic,
                    'problem_status': 'idle',
                    'mode': 'solve',
                    'status': 'idle',
                    'memory_note': f'Student requested Math topic: {intent_assist.requested_topic}.',
                }))
                label = intent_assist.requested_topic or 'that Math topic'
                formatted_reply = (
                    f'Sure—we can move to {label}. The earlier practice question will not count against you.\n\n'
                    f'Send me your {label} question, or say **give me a {label} question**.'
                )
            result_provider = 'local'
            result_model = 'deterministic-voice-math-topic-switch'
            special_local_reply = True
        elif intent_assist.label == 'pause':
            final_state = pause_active_task(tutoring_state).model_copy(update={'mode': 'paused', 'status': 'paused'})
            formatted_reply = 'Of course. Your problem and exact step are saved. Come back when you are ready.'
            result_provider = 'local'
            result_model = 'deterministic-voice-student-pause'
            special_local_reply = True
        elif _is_tutor_practice_question_state(tutoring_state) and intent_assist.label in {'help_request', 'related_question'}:
            formatted_reply, final_state = build_tutor_practice_support_reply(
                tutoring_state,
                transcript,
                action_intent,
            )
            result_provider = 'local'
            result_model = 'deterministic-voice-tutor-math-practice-support'
            special_local_reply = True
        elif (
            subject == 'Math'
            and intent_assist.label == 'help_request'
            and bool(next_state.current_question or next_state.current_step or next_state.active_problem)
        ):
            formatted_reply, final_state, hint_model, _ = await build_progressive_hint_reply_with_fallback(next_state, help_request=True)
            result_provider = 'local'
            result_model = 'strict-llm-voice-progressive-hint' if hint_model == 'strict-llm-progressive-hint' else 'deterministic-voice-progressive-hint'
            special_local_reply = True
        elif (
            _is_tutor_practice_question_state(tutoring_state)
            and (
                intent_assist.label == 'answer_current_step'
                or is_tutor_practice_answer_like(tutoring_state, effective_transcript)
            )
        ):
            practice_state = ensure_answer_attempt_registered(tutoring_state, tutoring_state).model_copy(update={
                'current_subject': subject,
            })
            formatted_reply, final_state = _tutor_practice_answer_reply(
                practice_state,
                effective_transcript,
                answer_check,
                action_intent,
            )
            result_provider = 'local'
            result_model = 'deterministic-voice-tutor-math-practice-check'
            special_local_reply = True
        elif next_state.mode == 'resume_paused_problem_notice':
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
        elif word_problem_candidate and not word_problem.accepted:
            final_state = align_tutor_practice_transition(tutoring_state, tutoring_state.model_copy(update={
                'current_subject': 'Math',
                'student_answer': transcript,
                'pending_input_kind': 'ambiguous_word_problem',
                'pending_new_problem': transcript,
                'mode': 'clarify_word_problem',
                'status': 'waiting_for_student',
                'problem_status': 'idle',
            }))
            formatted_reply = build_word_problem_clarification_reply(word_problem)
            result_provider = 'local'
            result_model = 'deterministic-voice-word-problem-clarification'
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
            and not extract_math_expression(next_state.active_problem)
        ):
            final_state = next_state.model_copy(update={
                'current_subject': subject,
                'active_problem': next_state.paused_main_problem,
                'current_step': next_state.paused_current_step or next_state.current_step,
                'current_question': next_state.paused_current_question or next_state.current_question or next_state.paused_current_step,
                'expected_answer': next_state.paused_expected_answer or next_state.expected_answer,
                'student_answer': transcript,
                'correctness_status': '',
                'attempt_count': 0,
                'hint_given': False,
                'mode': 'practice' if (next_state.paused_current_question or next_state.paused_current_step or next_state.current_question or next_state.current_step) else 'solve',
                'status': 'waiting_for_student',
                'paused_main_problem': '',
                'paused_current_step': '',
                'paused_current_question': '',
                'paused_expected_answer': '',
                'paused_completed_steps': [],
            })
            formatted_reply = build_subject_boundary_reply(subject, final_state)
            result_provider = 'local'
            result_model = 'deterministic-subject-boundary-temporary-guard'
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
            formatted_reply = build_temporary_math_problem_reply(next_state.active_problem) or build_switch_confirmation_reply(next_state, next_state.active_problem)
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
            result_provider = 'local'
            result_model = 'deterministic-temporary-math-problem-return'
            special_local_reply = True
        elif word_problem_started and not has_structured_math_problem(next_state):
            final_state = next_state
            formatted_reply = build_word_problem_start_reply(word_problem)
            result_provider = 'local'
            result_model = 'deterministic-voice-structured-word-problem'
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
            special_local_reply = True
        elif structured_progression and answer_check and answer_check.is_wrong and next_state.attempt_count in {1, 2}:
            formatted_reply, final_state, hint_model, _ = await build_progressive_hint_reply_with_fallback(next_state, help_request=False)
            formatted_reply = prepend_attempt_feedback(formatted_reply, next_state, transcript)
            result_provider = 'local'
            result_model = 'strict-llm-structured-step-hint' if hint_model == 'strict-llm-progressive-hint' else f'deterministic-structured-step-hint-{next_state.attempt_count}'
            special_local_reply = True
        elif structured_progression and answer_check and answer_check.is_wrong and next_state.attempt_count >= 3:
            final_state = advance_structured_math_problem(next_state, answer_check.expected_answer or next_state.expected_answer)
            formatted_reply = build_structured_step_reply(next_state, final_state, reveal=True)
            result_provider = 'local'
            result_model = 'deterministic-structured-step-reveal'
            special_local_reply = True
        elif (
            answer_check
            and answer_check.is_correct
            and subject == 'Math'
            and _is_substep_of_active_problem(next_state, current_step)
        ):
            formatted_reply = _substep_correct_finish_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = 'deterministic-substep-completion'
            special_local_reply = True
        elif answer_check and answer_check.is_correct and subject == 'Math' and next_state.problem_kind == 'word_problem' and not next_state.ordered_steps:
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            final_state = _finish_single_step_word_problem(
                next_state,
                student_answer=transcript,
                correctness_status=answer_check.status,
                final_answer=final_answer,
            )
            result_provider = 'local'
            result_model = 'deterministic-voice-word-problem-completion'
            special_local_reply = True
        elif answer_check and answer_check.is_correct and subject == 'Math' and next_state.problem_kind == 'opening_arithmetic':
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            final_state = _finish_with_continuation_choice(
                next_state,
                student_answer=transcript,
                correctness_status='correct',
                final_answer=final_answer,
                origin_problem=next_state.current_question or next_state.active_problem,
                origin_type='opening_arithmetic',
                origin_explanation=f'{_display_math_expression_from_state(next_state, current_step)} = {final_answer}.',
                memory_note=f'Finished opening arithmetic problem: {next_state.current_question or next_state.active_problem}',
            )
            formatted_reply = f"{formatted_reply}\n\nWould you like another practice question?"
            result_provider = 'local'
            result_model = 'deterministic-voice-opening-mixed-math-completion'
            special_local_reply = True
        elif answer_check and answer_check.is_correct and subject == 'Math' and _is_locked_conceptual_math_state(next_state):
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            final_state = _finish_with_continuation_choice(
                next_state,
                student_answer=transcript,
                correctness_status='correct',
                final_answer=final_answer,
                origin_problem=next_state.current_question or next_state.active_problem,
                origin_type=next_state.problem_kind,
                origin_explanation=f'The correct answer to {next_state.current_question or next_state.active_problem} is {final_answer}.',
                memory_note=f'Finished conceptual Math problem: {next_state.current_question or next_state.active_problem}',
            )
            formatted_reply = f"{formatted_reply}\n\nWould you like another practice question?"
            result_provider = 'local'
            result_model = 'deterministic-voice-conceptual-math-completion'
            special_local_reply = True
        elif answer_check and answer_check.is_correct and subject == 'Math' and _is_locked_student_arithmetic_state(next_state):
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            final_state = _finish_with_continuation_choice(
                next_state,
                student_answer=transcript,
                correctness_status='correct',
                final_answer=final_answer,
                origin_problem=next_state.current_question or next_state.active_problem,
                origin_type=next_state.problem_kind,
                origin_explanation=f'{_display_math_expression_from_state(next_state, current_step)} = {final_answer}.',
                memory_note=f'Finished student arithmetic problem: {next_state.current_question or next_state.active_problem}',
            )
            formatted_reply = f"{formatted_reply}\n\nWould you like another practice question?"
            result_provider = 'local'
            result_model = 'deterministic-voice-student-arithmetic-completion'
            special_local_reply = True
        elif answer_check and answer_check.is_correct and subject == 'Math':
            formatted_reply = _correct_math_answer_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = 'deterministic-current-math-check'
            special_local_reply = True
        elif (
            answer_check
            and answer_check.is_wrong
            and subject == 'Math'
            and next_state.attempt_count in {1, 2}
        ):
            formatted_reply, final_state, hint_model, _ = await build_progressive_hint_reply_with_fallback(next_state, help_request=False)
            formatted_reply = prepend_attempt_feedback(formatted_reply, next_state, transcript)
            result_provider = 'local'
            result_model = 'strict-llm-progressive-attempt-hint' if hint_model == 'strict-llm-progressive-hint' else f'deterministic-progressive-attempt-hint-{next_state.attempt_count}'
            special_local_reply = True
        elif answer_check and subject != 'Math' and (answer_check.expected_answer or answer_check.feedback_note or answer_check.status in {'correct', 'incorrect', 'partially_correct'}):
            formatted_reply = _text_answer_check_reply(answer_check, next_state, current_step)
            result_provider = 'local'
            result_model = f'deterministic-{subject.lower()}-text-check'
            special_local_reply = True
        elif (
            answer_check
            and answer_check.is_wrong
            and subject == 'Math'
            and next_state.attempt_count >= 3
            and next_state.problem_kind == 'word_problem'
            and not next_state.ordered_steps
        ):
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = _word_problem_reveal_reply(answer_check, next_state, current_step)
            final_state = _finish_single_step_word_problem(
                next_state,
                student_answer=transcript,
                correctness_status=answer_check.status,
                final_answer=final_answer,
                revealed=True,
            )
            result_provider = 'local'
            result_model = 'deterministic-voice-word-problem-reveal'
            special_local_reply = True
        elif (
            answer_check
            and answer_check.is_wrong
            and subject == 'Math'
            and next_state.attempt_count >= 3
            and _is_locked_student_arithmetic_state(next_state)
        ):
            final_answer = answer_check.expected_answer or next_state.expected_answer
            formatted_reply = (
                "Nice effort. Let's finish this one together.\n\n"
                f"{_display_math_expression_from_state(next_state, current_step)} = {final_answer}.\n\n"
                f"**Final answer:** {final_answer}.\n\n"
                "Would you like another practice question?"
            )
            final_state = _finish_with_continuation_choice(
                next_state,
                student_answer=transcript,
                correctness_status=answer_check.status,
                final_answer=final_answer,
                origin_problem=next_state.current_question or next_state.active_problem,
                origin_type=next_state.problem_kind,
                origin_explanation=f'{_display_math_expression_from_state(next_state, current_step)} = {final_answer}.',
                revealed=True,
                memory_note=f'Revealed student arithmetic problem: {next_state.current_question or next_state.active_problem}',
            )
            result_provider = 'local'
            result_model = 'deterministic-voice-student-arithmetic-reveal'
            special_local_reply = True
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
            special_local_reply = True
        elif subject == 'Math' and (
            _has_active_student_math_flow(next_state)
            or next_state.problem_status == 'finished'
            or next_state.mode == 'awaiting_more_practice_choice'
        ):
            final_state = preserve_attempt_progress(tutoring_state, next_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': '',
            }))
            formatted_reply = _math_fallback_reply(final_state)
            result_provider = 'local'
            result_model = 'deterministic-voice-math-fallback-tight'
            special_local_reply = True
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
        formatted_reply = ensure_contextual_final_answer(formatted_reply, next_state)
        math_response_guard = TutorMathResponseGuard()
        math_guard_result = None
        if subject == 'Math':
            guard_state = final_state if special_local_reply else next_state
            math_guard_result = math_response_guard.validate(
                formatted_reply,
                guard_state,
                intent_label=intent_assist.label,
                source=result_model,
            )
            formatted_reply = math_guard_result.text
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
        if (
            intent_assist.label in {'greeting', 'acknowledge', 'continue_current', 'related_question', 'help_request', 'meta_feedback'}
            and result_model != 'deterministic-voice-tutor-math-practice-check'
        ):
            final_state = preserve_tutor_practice_context(tutoring_state, final_state)
        if math_guard_result is not None:
            final_state = math_response_guard.apply_metadata(final_state, math_guard_result, result_model)
        final_state = reconcile_task_lifecycle(final_state)

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
            'resolved_subject': subject,
            'subject_changed': subject_changed,
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
