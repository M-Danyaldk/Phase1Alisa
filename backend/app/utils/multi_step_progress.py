import re
from fractions import Fraction

from ..models import TutoringState


def update_multi_step_progress(message: str, state: TutoringState) -> TutoringState:
    problem = state.full_problem or _extract_math_problem(message)
    if not problem or not _is_multi_step_problem(problem):
        return state

    current_expression = state.current_expression or problem
    completed_steps = list(state.completed_steps)
    remaining_steps = list(state.remaining_steps) or _remaining_steps_for_expression(current_expression)

    first_multiplication = _first_fraction_multiplication(current_expression)
    if first_multiplication and not completed_steps:
        left, right, product = first_multiplication
        completed_steps.append(f'{left} × {right} = {product}')
        current_expression = current_expression.replace(f'{left} * {right}', product, 1)
        current_expression = current_expression.replace(f'{left} × {right}', product, 1)
        remaining_steps = _remaining_steps_for_expression(current_expression)

    return state.model_copy(update={
        'full_problem': problem,
        'completed_steps': completed_steps,
        'current_expression': current_expression,
        'remaining_steps': remaining_steps,
    })


def build_progress_tracker_directives(state: TutoringState) -> list[str]:
    if not state.full_problem or not _is_multi_step_problem(state.full_problem):
        return []

    completed = '\n'.join(f'- {step}' for step in state.completed_steps) or '- None yet'
    remaining = '\n'.join(f'{index + 1}. {step}' for index, step in enumerate(state.remaining_steps)) or '1. Simplify final answer'
    step_number = max(1, len(state.completed_steps) + 1)
    current_expression = state.current_expression or state.full_problem

    return [
        'This is a multi-step problem. Keep a visible progress tracker in the tutor reply.',
        'The progress tracker must include these labels: Full problem, Step complete, Now the problem is, Still left, Now we are on Step.',
        'Ask only one small question at the end of the reply.',
        f'Full problem: {state.full_problem}',
        f'Completed steps so far:\n{completed}',
        f'Current simplified expression: {current_expression}',
        f'Remaining steps:\n{remaining}',
        f'Current step number: {step_number}',
    ]


def _extract_math_problem(message: str) -> str:
    normalized = message.replace('×', '*').replace('÷', '/')
    match = re.search(r'[-\d\s/+\*().]+', normalized)
    if not match:
        return ''
    problem = ' '.join(match.group(0).split())
    return problem if any(op in problem for op in ['+', '*', '/']) else ''


def _is_multi_step_problem(problem: str) -> bool:
    operators = len(re.findall(r'(?<!/)[+*](?!/)', problem.replace(' ', '')))
    return operators >= 2


def _first_fraction_multiplication(expression: str) -> tuple[str, str, str] | None:
    match = re.search(r'(\d+/\d+)\s*[*×]\s*(\d+/\d+)', expression)
    if not match:
        return None
    left = match.group(1)
    right = match.group(2)
    product = Fraction(left) * Fraction(right)
    product_text = f'{product.numerator}/{product.denominator}' if product.denominator != 1 else str(product.numerator)
    return left, right, product_text


def _remaining_steps_for_expression(expression: str) -> list[str]:
    parts = [part.strip() for part in re.split(r'\+', expression) if part.strip()]
    if len(parts) <= 1:
        return ['Simplify final answer']
    steps = [f'Add {part}' for part in parts[1:]]
    steps.append('Simplify final answer')
    return steps
