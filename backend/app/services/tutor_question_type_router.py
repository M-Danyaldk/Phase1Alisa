from __future__ import annotations

import re

from ..assessment_validation import extract_math_expression, normalize_math_text
from ..models import TutoringState


def infer_active_question_type(state: TutoringState) -> str:
    if state.mode == 'awaiting_more_practice_choice' and state.status == 'waiting_for_student':
        return 'continuation_choice'
    if state.emotional_support_mode or state.mode in {'emotional_checkin', 'safety_support'}:
        return 'emotion_support'
    if state.helper_branch.status == 'active' and state.helper_branch.question.strip():
        return 'side_question'
    if state.problem_kind == 'word_problem':
        return 'word_problem'

    skill_text = ' '.join([
        str(state.skill or ''),
        str(state.tutor_practice_topic or ''),
    ]).lower()
    prompt_text = ' '.join([
        str(state.current_question or ''),
        str(state.current_step or ''),
        str(state.active_problem or ''),
    ]).strip()
    lowered_prompt = prompt_text.lower()

    if _is_fraction_comparison(skill_text, prompt_text):
        return 'fraction_comparison'
    if _is_equivalent_fraction(skill_text, prompt_text):
        return 'equivalent_fraction'

    expression = _extract_active_expression(state)
    if expression:
        return 'arithmetic_multi_step' if _looks_multi_step(expression) else 'arithmetic_single_step'

    if _looks_word_problem(prompt_text):
        return 'word_problem'

    conceptual_markers = (
        'which is larger',
        'which is greater',
        'numerator',
        'denominator',
        'fraction',
        'decimal',
        'equation',
        'expression',
        'ratio',
        'percent',
        'perimeter',
        'area',
        'volume',
        'unit rate',
        'whole',
    )
    if any(marker in skill_text for marker in conceptual_markers):
        return 'conceptual_math'
    if any(marker in lowered_prompt for marker in conceptual_markers):
        return 'conceptual_math'

    return 'unknown'


def _is_fraction_comparison(skill_text: str, prompt_text: str) -> bool:
    if 'fraction comparison' in skill_text or 'decimal comparison' in skill_text:
        return True
    prompt = prompt_text.lower()
    fractions = re.findall(r'-?\d+\s*/\s*-?\d+', prompt)
    return len(fractions) >= 2 and any(marker in prompt for marker in ('which is larger', 'which is greater', 'compare'))


def _is_equivalent_fraction(skill_text: str, prompt_text: str) -> bool:
    if 'equivalent fraction' in skill_text or 'equivalent fractions' in skill_text:
        return True
    prompt = prompt_text.lower()
    return 'equivalent' in prompt and 'fraction' in prompt


def _looks_multi_step(expression: str) -> bool:
    compact = expression.replace(' ', '')
    operator_count = 0
    for index, character in enumerate(compact):
        if character in {'+', '*'}:
            operator_count += 1
            continue
        if character == '-' and index > 0 and compact[index - 1] not in '+-*/(':
            operator_count += 1
    return operator_count >= 2 or ('(' in compact and ')' in compact)


def _looks_word_problem(prompt_text: str) -> bool:
    lowered = prompt_text.lower()
    if len(re.findall(r'\d+(?:\.\d+)?', lowered)) < 2:
        return False
    return any(marker in lowered for marker in (
        'there are',
        'there were',
        'each',
        'altogether',
        'in total',
        'how many',
        'how much',
        'left',
        'remain',
        'needed',
        'shared',
    ))


def _extract_active_expression(state: TutoringState) -> str:
    seen: set[str] = set()
    for raw_text in (
        state.current_question,
        state.current_step,
        state.active_problem,
    ):
        text = str(raw_text or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        expression = extract_math_expression(normalize_math_text(text))
        if expression:
            return expression
    return ''
