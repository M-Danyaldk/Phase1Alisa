from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..assessment_validation import extract_math_expression, format_fraction, normalize_math_text, safe_eval_expression
from ..models import TutoringState
from ..utils.task_lifecycle import transition_to_task


@dataclass
class StudentArithmeticTask:
    accepted: bool = False
    original_text: str = ''
    expression: str = ''
    expected_answer: str = ''
    question_type: str = ''
    skill: str = 'Arithmetic Practice'


def parse_student_arithmetic_task(message: str) -> StudentArithmeticTask:
    text = ' '.join(str(message or '').strip().split())
    if not text:
        return StudentArithmeticTask()

    candidate = _extract_candidate_expression(text)
    if not candidate:
        return StudentArithmeticTask()

    normalized = normalize_math_text(candidate)
    expression = extract_math_expression(normalized)
    if not expression:
        return StudentArithmeticTask()

    expected_value = safe_eval_expression(expression)
    if expected_value is None:
        return StudentArithmeticTask()

    cleaned_expression = _display_expression(expression)
    return StudentArithmeticTask(
        accepted=True,
        original_text=text,
        expression=cleaned_expression,
        expected_answer=format_fraction(expected_value),
        question_type='arithmetic_multi_step' if _looks_multi_step(expression) else 'arithmetic_single_step',
    )


def apply_student_arithmetic_state(
    previous_state: TutoringState,
    current_state: TutoringState,
    task: StudentArithmeticTask,
) -> TutoringState:
    if not task.accepted:
        return current_state

    problem_id = f'arith-{hashlib.sha1(task.expression.lower().encode("utf-8")).hexdigest()[:12]}'
    next_state = current_state.model_copy(update={
        'problem_id': problem_id,
        'problem_kind': task.question_type,
        'word_problem_schema': {
            'question_type': task.question_type,
            'expression': task.expression,
            'expected_answer': task.expected_answer,
        },
        'main_problem': task.expression,
        'full_problem': task.expression,
        'active_problem': task.expression,
        'ordered_steps': [],
        'current_step_index': 0,
        'current_step_id': '',
        'completed_steps': [],
        'current_expression': task.expression,
        'remaining_steps': [],
        'completed_step_results': [],
        'step_results': {},
        'attempts_per_step': {},
        'support_per_step': {},
        'current_step': task.expression,
        'current_question': f'What is {task.expression}?',
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
        'memory_note': f'We are working on {task.expression}.',
    })
    return transition_to_task(
        previous_state,
        next_state,
        task.expression,
        subject='Math',
        topic=task.skill,
        source='student_arithmetic',
        previous='pause',
    )


def build_student_arithmetic_start_reply(task: StudentArithmeticTask) -> str:
    if task.question_type == 'arithmetic_multi_step':
        return (
            f"Let's work through {task.expression} one step at a time.\n\n"
            "Start carefully and keep track of each operation.\n\n"
            f"What is {task.expression}?"
        )
    return (
        f"Let's solve {task.expression} one step at a time.\n\n"
        f"What is {task.expression}?"
    )


def _extract_candidate_expression(text: str) -> str:
    lowered = text.lower().strip().rstrip('?.!')
    disallowed_prefixes = (
        'my answer',
        'answer is',
        'i got',
        'i think it is',
        'it is',
        'equals',
        'the answer',
    )
    if lowered.startswith(disallowed_prefixes):
        return ''

    direct_patterns = (
        r'^\s*(what is|solve|calculate)\s+(.+?)\s*$',
        r'^\s*(.+?)\s*$',
    )
    for pattern in direct_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(match.lastindex or 0).strip().rstrip('?.!') if match.lastindex else text.strip().rstrip('?.!')
        if _is_expression_like(candidate):
            return candidate
    return ''


def _is_expression_like(text: str) -> bool:
    compact = normalize_math_text(text)
    if not compact:
        return False
    if re.search(r'[a-z]{2,}', compact.lower()):
        return False
    expression = extract_math_expression(compact)
    if not expression:
        return False
    stripped = re.sub(r'\s+', '', compact)
    normalized_expression = re.sub(r'\s+', '', expression)
    return stripped == normalized_expression


def _looks_multi_step(expression: str) -> bool:
    compact = expression.replace(' ', '')
    operator_count = 0
    for index, character in enumerate(compact):
        if character in {'+', '*', '/'}:
            operator_count += 1
        elif character == '-' and index > 0 and compact[index - 1] not in '+-*/(':
            operator_count += 1
    return operator_count >= 2 or ('(' in compact and ')' in compact)


def _display_expression(expression: str) -> str:
    return (
        str(expression or '')
        .replace('*', 'x')
        .replace('\u00d7', 'x')
        .replace('\u00f7', '/')
        .strip()
    )
