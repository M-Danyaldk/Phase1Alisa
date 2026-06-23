import re
from collections.abc import Callable

from ..assessment_validation import extract_math_expression
from ..models import ChatHistoryItem, TutoringState
from ..services.tutor_answer_attempt_feedback import prepend_attempt_feedback
from ..services.tutor_answer_checker import TutorAnswerChecker
from ..services.tutor_progressive_hints import build_progressive_hint_reply
from ..tutor_math_practice_bank import TutorMathPracticeQuestion
from ..tutor_math_practice_support import student_matches_expected_practice_answer
from ..tutoring_logic import detect_definition_intent
from ..utils.task_lifecycle import complete_active_task, transition_to_task
from ..utils.tutor_flow_alignment import build_aligned_tutor_practice_state
from ..utils.tutor_response import contextual_unit_feedback, format_contextual_math_answer


def should_start_tutor_math_practice(
    subject: str,
    state: TutoringState,
    history: list[ChatHistoryItem] | list,
    effective_message: str,
) -> bool:
    if subject != 'Math':
        return False
    if extract_math_expression(effective_message):
        return False
    if has_active_student_math_flow(state):
        return False
    if state.status not in {'', 'idle', 'ready_for_mini_checkin'} and state.mode != 'opening_checkin':
        return False
    if state.mode not in {'', 'solve', 'opening_checkin'}:
        return False
    student_text = ' '.join(str(effective_message or '').lower().split())
    if not student_text:
        return False
    if any(marker in student_text for marker in ('homework', 'worksheet', 'upload', 'photo', 'explain', 'help me with', 'solve')):
        return False
    return history_has_opening_math_prompt(history) or state.mode == 'opening_checkin' or state.status == 'ready_for_mini_checkin'


def has_active_student_math_flow(state: TutoringState) -> bool:
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


def tutor_practice_choice_intent(
    state: TutoringState,
    effective_message: str,
    intent_label: str = '',
) -> str:
    if state.mode != 'awaiting_more_practice_choice' or state.status != 'waiting_for_student':
        return ''
    if intent_label == 'continuation_yes':
        return 'yes'
    if intent_label == 'continuation_no':
        return 'no'
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
    if any(choice_marker_matches(text, marker) for marker in no_markers):
        return 'no'
    if any(choice_marker_matches(text, marker) for marker in yes_markers):
        return 'yes'
    return 'unclear'


def continuation_choice_intent(
    state: TutoringState,
    effective_message: str,
    intent_label: str = '',
) -> str:
    if state.mode != 'awaiting_more_practice_choice' or state.status != 'waiting_for_student':
        return ''
    if intent_label == 'related_question' and not detect_definition_intent(effective_message):
        return 'explain'
    if intent_label == 'related_question' and detect_definition_intent(effective_message):
        return ''
    base_choice = tutor_practice_choice_intent(state, effective_message, intent_label)
    if base_choice in {'yes', 'no'}:
        return base_choice
    if extract_math_expression(effective_message) or intent_label in {'new_problem', 'switch_request', 'topic_switch'}:
        return ''
    text = ' '.join(str(effective_message or '').lower().split())
    if not text:
        return 'unclear'
    explanation_markers = (
        'explain',
        'why',
        'how',
        'what do you mean',
        'where did',
        'how did',
        'why is',
        'why was',
    )
    if any(text.startswith(marker) or f' {marker} ' in f' {text} ' for marker in explanation_markers):
        return 'explain'
    return base_choice or 'unclear'


def continuation_explanation_reply(state: TutoringState) -> str:
    explanation = str(state.continuation_origin_explanation or '').strip()
    problem = str(state.continuation_origin_problem or 'that problem').strip()
    answer = str(state.continuation_origin_answer or state.final_answer or '').strip()
    origin_type = str(state.continuation_origin_type or '').strip()
    if explanation:
        body = explanation
    elif origin_type == 'fraction_comparison' and ' or ' in problem:
        body = f'{problem} is solved by comparing which fraction is larger. The correct answer is {answer}.'
    elif origin_type == 'equivalent_fraction':
        body = f'{problem} is about finding the fraction with the same value. The correct answer is {answer}.'
    elif answer:
        body = f'{problem} = {answer}.'
    else:
        body = f"Let's look back at {problem} one step at a time."
    return (
        f"{body}\n\n"
        "Would you like another practice question, or a new Math problem?"
    )


def math_fallback_reply(state: TutoringState) -> str:
    question = str(state.current_question or state.current_step or '').strip()
    problem = str(state.active_problem or state.main_problem or '').strip()
    if state.mode == 'awaiting_more_practice_choice' or (
        state.problem_status == 'finished'
        and not question
        and not problem
    ):
        return 'Would you like another practice question, a quick explanation of the last one, or a new Math problem?'
    if question:
        return (
            "Here is the saved step to try.\n\n"
            f'{question}'
        )
    if problem:
        return (
            "Here is the saved problem.\n\n"
            f'**Problem:** {problem}\n\n'
            'Send your next step or answer for this problem.'
        )
    return 'Send me the Math problem you want to work on, and I will help one step at a time.'


def finish_with_continuation_choice(
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
    finished_state = state.model_copy(update={
        'active_problem': '',
        'current_step': '',
        'current_question': '',
        'expected_answer': '',
        'student_answer': student_answer,
        'correctness_status': correctness_status,
        'answer_revealed': revealed,
        'final_answer': final_answer,
        'continuation_origin_problem': origin_problem,
        'continuation_origin_answer': final_answer,
        'continuation_origin_type': origin_type,
        'continuation_origin_explanation': origin_explanation,
        'problem_status': 'finished',
        'mode': 'awaiting_more_practice_choice',
        'status': 'waiting_for_student',
        'memory_note': memory_note,
    })
    return complete_active_task(finished_state)


def choice_marker_matches(text: str, marker: str) -> bool:
    if text == marker:
        return True
    return bool(re.search(rf'(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])', text))


def history_role(item: ChatHistoryItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get('role') or '')
    return str(getattr(item, 'role', '') or '')


def history_content(item: ChatHistoryItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get('content') or '')
    return str(getattr(item, 'content', '') or '')


def history_has_opening_math_prompt(history: list[ChatHistoryItem] | list) -> bool:
    if not history:
        return False
    last = history[-1]
    if history_role(last) != 'msalisia':
        return False
    text = ' '.join(history_content(last).lower().split())
    if not text:
        return False
    mood_markers = ('how are you', 'how are you doing', 'how are you feeling', 'before we start')
    quick_markers = ('quick math', 'quick thing', 'quick question', 'know how to help')
    return any(marker in text for marker in mood_markers) and any(marker in text for marker in quick_markers)


def tutor_math_starter_reply(
    question: TutorMathPracticeQuestion,
    display_question: Callable[[str], str],
    *,
    rich_text: bool,
    intro_text: str = '',
) -> str:
    label = '**Question:**' if rich_text else 'Question:'
    intro = str(intro_text or '').strip() or "That's good to hear. Let's start with one quick Math question."
    return (
        f"{intro}\n\n"
        f"{label} {display_question(question.question)}"
    )


def opening_math_starter_override(intent_label: str, emotion: str = '') -> bool:
    if intent_label in {'greeting', 'acknowledge'}:
        return True
    return intent_label == 'emotion' and emotion != 'crisis'


def opening_math_starter_intro(intent_label: str, emotion: str = '') -> str:
    if intent_label == 'emotion':
        gentle_emotions = {
            'tired',
            'frustrated',
            'upset',
            'sad',
            'nervous',
            'overwhelmed',
            'discouraged',
        }
        if emotion in gentle_emotions:
            return "Thanks for telling me. We can take this one step at a time. Let's start with one quick Math question."
        return "Thanks for telling me. Let's start with one quick Math question."
    if intent_label in {'greeting', 'acknowledge'}:
        return "Thanks for telling me. Let's start with one quick Math question."
    return ''


def tutor_math_next_practice_reply(question: TutorMathPracticeQuestion, display_question: Callable[[str], str], *, rich_text: bool) -> str:
    label = '**Question:**' if rich_text else 'Question:'
    return (
        "Sure. Try this one:\n\n"
        f"{label} {display_question(question.question)}"
    )


def tutor_math_question_state(
    state: TutoringState,
    subject: str,
    student_message: str,
    practice_question: TutorMathPracticeQuestion,
    *,
    source_label: str,
    source: str,
) -> TutoringState:
    recent_practice_ids = next_recent_tutor_practice_ids(
        state.recent_tutor_practice_question_ids,
        practice_question.id,
    )
    next_state = build_aligned_tutor_practice_state(
        state,
        subject=subject,
        student_message=student_message,
        practice_question=practice_question,
        recent_question_ids=recent_practice_ids,
        source_label=source_label,
    )
    return transition_to_task(
        state,
        next_state,
        practice_question.question,
        subject=subject,
        topic=practice_question.topic,
        source=source,
        previous='abandon',
    )


def is_tutor_practice_question_state(state: TutoringState) -> bool:
    return (
        state.problem_status == 'tutor_practice'
        and bool(state.current_question.strip())
        and bool(state.expected_answer.strip())
    )


def tutor_practice_answer_reply(
    state: TutoringState,
    student_answer: str,
    answer_check,
    action_intent: str,
    *,
    display_question: Callable[[str], str],
) -> tuple[str, TutoringState]:
    if action_intent == 'hint':
        hint = state.tutor_practice_hint_2 if state.hint_given and state.tutor_practice_hint_2 else state.tutor_practice_hint_1
        hint = hint or 'Try one small step and then check the numbers again.'
        reply = (
            "Sure. Here's one hint.\n\n"
            f"{hint}\n\n"
            f"Try this same question:\n{display_question(state.current_question)}"
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
    attempt_count = state.attempt_count if state.attempt_count > 0 else 1
    if local_check.is_correct or student_matches_expected_practice_answer(state, student_answer):
        expected = state.expected_answer or local_check.expected_answer
        explanation = state.tutor_practice_explanation or f'The answer is {expected}.'
        reply = (
            "Yes, that's correct!\n\n"
            f"{display_question(explanation)}\n\n"
            "Would you like another practice question?"
        )
        return reply, finished_tutor_practice_state(state, student_answer, 'correct', expected)

    if attempt_count in {1, 2}:
        guidance_state = state.model_copy(update={
            'student_answer': student_answer,
            'correctness_status': 'incorrect',
            'attempt_count': attempt_count,
            'answer_revealed': False,
            'status': 'waiting_for_student',
        })
        reply, next_state = build_progressive_hint_reply(guidance_state, help_request=False)
        return prepend_attempt_feedback(reply, guidance_state, student_answer), next_state

    expected = state.expected_answer or local_check.expected_answer
    explanation = state.tutor_practice_explanation or f'The answer is {expected}.'
    reveal_explanation = _ensure_explicit_expected_answer(explanation, expected)
    reply = (
        "Nice effort. Let's finish this one together.\n\n"
        f"{display_question(reveal_explanation)}\n\n"
        "Would you like another practice question?"
    )
    return reply, finished_tutor_practice_state(state, student_answer, 'incorrect', expected, revealed=True)


def _ensure_explicit_expected_answer(explanation: str, expected: str) -> str:
    clean_explanation = str(explanation or '').strip()
    clean_expected = str(expected or '').strip()
    if not clean_expected:
        return clean_explanation
    compact_explanation = re.sub(r'\s+', '', clean_explanation).lower()
    compact_expected = re.sub(r'\s+', '', clean_expected).lower()
    if compact_expected and compact_expected in compact_explanation:
        return clean_explanation
    if not clean_explanation:
        return f'The answer is {clean_expected}.'
    return f'The answer is {clean_expected}.\n\n{clean_explanation}'


def finished_tutor_practice_state(
    state: TutoringState,
    student_answer: str,
    correctness_status: str,
    expected_answer: str,
    *,
    revealed: bool = False,
) -> TutoringState:
    return finish_with_continuation_choice(
        state,
        student_answer=student_answer,
        correctness_status=correctness_status,
        final_answer=expected_answer,
        origin_problem=state.current_question or state.active_problem,
        origin_type='tutor_practice',
        origin_explanation=state.tutor_practice_explanation or f'The answer is {expected_answer}.',
        revealed=revealed,
        memory_note=f'Finished tutor practice question: {state.current_question}',
    )


def next_recent_tutor_practice_ids(previous_ids: list[str] | tuple[str, ...] | None, question_id: str) -> list[str]:
    clean_ids = [str(item) for item in (previous_ids or ()) if str(item).strip() and str(item) != question_id]
    clean_ids.append(question_id)
    return clean_ids[-10:]


def correct_math_answer_reply(
    answer_check,
    state: TutoringState,
    current_step: str,
    *,
    display_expression: Callable[[TutoringState, str], str],
) -> str:
    expected = answer_check.expected_answer or state.expected_answer or 'that answer'
    expected_display = format_contextual_math_answer(state, expected)
    expression = display_expression(state, current_step)
    unit_note = contextual_unit_feedback(state, state.student_answer)
    unit_line = f'\n\n{unit_note}' if unit_note else ''
    if expression:
        return f"Yes, that's correct!\n\n{expression} = {expected_display}.{unit_line}\n\nNice work. Let's keep going one small step at a time."
    return f"Yes, that's correct!\n\nThe answer is {expected_display}.{unit_line}\n\nNice work. Let's keep going one small step at a time."


def text_answer_check_reply(answer_check, state: TutoringState, current_step: str = '') -> str:
    prompt = clean_text_retry_prompt(state.current_question or current_step or state.current_step or 'that question')
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


def clean_text_retry_prompt(prompt: str) -> str:
    cleaned = str(prompt or '').strip()
    if 'finish this sentence' in cleaned.lower():
        stem_match = re.search(r'["â€œ]([^"â€]*\.{3}[^"â€]*)["â€]', cleaned)
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
