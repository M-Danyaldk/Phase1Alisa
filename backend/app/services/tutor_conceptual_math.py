from __future__ import annotations

import hashlib
import re
from fractions import Fraction

from pydantic import BaseModel, Field

from ..models import TutoringState
from ..utils.task_lifecycle import transition_to_task


class ConceptualMathTask(BaseModel):
    accepted: bool = False
    original_text: str = ''
    question_type: str = ''
    expected_answer: str = ''
    choices: list[str] = Field(default_factory=list)
    skill: str = ''
    explanation_seed: str = ''


def parse_conceptual_math_task(message: str) -> ConceptualMathTask:
    text = ' '.join(str(message or '').strip().split())
    if not text:
        return ConceptualMathTask()

    comparison = _parse_comparison(text)
    if comparison.accepted:
        return comparison

    equivalent = _parse_equivalent_fraction(text)
    if equivalent.accepted:
        return equivalent

    return ConceptualMathTask()


def apply_conceptual_math_state(
    previous_state: TutoringState,
    current_state: TutoringState,
    task: ConceptualMathTask,
) -> TutoringState:
    if not task.accepted:
        return current_state

    problem_id = f'concept-{hashlib.sha1(task.original_text.lower().encode("utf-8")).hexdigest()[:12]}'
    next_state = current_state.model_copy(update={
        'problem_id': problem_id,
        'problem_kind': task.question_type,
        'word_problem_schema': {
            'question_type': task.question_type,
            'choices': task.choices,
            'expected_answer': task.expected_answer,
        },
        'main_problem': task.original_text,
        'full_problem': task.original_text,
        'active_problem': task.original_text,
        'ordered_steps': [],
        'current_step_index': 0,
        'current_step_id': '',
        'completed_steps': [],
        'current_expression': '',
        'remaining_steps': [],
        'completed_step_results': [],
        'step_results': {},
        'attempts_per_step': {},
        'support_per_step': {},
        'current_step': task.original_text,
        'current_question': task.original_text,
        'expected_answer': task.expected_answer,
        'answer_unit': '',
        'answer_label': 'answer',
        'display_answer': task.expected_answer,
        'student_answer': '',
        'correctness_status': '',
        'skill': task.skill,
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'helper_branch': current_state.helper_branch.model_copy(update={
            'branch_id': '',
            'branch_type': '',
            'question': '',
            'linked_step_id': '',
            'return_step_id': '',
            'status': 'idle',
        }),
        'queued_followup_questions': [],
        'pending_input_kind': '',
        'pending_new_problem': '',
        'return_step_index': 0,
        'return_step_id': '',
        'final_answer': '',
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
        'memory_note': f'We are working on {task.original_text}.',
    })
    return transition_to_task(
        previous_state,
        next_state,
        task.original_text,
        subject='Math',
        topic=task.skill,
        source='conceptual_math',
        previous='pause',
    )


def build_conceptual_math_start_reply(task: ConceptualMathTask) -> str:
    if task.question_type == 'fraction_comparison':
        left, right = _safe_pair(task.choices)
        left_parts = _fraction_parts(left)
        right_parts = _fraction_parts(right)
        if left_parts and right_parts and left_parts[1] == right_parts[1]:
            return (
                "Let's compare these one step at a time.\n\n"
                f"Both fractions have the same bottom number, {left_parts[1]}.\n"
                "So we compare the top numbers.\n\n"
                f"Which is larger: {left} or {right}?"
            )
        return (
            "Let's compare these one step at a time.\n\n"
            f"Look carefully at the two choices: {left} and {right}.\n"
            "Which one shows the larger amount?"
        )
    if task.question_type == 'decimal_comparison':
        left, right = _safe_pair(task.choices)
        return (
            "Let's compare these decimals one step at a time.\n\n"
            "Line up the place values, then compare from left to right.\n\n"
            f"Which is larger: {left} or {right}?"
        )
    if task.question_type == 'percent_comparison':
        left, right = _safe_pair(task.choices)
        return (
            "Let's compare these percents one step at a time.\n\n"
            "A bigger percent means a bigger part out of 100.\n\n"
            f"Which is larger: {left} or {right}?"
        )
    if task.question_type == 'equivalent_fraction':
        choices = ' or '.join(task.choices)
        return (
            "Let's look for the fraction that names the same amount.\n\n"
            "Equivalent fractions can look different, but they have the same value.\n\n"
            f"Which choice is equivalent: {choices}?"
        )
    return f"Let's work on this one step at a time.\n\n{task.original_text}"


def _parse_comparison(text: str) -> ConceptualMathTask:
    lowered = text.lower()
    wants_larger = any(marker in lowered for marker in ('which is larger', 'which is greater', 'which one is larger', 'which one is greater', 'compare'))
    wants_smaller = any(marker in lowered for marker in ('which is smaller', 'which is less', 'which one is smaller', 'which one is less'))
    if not (wants_larger or wants_smaller):
        return ConceptualMathTask()

    choices = _extract_number_choices(text)
    if len(choices) < 2:
        return ConceptualMathTask()

    left, right = choices[0], choices[1]
    left_value = _value_of(left)
    right_value = _value_of(right)
    if left_value is None or right_value is None or left_value == right_value:
        return ConceptualMathTask()

    expected = left if (left_value > right_value) == wants_larger else right
    question_type = _comparison_type(left, right)
    prompt = _clean_comparison_prompt(text)
    return ConceptualMathTask(
        accepted=True,
        original_text=prompt,
        question_type=question_type,
        expected_answer=expected,
        choices=[left, right],
        skill=_skill_for_comparison(question_type),
    )


def _parse_equivalent_fraction(text: str) -> ConceptualMathTask:
    lowered = text.lower()
    if 'equivalent' not in lowered or '/' not in text:
        return ConceptualMathTask()
    choices = _extract_number_choices(text)
    if len(choices) < 3:
        return ConceptualMathTask()

    target = choices[0]
    target_value = _value_of(target)
    if target_value is None:
        return ConceptualMathTask()

    answer_choices = choices[1:]
    matches = [choice for choice in answer_choices if _value_of(choice) == target_value]
    if len(matches) != 1:
        return ConceptualMathTask()
    prompt = _clean_equivalent_prompt(text)
    return ConceptualMathTask(
        accepted=True,
        original_text=prompt,
        question_type='equivalent_fraction',
        expected_answer=matches[0],
        choices=answer_choices[:4],
        skill='Equivalent Fractions',
    )


def _extract_number_choices(text: str) -> list[str]:
    raw = re.findall(r'-?\d+(?:\.\d+)?\s*/\s*-?\d+(?:\.\d+)?|-?\d+(?:\.\d+)?%?', text)
    choices: list[str] = []
    for item in raw:
        clean = item.replace(' ', '')
        if clean and clean not in choices:
            choices.append(clean)
    return choices


def _clean_comparison_prompt(text: str) -> str:
    raw = ' '.join(str(text or '').strip().split())
    lowered = raw.lower()
    markers = (
        'which is larger',
        'which is greater',
        'which one is larger',
        'which one is greater',
        'which is smaller',
        'which is less',
        'which one is smaller',
        'which one is less',
        'compare',
    )
    indexes = [lowered.find(marker) for marker in markers if lowered.find(marker) >= 0]
    if indexes:
        raw = raw[min(indexes):]
    return raw[:1].upper() + raw[1:] if raw else raw


def _clean_equivalent_prompt(text: str) -> str:
    raw = ' '.join(str(text or '').strip().split())
    lowered = raw.lower()
    for marker in ('which fraction', 'what fraction', 'which is equivalent', 'what is equivalent'):
        index = lowered.find(marker)
        if index >= 0:
            raw = raw[index:]
            break
    return raw[:1].upper() + raw[1:] if raw else raw


def _value_of(choice: str) -> Fraction | None:
    text = str(choice or '').strip().replace(' ', '')
    try:
        if text.endswith('%'):
            return Fraction(text[:-1]) / 100
        if '/' in text:
            left, right = text.split('/', 1)
            return Fraction(left) / Fraction(right)
        return Fraction(text)
    except Exception:
        return None


def _comparison_type(left: str, right: str) -> str:
    if left.endswith('%') or right.endswith('%'):
        return 'percent_comparison'
    if '/' in left or '/' in right:
        return 'fraction_comparison'
    return 'decimal_comparison' if ('.' in left or '.' in right) else 'number_comparison'


def _skill_for_comparison(question_type: str) -> str:
    return {
        'fraction_comparison': 'Fraction Comparison',
        'decimal_comparison': 'Decimal Comparison',
        'percent_comparison': 'Percent Comparison',
        'number_comparison': 'Number Comparison',
    }.get(question_type, 'Conceptual Math')


def _fraction_parts(value: str) -> tuple[str, str] | None:
    match = re.fullmatch(r'(-?\d+)\s*/\s*(-?\d+)', str(value or '').strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _safe_pair(choices: list[str]) -> tuple[str, str]:
    left = choices[0] if choices else 'the first choice'
    right = choices[1] if len(choices) > 1 else 'the second choice'
    return left, right
