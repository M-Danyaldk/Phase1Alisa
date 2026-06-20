from __future__ import annotations

import re

from .models import TutoringState


def is_tutor_practice_answer_like(state: TutoringState, student_message: str) -> bool:
    if state.mode != 'tutor_practice_question' or state.problem_status != 'tutor_practice':
        return False
    text = ' '.join(str(student_message or '').strip().lower().split())
    expected = ' '.join(str(state.expected_answer or '').strip().lower().split())
    if not text or not expected:
        return False
    if '?' in text or len(text) > 80:
        return False
    if text == expected:
        return True
    if expected.endswith('%') and text in {expected[:-1].strip(), expected.replace('%', ' percent')}:
        return True
    if ':' in expected and text.replace(' ', '') == expected.replace(' ', ''):
        return True
    compact_text = text.replace(' ', '')
    compact_expected = expected.replace(' ', '')
    if compact_text == compact_expected:
        return True
    answer_like_pattern = r'[-+]?\d+(?:\.\d+)?(?:/\d+)?|[-+]?\d+\s*:\s*[-+]?\d+|[-+]?\d+(?:\.\d+)?%?'
    if re.fullmatch(answer_like_pattern, text):
        return True
    if expected in {'yes', 'no'} and text in {'yes', 'no', 'y', 'n'}:
        return True
    if len(text.split()) <= 3 and expected.replace(' ', '') in text.replace(' ', ''):
        return True
    return False


def student_matches_expected_practice_answer(state: TutoringState, student_message: str) -> bool:
    text = ' '.join(str(student_message or '').strip().lower().split())
    expected = ' '.join(str(state.expected_answer or '').strip().lower().split())
    if not text or not expected:
        return False
    if text == expected or text.replace(' ', '') == expected.replace(' ', ''):
        return True
    if expected.endswith('%') and text in {expected[:-1].strip(), expected.replace('%', ' percent')}:
        return True
    if expected in {'yes', 'no'}:
        return (expected == 'yes' and text in {'yes', 'y', 'yeah', 'yep'}) or (
            expected == 'no' and text in {'no', 'n', 'nope'}
        )
    return False


def build_tutor_practice_support_reply(state: TutoringState, student_message: str, action_intent: str = '') -> tuple[str, TutoringState]:
    question = state.current_question or state.current_step or state.active_problem
    text = ' '.join(str(student_message or '').lower().split())
    hint_given = state.hint_given

    if action_intent == 'hint' or text in {'hint', 'give me a hint'} or 'hint' in text:
        hint = state.tutor_practice_hint_2 if state.hint_given and state.tutor_practice_hint_2 else state.tutor_practice_hint_1
        hint = hint or 'Look at the important numbers and try one small step.'
        hint_given = True
        reply = (
            "Sure - here's one hint.\n\n"
            f"{hint}\n\n"
            f"Now try this same question:\n\n{question}"
        )
    elif 'denominator' in text and _looks_fraction_topic(state):
        reply = (
            "The denominator is the bottom number in a fraction.\n\n"
            "It tells how many equal parts make the whole. In this question, the whole has 4 equal parts.\n\n"
            f"Now try the same question:\n\n{question}"
        )
    elif 'numerator' in text and _looks_fraction_topic(state):
        reply = (
            "The numerator is the top number in a fraction.\n\n"
            "It tells how many parts we are talking about. In this question, we are talking about 1 part.\n\n"
            f"Now try the same question:\n\n{question}"
        )
    elif 'example' in text:
        reply = (
            "Here's a quick example.\n\n"
            "If something is split into 3 equal parts and we use 1 part, we write 1/3.\n\n"
            f"Now try your question:\n\n{question}"
        )
    else:
        hint = state.tutor_practice_hint_1 or 'Start by naming what the question is asking for.'
        reply = (
            "Let's look at it another way.\n\n"
            f"{hint}\n\n"
            f"Now try this same question:\n\n{question}"
        )

    next_state = state.model_copy(update={
        'student_answer': student_message,
        'correctness_status': '',
        'hint_given': hint_given,
        'status': 'waiting_for_student',
        'mode': 'tutor_practice_question',
        'problem_status': 'tutor_practice',
    })
    return reply, next_state


def _looks_fraction_topic(state: TutoringState) -> bool:
    joined = ' '.join([
        state.skill,
        state.tutor_practice_topic,
        state.current_question,
        state.active_problem,
    ]).lower()
    return 'fraction' in joined or '/' in joined
