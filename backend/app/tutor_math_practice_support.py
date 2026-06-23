from __future__ import annotations

import re

from .assessment_validation import extract_numeric_value
from .models import TutoringState
from .services.tutor_progressive_hints import current_step_support, record_step_hint


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
    expected_value = extract_numeric_value(expected)
    answer_value = extract_numeric_value(text)
    if expected_value is not None and answer_value is not None and _looks_like_short_numeric_response(text):
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
    expected_value = extract_numeric_value(expected)
    answer_value = extract_numeric_value(text)
    if (
        expected_value is not None
        and answer_value is not None
        and _looks_like_short_numeric_response(text)
        and expected_value == answer_value
    ):
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
    fraction_context = _fraction_context(state)

    progressive_help = (
        action_intent in {'hint', 'explain_again'}
        or text in {'hint', 'give me a hint'}
        or 'hint' in text
        or 'understand' in text
        or 'stuck' in text
    )

    if progressive_help:
        support = current_step_support(state)
        level = min(3, support.help_level + 1)
        if level == 1:
            hint_id = 'concept'
            hint = state.tutor_practice_hint_1 or 'Look at the important numbers and identify the operation.'
        elif level == 2:
            hint_id = 'strategy'
            hint = state.tutor_practice_hint_2 or state.tutor_practice_hint_1 or 'Break the calculation into one smaller part.'
        else:
            hint_id = 'worked_substep'
            hint = state.tutor_practice_explanation or state.tutor_practice_hint_2 or 'Let’s work one small part of this step together.'
        hint_given = True
        reply = (
            f"Here is {'the first' if level == 1 else 'a stronger' if level == 2 else 'one worked'} hint.\n\n"
            f"{hint}\n\n"
            f"Now try this same question:\n\n{question}"
        )
    elif 'denominator' in text and _looks_fraction_topic(state):
        reply = (
            "The denominator is the bottom number in a fraction.\n\n"
            f"It tells how many equal parts make the whole. {fraction_context['denominator_sentence']}\n\n"
            f"Now try the same question:\n\n{question}"
        )
    elif 'numerator' in text and _looks_fraction_topic(state):
        reply = (
            "The numerator is the top number in a fraction.\n\n"
            f"It tells how many parts we are talking about. {fraction_context['numerator_sentence']}\n\n"
            f"Now try the same question:\n\n{question}"
        )
    elif _asks_fraction_definition(text) and _looks_fraction_topic(state):
        reply = (
            "A fraction shows part of a whole or part of a group.\n\n"
            "The top number tells how many parts we have, and the bottom number tells how many equal parts make the whole. "
            f"{fraction_context['fraction_sentence']}\n\n"
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
    if progressive_help:
        next_state = record_step_hint(next_state, level, hint_id)
    return reply, next_state


def _looks_fraction_topic(state: TutoringState) -> bool:
    joined = ' '.join([
        state.skill,
        state.tutor_practice_topic,
        state.current_question,
        state.active_problem,
    ]).lower()
    return 'fraction' in joined or '/' in joined


def _asks_fraction_definition(text: str) -> bool:
    if 'fraction' not in text and 'fractions' not in text:
        return False
    return bool(re.search(r'\b(what is|what are|what does|what means|define|meaning of)\b', text))


def _fraction_context(state: TutoringState) -> dict[str, str]:
    joined = ' '.join([
        state.current_question,
        state.current_step,
        state.active_problem,
        state.expected_answer,
    ])
    fractions = _fraction_parts(joined)
    if fractions:
        numerators = [num for num, _den in fractions]
        denominators = [den for _num, den in fractions]
        return {
            'numerator_sentence': f"In this question, {_value_phrase('the numerator', 'the numerators', numerators)}.",
            'denominator_sentence': f"In this question, {_value_phrase('the denominator', 'the denominators', denominators)}.",
            'fraction_sentence': f"Here, the fraction parts are {_fraction_parts_phrase(fractions)}.",
        }

    out_of_match = re.search(r'\b(-?\d+)\s+parts?\s+out\s+of\s+(-?\d+)\s+equal\s+parts?\b', joined, flags=re.IGNORECASE)
    if out_of_match:
        numerator, denominator = out_of_match.groups()
        return {
            'numerator_sentence': f"In this question, the numerator is {numerator}.",
            'denominator_sentence': f"In this question, the denominator is {denominator}.",
            'fraction_sentence': f"Here, {numerator}/{denominator} means {numerator} part out of {denominator} equal parts.",
        }

    return {
        'numerator_sentence': 'In your question, look above the fraction bar to find it.',
        'denominator_sentence': 'In your question, look below the fraction bar to find it.',
        'fraction_sentence': 'Look for the top and bottom numbers around the fraction bar in this question.',
    }


def _fraction_parts(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for match in re.finditer(r'(?<!\d)(-?\d+)\s*/\s*(-?\d+)(?!\d)', str(text or '')):
        numerator, denominator = match.groups()
        if denominator != '0':
            parts.append((numerator, denominator))
    return parts


def _value_phrase(single_label: str, plural_label: str, values: list[str]) -> str:
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) == 1:
        return f'{single_label} is {unique_values[0]}'
    return f"{plural_label} are {_join_values(unique_values)}"


def _fraction_parts_phrase(fractions: list[tuple[str, str]]) -> str:
    unique = list(dict.fromkeys([f'{num}/{den}' for num, den in fractions]))
    return _join_values(unique)


def _join_values(values: list[str]) -> str:
    if len(values) <= 1:
        return values[0] if values else ''
    if len(values) == 2:
        return f'{values[0]} and {values[1]}'
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _looks_like_short_numeric_response(text: str) -> bool:
    compact = ' '.join(str(text or '').lower().split())
    if not compact or len(compact) > 40 or '?' in compact:
        return False
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?(?:/\d+)?', compact):
        return True
    if re.fullmatch(r'[-+]?\d+\s*:\s*[-+]?\d+', compact):
        return True
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?%?', compact):
        return True
    return bool(re.fullmatch(r'(?:negative|minus)?\s*[a-z-]+(?:\s+[a-z-]+){0,3}', compact))
