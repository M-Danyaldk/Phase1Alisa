from fractions import Fraction
import random

from backend.app.models import TutoringState
from backend.app.services.tutor_math_response_guard import TutorMathResponseGuard
from backend.app.utils.task_lifecycle import (
    abandon_active_task,
    active_task,
    complete_active_task,
    pause_active_task,
    reconcile_task_lifecycle,
    resume_latest_paused_task,
    start_task,
)


def _format(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f'{value.numerator}/{value.denominator}'


def main() -> None:
    failures: list[str] = []
    guard = TutorMathResponseGuard()
    equation_checks = 0
    for left in range(-6, 7):
        for right in range(-6, 7):
            for operator in '+-*/':
                if operator == '/' and right == 0:
                    continue
                if operator == '+':
                    value = Fraction(left + right)
                elif operator == '-':
                    value = Fraction(left - right)
                elif operator == '*':
                    value = Fraction(left * right)
                else:
                    value = Fraction(left, right)
                expression = f'{left} {operator} {right}'
                expected = _format(value)
                state = TutoringState(
                    current_subject='Math',
                    current_question=f'What is {expression}?',
                    expected_answer=expected,
                    attempt_count=3,
                    answer_revealed=True,
                    problem_status='awaiting_step',
                )
                correct = guard.validate(f'{expression} = {expected}.', state, intent_label='answer_current_step')
                incorrect = guard.validate(f'{expression} = {_format(value + 1)}.', state, intent_label='answer_current_step')
                if not correct.valid:
                    failures.append(f'Correct generated equation rejected: {expression} = {expected}.')
                if incorrect.valid:
                    failures.append(f'Incorrect generated equation accepted: {expression} = {_format(value + 1)}.')
                equation_checks += 2

    random.seed(17)
    state = TutoringState(current_subject='Math')
    operations = ('start', 'pause', 'resume', 'complete', 'abandon', 'reconcile')
    for index in range(750):
        operation = random.choice(operations)
        if operation == 'start':
            problem = f'{random.randint(1, 20)} + {random.randint(1, 20)}'
            state = state.model_copy(update={
                'active_problem': problem,
                'current_question': f'What is {problem}?',
                'problem_status': 'awaiting_step',
                'status': 'waiting_for_student',
            })
            state = start_task(state, problem, subject='Math', previous=random.choice(('pause', 'abandon')))
        elif operation == 'pause':
            state = pause_active_task(state)
        elif operation == 'resume':
            state = resume_latest_paused_task(state)
        elif operation == 'complete':
            state = complete_active_task(state.model_copy(update={'problem_status': 'finished', 'status': 'finished'}))
        elif operation == 'abandon':
            state = abandon_active_task(state)
        else:
            state = reconcile_task_lifecycle(state)

        active_records = [record for record in state.task_records if record.status == 'active']
        paused_records = [record for record in state.task_records if record.status == 'paused']
        if len(active_records) > 1:
            failures.append(f'Lifecycle operation {index} created multiple active tasks.')
            break
        if bool(state.active_task_id) != bool(active_records):
            failures.append(f'Lifecycle operation {index} desynchronized active_task_id.')
            break
        if active_records and active_task(state).task_id != state.active_task_id:
            failures.append(f'Lifecycle operation {index} selected the wrong active task.')
            break
        if len(paused_records) > 10:
            failures.append(f'Lifecycle operation {index} exceeded paused-task retention.')
            break

        restored = TutoringState.model_validate(state.model_dump())
        if restored.active_task_id != state.active_task_id or len(restored.task_records) != len(state.task_records):
            failures.append(f'State serialization changed lifecycle data at operation {index}.')
            break

    if failures:
        print('Tutor generated-invariant check failed:')
        for failure in failures[:20]:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor generated-invariant check passed.')
    print(f'- Verified {equation_checks} generated signed, fraction, and integer equation outcomes.')
    print('- Randomized lifecycle and state serialization invariants remained valid.')


if __name__ == '__main__':
    main()
