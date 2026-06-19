from backend.app.main import _math_topic_switch_state, _tutor_math_question_state
from backend.app.models import TutoringState
from backend.app.tutor_math_practice_bank import select_tutor_math_question
from backend.app.utils.multi_step_progress import advance_structured_math_problem, has_structured_math_problem, update_multi_step_progress
from backend.app.utils.task_lifecycle import (
    active_task,
    can_resume_paused_task,
    complete_active_task,
    complete_and_resume_latest,
    ensure_task_lifecycle,
    latest_paused_task,
    pause_active_task,
    resume_latest_paused_task,
    start_task,
    transition_to_task,
)


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []

    practice_question = select_tutor_math_question(4, topic='multiplication')
    practice = _tutor_math_question_state(TutoringState(current_subject='Math'), 'Math', 'ready', practice_question)
    _expect(active_task(practice) is not None, 'Practice question did not create an active task.', failures)
    _expect(len([task for task in practice.task_records if task.status == 'active']) == 1, 'Practice state did not have exactly one active task.', failures)

    completed_practice = complete_active_task(practice.model_copy(update={
        'active_problem': '',
        'current_step': '',
        'current_question': '',
        'final_answer': practice.expected_answer,
        'problem_status': 'finished',
        'status': 'finished',
    }))
    _expect(active_task(completed_practice) is None, 'Completed practice task remained active.', failures)
    _expect(completed_practice.task_records[-1].status == 'completed', 'Practice task was not marked completed.', failures)
    _expect(not can_resume_paused_task(completed_practice), 'Completed practice task was incorrectly restorable.', failures)

    auditorium = update_multi_step_progress('28 * 35 - 180', TutoringState(current_subject='Math'))
    while has_structured_math_problem(auditorium):
        auditorium = advance_structured_math_problem(auditorium, auditorium.expected_answer)
    _expect(auditorium.final_answer == '800', 'Auditorium structured problem did not finish with 800.', failures)
    _expect(auditorium.task_records[-1].status == 'completed', 'Finished auditorium task was not marked completed.', failures)

    pizza_state = auditorium.model_copy(update={
        'problem_id': '',
        'main_problem': '',
        'full_problem': '',
        'ordered_steps': [],
        'current_step_id': '',
        'active_problem': 'Find an equivalent fraction for 3/8 with denominator 16.',
        'current_step': '8 x ? = 16',
        'current_question': 'What number multiplies 8 to make 16?',
        'expected_answer': '2',
        'final_answer': '',
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
    })
    pizza_state = transition_to_task(
        auditorium,
        pizza_state,
        pizza_state.active_problem,
        subject='Math',
        topic='fractions',
        source='student',
        previous='pause',
    )
    _expect(auditorium.task_records[-1].status == 'completed', 'Starting fractions changed the completed auditorium task.', failures)
    _expect(not can_resume_paused_task(pizza_state), 'Completed auditorium task became paused when fractions started.', failures)
    finished_pizza = complete_active_task(pizza_state.model_copy(update={
        'active_problem': '',
        'current_step': '',
        'current_question': '',
        'final_answer': '6/16',
        'problem_status': 'finished',
        'status': 'finished',
    }))
    no_stale_restore = complete_and_resume_latest(finished_pizza)
    _expect(active_task(no_stale_restore) is None, 'Completed auditorium task returned after the fraction task.', failures)
    _expect(not can_resume_paused_task(no_stale_restore), 'A completed task remained eligible for restoration.', failures)

    original = update_multi_step_progress('12 + 3 * 4', TutoringState(current_subject='Math'))
    original_task_id = original.active_task_id
    cookie = original.model_copy(update={
        'problem_id': '',
        'main_problem': '',
        'full_problem': '',
        'ordered_steps': [],
        'current_step_id': '',
        'active_problem': 'A bakery made 72 cookies, sold 48, then baked 36 more.',
        'current_step': '72 - 48',
        'current_question': 'What is 72 - 48?',
        'expected_answer': '24',
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
    })
    cookie = transition_to_task(original, cookie, cookie.active_problem, subject='Math', source='student', previous='pause')
    _expect(latest_paused_task(cookie) is not None and latest_paused_task(cookie).task_id == original_task_id, 'Starting a new problem did not pause the unfinished original task.', failures)
    _expect(active_task(cookie) is not None and active_task(cookie).problem_text.startswith('A bakery'), 'Cookie problem did not become the only active task.', failures)

    resumed = complete_and_resume_latest(cookie.model_copy(update={
        'final_answer': '60',
        'problem_status': 'finished',
        'status': 'finished',
    }))
    _expect(active_task(resumed) is not None and active_task(resumed).task_id == original_task_id, 'Original task did not resume after the temporary task completed.', failures)
    _expect(resumed.mode == 'resume_paused_problem_notice', 'Resumed task did not announce restoration.', failures)
    _expect(all(task.status != 'paused' for task in resumed.task_records), 'Resumed task remained duplicated in paused status.', failures)

    paused = pause_active_task(resumed)
    _expect(active_task(paused) is None and latest_paused_task(paused) is not None, 'Explicit pause did not remove the active task.', failures)
    resumed_again = resume_latest_paused_task(paused)
    _expect(active_task(resumed_again) is not None and resumed_again.current_question == original.current_question, 'Explicit resume did not restore the exact saved step.', failures)

    side_task = resumed_again.model_copy(update={
        'active_problem': '9 + 4',
        'current_step': '9 + 4',
        'current_question': 'What is 9 + 4?',
        'expected_answer': '13',
        'problem_status': 'awaiting_step',
    })
    side_task = transition_to_task(resumed_again, side_task, '9 + 4', subject='Math', source='student', previous='pause')
    swapped = resume_latest_paused_task(side_task)
    _expect(len([task for task in swapped.task_records if task.status == 'active']) == 1, 'Explicit resume created multiple active tasks.', failures)
    _expect(active_task(swapped) is not None and active_task(swapped).task_id == original_task_id, 'Explicit resume did not activate the intended paused task.', failures)
    _expect(any(task.status == 'paused' and task.problem_text == '9 + 4' for task in swapped.task_records), 'Task interrupted by explicit resume was not preserved as paused.', failures)

    switched = _math_topic_switch_state(resumed_again, 'I want to learn fractions', 'fraction')
    _expect(active_task(switched) is None, 'Topic switch left the old task active.', failures)
    _expect(any(task.status == 'abandoned' for task in switched.task_records), 'Topic switch did not mark the old routine task abandoned.', failures)
    _expect(not can_resume_paused_task(switched), 'Abandoned task remained eligible for restoration.', failures)

    stale_legacy = ensure_task_lifecycle(TutoringState(
        current_subject='Math',
        active_problem='28 x 35 - 180',
        final_answer='800',
        problem_status='finished',
        status='finished',
        paused_main_problem='28 x 35 - 180',
        paused_current_step='980 - 180',
    ))
    _expect(not stale_legacy.paused_main_problem, 'Legacy completed state retained a stale paused problem.', failures)
    _expect(not can_resume_paused_task(stale_legacy), 'Legacy completed task was still restorable.', failures)

    bounded = TutoringState(current_subject='Math')
    for index in range(25):
        problem = f'{index} + 1'
        bounded = bounded.model_copy(update={
            'active_problem': problem,
            'current_question': f'What is {problem}?',
            'problem_status': 'awaiting_step',
            'status': 'waiting_for_student',
        })
        bounded = start_task(bounded, problem, subject='Math', previous='pause')
    _expect(len([task for task in bounded.task_records if task.status == 'paused']) <= 10, 'Paused task history grew without a bound.', failures)
    _expect(len([task for task in bounded.task_records if task.status == 'active']) == 1, 'Bounding task history removed or duplicated the active task.', failures)

    if failures:
        print('Tutor task lifecycle check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor task lifecycle check passed.')
    print('- Every problem has one explicit lifecycle status.')
    print('- Completed and abandoned tasks cannot return.')
    print('- Temporary tasks pause and restore the exact unfinished task once.')
    print('- Explicit pause/resume restores the saved step.')
    print('- Legacy completed state clears stale paused-problem fields.')


if __name__ == '__main__':
    main()
