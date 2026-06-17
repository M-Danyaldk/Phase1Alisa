import hashlib
import re

from ..assessment_validation import format_fraction, normalize_math_text, safe_eval_expression
from ..models import TutorHelperBranch, TutorStepRecord, TutoringState

NUMBER_TOKEN = r'(?<![\d/])-?\d+(?:/\d+)?(?![\d/])'


def update_multi_step_progress(message: str, state: TutoringState) -> TutoringState:
    incoming_problem = _extract_math_problem(message)
    problem = incoming_problem or state.main_problem or state.full_problem
    if not problem or not _is_multi_step_problem(problem):
        return state

    normalized_problem = _normalize_expression(problem)
    if not normalized_problem:
        return state

    if state.problem_id and state.main_problem and _normalize_expression(state.main_problem) == normalized_problem and state.ordered_steps:
        if incoming_problem and _normalize_expression(incoming_problem) == normalized_problem:
            return _initialize_structured_problem_state(state, normalized_problem)
        return _sync_existing_state(state, normalized_problem)

    return _initialize_structured_problem_state(state, normalized_problem)


def build_progress_tracker_directives(state: TutoringState) -> list[str]:
    if not state.ordered_steps or not state.main_problem:
        return []

    completed = '\n'.join(f'- {step}' for step in state.completed_steps) or '- None yet'
    remaining_items = []
    for step in state.ordered_steps[state.current_step_index + 1:]:
        remaining_items.append(f'{step.label}: {step.description or step.expression}')
    remaining = '\n'.join(remaining_items) or 'Final answer check'
    current_step = _current_step_record(state)
    current_label = current_step.label if current_step else f'Step {max(1, state.current_step_index + 1)}'
    current_expression = state.current_expression or state.main_problem

    return [
        'This is a structured multi-step math problem. Keep a visible progress tracker in the tutor reply.',
        'The progress tracker must include these labels: Main problem, Step complete, Now the problem becomes, Steps left, Current step.',
        'Show the step labels exactly like Step A, Step B, Step C when available.',
        'Ask only one small question at the end of the reply.',
        f'Main problem: {_display_expression(state.main_problem)}',
        f'Completed steps so far:\n{completed}',
        f'Current full expression: {_display_expression(current_expression)}',
        f'Steps left:\n{remaining}',
        f'Current step: {current_label}',
    ]


def has_structured_math_problem(state: TutoringState) -> bool:
    return bool(state.problem_id and state.ordered_steps and state.current_step_id)


def advance_structured_math_problem(state: TutoringState, resolved_answer: str = '') -> TutoringState:
    if not has_structured_math_problem(state):
        return state

    current_step = _current_step_record(state)
    if not current_step:
        return state

    result = resolved_answer or current_step.expected_answer
    updated_steps: list[TutorStepRecord] = []
    for step in state.ordered_steps:
        if step.step_id == current_step.step_id:
            updated_steps.append(step.model_copy(update={
                'result': result,
                'status': 'complete',
                'attempts': state.attempts_per_step.get(step.step_id, state.attempt_count),
            }))
        else:
            updated_steps.append(step)

    completed_steps = list(state.completed_steps)
    completed_steps.append(f'{current_step.label}: {_display_expression(current_step.expression)} = {result}')
    completed_step_results = list(state.completed_step_results)
    if current_step.updated_expression:
        completed_step_results.append(_display_expression(current_step.updated_expression))

    step_results = dict(state.step_results)
    step_results[current_step.step_id] = result

    next_index = state.current_step_index + 1
    if next_index >= len(updated_steps):
        return state.model_copy(update={
            'ordered_steps': updated_steps,
            'completed_steps': completed_steps,
            'completed_step_results': completed_step_results,
            'step_results': step_results,
            'current_expression': current_step.updated_expression or result,
            'remaining_steps': [],
            'current_step_index': len(updated_steps),
            'current_step_id': '',
            'current_step': '',
            'current_question': '',
            'expected_answer': '',
            'attempt_count': 0,
            'hint_given': False,
            'answer_revealed': False,
            'return_step_index': len(updated_steps),
            'return_step_id': '',
            'final_answer': result,
            'problem_status': 'finished',
            'mode': 'solve',
            'status': 'finished',
        })

    next_step = updated_steps[next_index]
    updated_steps[next_index] = next_step.model_copy(update={'status': 'in_progress'})
    next_step = updated_steps[next_index]
    return state.model_copy(update={
        'ordered_steps': updated_steps,
        'completed_steps': completed_steps,
        'completed_step_results': completed_step_results,
        'step_results': step_results,
        'current_expression': current_step.updated_expression or state.current_expression,
        'remaining_steps': [step.description or step.expression for step in updated_steps[next_index + 1:]],
        'current_step_index': next_index,
        'current_step_id': next_step.step_id,
        'current_step': next_step.expression,
        'current_question': _step_prompt(next_step),
        'expected_answer': next_step.expected_answer,
        'step_number': next_index + 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'return_step_index': next_index,
        'return_step_id': next_step.step_id,
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
    })


def build_structured_step_reply(previous_state: TutoringState, next_state: TutoringState, reveal: bool = False) -> str:
    current_step = _current_step_record(previous_state)
    if not current_step:
        return ''

    intro = "Let's finish this part together." if reveal else "Yes, that's right!"
    result = next_state.step_results.get(current_step.step_id) or current_step.result or current_step.expected_answer
    lines = [intro, '']
    lines.extend(_structured_progress_lines(previous_state, current_step, result))

    if current_step.updated_expression:
        lines.extend([
            '',
            f'Now the problem becomes: {_display_expression(current_step.updated_expression)}',
        ])

    if next_state.problem_status == 'finished':
        lines.extend([
            '',
            f'Final answer: {next_state.final_answer}.',
        ])
        return '\n'.join(lines)

    next_step = _current_step_record(next_state)
    if next_step:
        lines.extend([
            '',
            f"Now let's move to {next_step.label}.",
            '',
            f'{next_step.label}: {next_step.description or _display_expression(next_step.expression)}',
            '',
            'Easy idea:',
            _child_friendly_step_explanation(next_step),
            '',
            _step_answer_guidance(next_step),
            '',
            _step_prompt(next_step),
        ])
    return '\n'.join(lines)


def build_structured_roadmap_reply(state: TutoringState) -> str:
    if not has_structured_math_problem(state):
        return ''

    current_step = _current_step_record(state)
    if not current_step:
        return ''

    lines = [
        "We can solve this one step at a time.",
        '',
        f'Main problem: {_display_expression(state.main_problem or state.active_problem)}',
        '',
        'Step roadmap:',
    ]
    lines.extend(_roadmap_lines(state))
    lines.extend([
        '',
        f"Now let's start with {current_step.label}.",
        '',
        f'{current_step.label}: {current_step.description or _display_expression(current_step.expression)}',
        '',
        'Easy idea:',
        _child_friendly_step_explanation(current_step),
        '',
        _step_answer_guidance(current_step),
        '',
        "Let's start here:",
        _step_prompt(current_step),
    ])
    return '\n'.join(lines)


def build_structured_retry_reply(state: TutoringState, attempt_count: int) -> str:
    current_step = _current_step_record(state)
    if not current_step:
        return ''

    stronger = attempt_count >= 2
    opener = 'Good try.'
    hint_lines = _structured_hint_lines(current_step, stronger=stronger)
    lines = [
        opener,
        '',
        "Let's check that.",
        '',
        f'Main problem: {_display_expression(state.main_problem or state.active_problem)}',
        f'Current step: {current_step.label}',
        f'{current_step.label}: {_display_expression(current_step.expression)}',
        '',
        'Easy idea:',
        _child_friendly_step_explanation(current_step),
        '',
        _step_answer_guidance(current_step),
    ]
    if hint_lines:
        lines.extend([''])
        lines.extend(hint_lines)
    lines.extend([
        '',
        _step_prompt(current_step),
    ])
    return '\n'.join(lines)


def build_structured_step_focus_reply(state: TutoringState, intro: str = '') -> str:
    current_step = _current_step_record(state)
    if not current_step:
        return ''

    lines: list[str] = []
    if intro.strip():
        lines.extend([intro.strip(), ''])
    lines.extend([
        f'Main problem: {_display_expression(state.main_problem or state.active_problem)}',
        f'Current step: {current_step.label}',
        f'{current_step.label}: {_display_expression(current_step.expression)}',
        '',
        'Easy idea:',
        _child_friendly_step_explanation(current_step),
        '',
        _step_answer_guidance(current_step),
        '',
        _step_prompt(current_step),
    ])
    return '\n'.join(lines)


def current_step_expression(state: TutoringState) -> str:
    step = _current_step_record(state)
    if step:
        return step.expression
    return state.current_step or state.current_question or ''


def _structured_progress_lines(state: TutoringState, step: TutorStepRecord, result: str) -> list[str]:
    lines = []
    main_problem = _display_expression(state.main_problem or state.active_problem)
    if main_problem:
        lines.append(f'Main problem: {main_problem}')
    lines.append(f'{step.label} complete: {_display_expression(step.expression)} = {result}')
    guidance = _result_format_followup(step, result)
    if guidance:
        lines.append(guidance)
    return lines


def _roadmap_lines(state: TutoringState) -> list[str]:
    lines: list[str] = []
    current_step_id = state.current_step_id
    for step in state.ordered_steps:
        summary = _student_facing_roadmap_summary(step, is_current=step.step_id == current_step_id)
        lines.append(f'{step.label}: {summary}')
    return lines


def _student_facing_roadmap_summary(step: TutorStepRecord, is_current: bool = False) -> str:
    expression = _display_expression(step.expression)
    compact = step.expression.replace(' ', '')
    if is_current:
        return f'Solve {expression}'
    if (step.description or '').lower().startswith('solve the parentheses'):
        return f'Solve {expression}'
    if '*' in compact or ('/' in compact and re.fullmatch(r'(\d+)/(\d+)/(\d+)/(\d+)', compact)):
        return f'Solve {expression}'
    if '+' in compact:
        whole_plus_fraction = re.fullmatch(r'(\d+/\d+)\+(\d+)', compact) or re.fullmatch(r'(\d+)\+(\d+/\d+)', compact)
        fraction_add = re.fullmatch(r'(\d+)/(\d+)\+(\d+)/(\d+)', compact)
        if whole_plus_fraction:
            return 'Add the final results'
        if fraction_add:
            return 'Add the fraction results'
        return 'Add the next results'
    if '-' in compact:
        return 'Finish the subtraction step'
    return f'Solve {expression}'


def _remaining_step_labels(state: TutoringState, completed_step_id: str = '') -> str:
    labels: list[str] = []
    completed_seen = not completed_step_id
    for step in state.ordered_steps:
        if completed_step_id and step.step_id == completed_step_id:
            completed_seen = True
            continue
        if not completed_seen:
            continue
        if step.status != 'complete':
            labels.append(step.label)
    return ', '.join(labels) if labels else 'None'


def _structured_hint_lines(step: TutorStepRecord, stronger: bool = False) -> list[str]:
    expression = step.expression.replace(' ', '')
    if '+' in expression:
        whole_plus_fraction = re.fullmatch(r'(\d+/\d+)\+(\d+)', expression) or re.fullmatch(r'(\d+)\+(\d+/\d+)', expression)
        same_denominator = re.fullmatch(r'(\d+)/(\d+)\+(\d+)/(\d+)', expression)
        if whole_plus_fraction:
            fraction_part = whole_plus_fraction.group(1) if '/' in whole_plus_fraction.group(1) else whole_plus_fraction.group(2)
            whole_part = whole_plus_fraction.group(2) if '/' in whole_plus_fraction.group(1) else whole_plus_fraction.group(1)
            denominator = fraction_part.split('/')[1]
            if stronger:
                return [
                    'We need matching pieces first.',
                    f'Turn {whole_part} into {int(whole_part) * int(denominator)}/{denominator}.',
                    'Then add the top numbers and keep the bottom number the same.',
                ]
            return [
                'The whole number needs the same bottom number as the fraction first.',
                f'Start by turning {whole_part} into a fraction with {denominator} on the bottom.',
            ]
        if same_denominator and same_denominator.group(2) == same_denominator.group(4):
            denominator = same_denominator.group(2)
            if stronger:
                return [
                    'The bottom numbers already match.',
                    f'Add the top numbers only and keep {denominator} on the bottom.',
                ]
            return [
                'The bottom numbers already match, so do not change them.',
                'Start by adding the top numbers only.',
            ]
        left_denominator = same_denominator.group(2) if same_denominator else ''
        right_denominator = same_denominator.group(4) if same_denominator else ''
        if stronger and left_denominator == '8' and right_denominator == '9':
            return [
                'We need the same bottom number first.',
                '8 and 9 both fit into 72.',
                'Now rename both fractions so they use 72 on the bottom.',
            ]
        if stronger:
            return [
                'We need the same bottom number first.',
                f'Look for one number both {left_denominator} and {right_denominator} can fit into.',
                'Then rename both fractions before you add.',
            ]
        return [
            'The bottom numbers are different, so we cannot add yet.',
            f'What number can both {left_denominator} and {right_denominator} fit into?',
        ]
    if '-' in expression:
        if stronger:
            left, right = expression.split('-', 1)
            return [
                'Stay on this subtraction step only.',
                f'Start with {left}, then take away {right}.',
            ]
        return [
            'Stay on this subtraction step only.',
            'Start with the first number, then take away the second number.',
        ]
    if '*' in expression:
        if re.fullmatch(r'(\d+)/(\d+)\*(\d+)/(\d+)', expression):
            top_left, bottom_left, top_right, bottom_right = re.fullmatch(r'(\d+)/(\d+)\*(\d+)/(\d+)', expression).groups()
            if stronger:
                return [
                    f'Start with the top numbers: {top_left} x {top_right}.',
                    f'Then do the bottom numbers: {bottom_left} x {bottom_right}.',
                ]
            return [
                'For fraction multiplication, do the top numbers together first.',
                'Then do the bottom numbers together.',
            ]
        if '/' in expression:
            left_part, right_part = expression.split('/', 1)
            left_display = _display_expression(left_part)
            right_display = _display_expression(right_part)
            if stronger:
                return [
                    f'First work out {left_display}.',
                    f'After that, divide that result by {right_display}.',
                ]
            return [
                'In this step, multiply first before dividing.',
                f'Start with {left_display}.',
            ]
        if stronger:
            return [
                'Stay on this multiplication step only.',
                'Multiply the two numbers in this step.',
            ]
        return [
            'Stay on this multiplication step only.',
            'Start by multiplying the numbers in this step.',
        ]
    if '/' in expression and re.fullmatch(r'(\d+)/(\d+)/(\d+)/(\d+)', expression):
        if stronger:
            return [
                'Keep the first fraction the same.',
                'Flip the second fraction, then multiply.',
            ]
        return [
            'For dividing fractions, change the division into multiplication first.',
            'Then flip the second fraction.',
        ]
    return ['Focus only on this one step first.']


def _child_friendly_step_explanation(step: TutorStepRecord) -> str:
    expression = step.expression.replace(' ', '')
    if (step.description or '').lower().startswith('solve the parentheses'):
        return 'The parentheses are like a little box inside the big problem. We finish that box first, then bring its answer back to the whole problem.'

    whole_plus_fraction = re.fullmatch(r'(\d+/\d+)\+(\d+)', expression) or re.fullmatch(r'(\d+)\+(\d+/\d+)', expression)
    any_fraction_add = re.fullmatch(r'(\d+)/(\d+)\+(\d+)/(\d+)', expression)

    if whole_plus_fraction:
        return 'Think about money, like dollars and coins. If one amount is whole and the other is split into smaller pieces, we first rename the whole amount into matching pieces so we can add them fairly.'

    if any_fraction_add:
        left_denominator = any_fraction_add.group(2)
        right_denominator = any_fraction_add.group(4)
        if left_denominator == right_denominator:
            return 'Think about pizza slices cut the same way. When the slice size already matches, we only add how many slices we have.'
        return 'Think about pizza slices from two pizzas cut into different-size pieces. Before adding, we rename them into matching-size slices.'

    if '-' in expression:
        return 'Think about spending some of your money at a store. Subtraction shows what is left after part of it is gone.'

    if '*' in expression:
        if re.fullmatch(r'(\d+)/(\d+)\*(\d+)/(\d+)', expression):
            return 'Think about game points on two score cards. For fraction multiplication, we multiply the top numbers together and the bottom numbers together to make one new fraction.'
        return 'Think about equal groups of stickers. Multiplication means the same amount is repeated, so we count the groups step by step.'

    if '/' in expression and re.fullmatch(r'(\d+)/(\d+)/(\d+)/(\d+)', expression):
        return 'Think about sharing snacks equally. For fraction division, we keep the first fraction, flip the second one, and then multiply.'

    if '/' in expression:
        return 'Think about sharing something equally with friends. Division asks how many equal groups we can make.'

    return 'We will solve this small part first, then place it back into the bigger problem.'


def _sync_existing_state(state: TutoringState, normalized_problem: str) -> TutoringState:
    current_step = _current_step_record(state)
    return state.model_copy(update={
        'main_problem': normalized_problem,
        'active_problem': normalized_problem,
        'full_problem': normalized_problem,
        'current_expression': state.current_expression or normalized_problem,
        'current_step': current_step.expression if current_step else state.current_step,
        'current_question': _step_prompt(current_step) if current_step else (state.current_question or state.current_step),
        'expected_answer': current_step.expected_answer if current_step else state.expected_answer,
        'step_number': max(1, state.current_step_index + 1) if state.current_step_id else state.step_number,
        'problem_status': state.problem_status or 'awaiting_step',
    })


def _initialize_structured_problem_state(state: TutoringState, normalized_problem: str) -> TutoringState:
    steps = _plan_steps(normalized_problem)
    if not steps:
        return state

    first_step = steps[0]
    return state.model_copy(update={
        'problem_id': _problem_id(normalized_problem),
        'main_problem': normalized_problem,
        'active_problem': normalized_problem,
        'full_problem': normalized_problem,
        'ordered_steps': steps,
        'current_step_index': 0,
        'current_step_id': first_step.step_id,
        'completed_steps': [],
        'current_expression': normalized_problem,
        'remaining_steps': [step.description or step.expression for step in steps[1:]],
        'completed_step_results': [],
        'step_results': {},
        'attempts_per_step': {},
        'current_step': first_step.expression,
        'current_question': _step_prompt(first_step),
        'expected_answer': first_step.expected_answer,
        'student_answer': '',
        'correctness_status': '',
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'helper_branch': TutorHelperBranch(),
        'queued_followup_questions': [],
        'pending_input_kind': '',
        'pending_new_problem': '',
        'paused_main_problem': '',
        'paused_current_step': '',
        'paused_current_question': '',
        'paused_completed_steps': [],
        'return_step_index': 0,
        'return_step_id': first_step.step_id,
        'final_answer': '',
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
        'memory_note': f'We are working on {normalized_problem}.',
    })


def _current_step_record(state: TutoringState) -> TutorStepRecord | None:
    if not state.ordered_steps:
        return None
    if state.current_step_id:
        for step in state.ordered_steps:
            if step.step_id == state.current_step_id:
                return step
    if 0 <= state.current_step_index < len(state.ordered_steps):
        return state.ordered_steps[state.current_step_index]
    return None


def _plan_steps(problem: str) -> list[TutorStepRecord]:
    current_expression = problem
    steps: list[TutorStepRecord] = []
    labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    index = 0

    while _has_math_operator(current_expression):
        next_expression = _next_step_expression(current_expression)
        if not next_expression:
            break

        value = safe_eval_expression(next_expression)
        if value is None:
            break

        expected_answer = format_fraction(value)
        updated_expression = _replace_step(current_expression, next_expression, expected_answer)
        if updated_expression == current_expression:
            break

        label = f'Step {labels[index]}' if index < len(labels) else f'Step {index + 1}'
        steps.append(TutorStepRecord(
            step_id=f'{_problem_id(problem)}-{index + 1}',
            label=label,
            description=_step_description(current_expression, next_expression),
            expression=next_expression,
            expected_answer=expected_answer,
            updated_expression=updated_expression,
            status='in_progress' if index == 0 else 'pending',
        ))

        current_expression = updated_expression
        index += 1
        if index > 12:
            break

    return steps


def _problem_id(problem: str) -> str:
    return hashlib.sha1(problem.encode('utf-8')).hexdigest()[:12]


def _extract_math_problem(message: str) -> str:
    normalized = _normalize_expression(message)
    match = re.search(r'[-\d\s/+\-*().]+', normalized)
    if not match:
        return ''
    problem = ' '.join(match.group(0).split())
    return problem if _is_multi_step_problem(problem) else ''


def _normalize_expression(text: str) -> str:
    normalized = normalize_math_text(text)
    normalized = normalized.replace('=', ' ')
    normalized = re.sub(r'(?<![\d/])(-?\d+)\s*/\s*(-?\d+)(?![\d/])', r'\1/\2', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _is_multi_step_problem(problem: str) -> bool:
    compact = problem.replace(' ', '')
    operators = len(re.findall(r'(?<!/)[+\-*](?!/)', compact))
    multiply_or_divide_steps = len(re.findall(rf'{NUMBER_TOKEN}\s*[*/]\s*{NUMBER_TOKEN}', problem))
    add_or_subtract_steps = len(re.findall(rf'{NUMBER_TOKEN}\s*[+-]\s*{NUMBER_TOKEN}', problem))
    return (
        operators >= 2
        or ('(' in compact and ')' in compact)
        or multiply_or_divide_steps >= 2
        or (multiply_or_divide_steps >= 1 and add_or_subtract_steps >= 1)
    )


def _has_math_operator(expression: str) -> bool:
    compact = expression.replace(' ', '')
    return bool(
        re.search(r'(?<!/)[+\-*](?!/)', compact)
        or re.search(rf'{NUMBER_TOKEN}\s*/\s*{NUMBER_TOKEN}', expression)
    )


def _next_step_expression(expression: str) -> str:
    normalized = expression.strip()

    paren_matches = list(re.finditer(r'\(([^()]+)\)', normalized))
    for match in paren_matches:
        inner = match.group(1).strip()
        if _has_math_operator(inner):
            return inner

    multiply_or_divide = re.search(
        rf'({NUMBER_TOKEN})\s*([*/])\s*({NUMBER_TOKEN})',
        normalized,
    )
    if multiply_or_divide:
        return multiply_or_divide.group(0).strip()

    add_or_subtract = re.search(
        rf'({NUMBER_TOKEN})\s*([+-])\s*({NUMBER_TOKEN})',
        normalized,
    )
    if add_or_subtract:
        return add_or_subtract.group(0).strip()

    return normalized if safe_eval_expression(normalized) is not None else ''


def _replace_step(full_expression: str, step_expression: str, result: str) -> str:
    paren_pattern = re.escape(f'({step_expression})')
    replaced = re.sub(paren_pattern, result, full_expression, count=1)
    if replaced != full_expression:
        return _normalize_expression(replaced)
    replaced = re.sub(re.escape(step_expression), result, full_expression, count=1)
    return _normalize_expression(replaced)


def _step_description(full_expression: str, step_expression: str) -> str:
    if f'({step_expression})' in full_expression:
        return f'Solve the parentheses -> {_display_expression(step_expression)}'
    if '*' in step_expression:
        return f'Multiply -> {_display_expression(step_expression)}'
    if '/' in step_expression and re.search(r'\d+/\d+\s*/\s*\d+/\d+', step_expression):
        return f'Divide -> {_display_expression(step_expression)}'
    if '+' in step_expression:
        return f'Add -> {_display_expression(step_expression)}'
    if '-' in step_expression:
        return f'Subtract -> {_display_expression(step_expression)}'
    return f'Solve -> {_display_expression(step_expression)}'


def _step_prompt(step: TutorStepRecord | None) -> str:
    if not step:
        return ''
    return f'What is {_display_expression(step.expression)}?'


def _step_answer_guidance(step: TutorStepRecord) -> str:
    if _should_prefer_fraction_form(step):
        return 'Answer form: keep your answer as a fraction for now so the next step stays easy to follow.'
    if _is_exact_whole_number_step(step):
        return 'Answer form: write the whole number you get for this step.'
    return 'Answer form: write just the value for this step before going back to the whole problem.'


def _result_format_followup(step: TutorStepRecord, result: str) -> str:
    if _should_prefer_fraction_form(step) and '/' in result:
        return f'We will keep {result} as a fraction so the next step is easier to follow.'
    if _should_prefer_fraction_form(step):
        return f'We will keep this result as {step.expected_answer} so the next step is easier to follow.'
    return ''


def _should_prefer_fraction_form(step: TutorStepRecord) -> bool:
    expression = step.expression.replace(' ', '')
    updated_expression = (step.updated_expression or '').replace(' ', '')
    if re.fullmatch(r'-?\d+/\d+', expression):
        value = safe_eval_expression(expression)
        return value is not None and value.denominator != 1
    if re.fullmatch(r'(\d+)/(\d+)[+\-*](\d+)/(\d+)', expression):
        return True
    if re.fullmatch(r'(\d+/\d+)\+(\d+)', expression) or re.fullmatch(r'(\d+)\+(\d+/\d+)', expression):
        return True
    if '/' in expression and '/' in updated_expression:
        return True
    return False


def _is_exact_whole_number_step(step: TutorStepRecord) -> bool:
    value = safe_eval_expression(step.expression)
    return value is not None and value.denominator == 1


def _display_expression(expression: str) -> str:
    text = str(expression or '').strip()
    text = text.replace('*', ' x ')
    text = re.sub(r'(?<!\d)/(?!\d)', ' / ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
