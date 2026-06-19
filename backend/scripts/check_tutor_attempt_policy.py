from backend.app.main import _tutor_math_question_state, _tutor_practice_answer_reply
from backend.app.models import TutoringState
from backend.app.services.tutor_answer_checker import TutorAnswerChecker
from backend.app.tutor_math_practice_bank import select_tutor_math_question
from backend.app.utils.attempt_policy import (
    attempt_count_for,
    attempt_scope_key,
    attempt_stage,
    preserve_attempt_progress,
    register_answer_attempt,
    reset_attempt_display,
    should_reveal,
)
from backend.app.utils.multi_step_progress import advance_structured_math_problem, update_multi_step_progress
from backend.app.utils.task_lifecycle import ensure_task_lifecycle


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []
    checker = TutorAnswerChecker()
    question = select_tutor_math_question(4, topic='multiplication')
    state = _tutor_math_question_state(TutoringState(current_subject='Math'), 'Math', 'ready', question)
    first_scope = attempt_scope_key(state)

    first = register_answer_attempt(state)
    _expect(first.attempt_count == 1 and attempt_stage(first.attempt_count) == 'small_hint', 'First answer did not enter the small-hint stage.', failures)
    _expect(not should_reveal(first.attempt_count), 'First answer incorrectly enabled reveal.', failures)

    emotional_branch = first.model_copy(update={'student_answer': 'I am tired'})
    after_emotion = preserve_attempt_progress(first, emotional_branch)
    _expect(after_emotion.attempt_count == 1, 'Emotional interruption changed the attempt count.', failures)
    _expect(attempt_count_for(after_emotion) == 1, 'Emotional interruption changed scoped attempt history.', failures)

    help_branch = reset_attempt_display(after_emotion)
    after_help = preserve_attempt_progress(after_emotion, help_branch)
    _expect(after_help.attempt_count == 1, 'Help request changed the attempt count.', failures)

    second = register_answer_attempt(after_help)
    _expect(second.attempt_count == 2 and attempt_stage(second.attempt_count) == 'strong_hint', 'Second answer did not enter the strong-hint stage.', failures)
    _expect(not should_reveal(second.attempt_count), 'Second answer incorrectly enabled reveal.', failures)

    feedback_branch = second.model_copy(update={'attempt_count': 0, 'student_answer': 'You asked the wrong question'})
    after_feedback = preserve_attempt_progress(second, feedback_branch)
    _expect(after_feedback.attempt_count == 2, 'Tutor-feedback interruption changed the attempt count.', failures)

    third = register_answer_attempt(after_feedback)
    _expect(third.attempt_count == 3 and attempt_stage(third.attempt_count) == 'reveal', 'Third answer did not enter the reveal stage.', failures)
    _expect(should_reveal(third.attempt_count), 'Third answer did not enable reveal.', failures)
    fourth = register_answer_attempt(third)
    _expect(fourth.attempt_count == 3, 'Attempt count was not capped at the reveal stage.', failures)

    wrong_check = checker._check_math(question.question, '999999', question.expected_answer)
    first_reply, _ = _tutor_practice_answer_reply(first, 'wrong one', wrong_check, '')
    second_reply, _ = _tutor_practice_answer_reply(second, 'wrong two', wrong_check, '')
    third_reply, _ = _tutor_practice_answer_reply(third, 'wrong three', wrong_check, '')
    _expect(question.expected_answer not in first_reply, 'Practice first hint revealed the answer.', failures)
    _expect(question.expected_answer not in second_reply, 'Practice second hint revealed the answer.', failures)
    _expect(question.expected_answer in third_reply, 'Practice third attempt did not reveal the answer.', failures)

    next_step_state = reset_attempt_display(third).model_copy(update={
        'current_step_id': 'next-step',
        'current_step': 'A different step',
        'current_question': 'What is the next step answer?',
    })
    next_step = register_answer_attempt(next_step_state)
    _expect(next_step.attempt_count == 1, 'A new step inherited the previous step attempt count.', failures)
    _expect(next_step.attempts_per_step.get(first_scope) == 3, 'Previous step attempt history was not retained for auditing.', failures)

    structured = update_multi_step_progress('6 + (12 / 3)', TutoringState(current_subject='Math'))
    structured_first = register_answer_attempt(structured)
    structured_second = register_answer_attempt(structured_first)
    _expect(attempt_count_for(structured_second, structured.current_step_id) == 2, 'Structured step did not use the shared attempt counter.', failures)
    advanced = advance_structured_math_problem(structured_second, structured_second.expected_answer)
    _expect(advanced.attempt_count == 0, 'Advancing a structured step did not reset the visible attempt count.', failures)
    if advanced.current_step_id:
        advanced_first = register_answer_attempt(advanced)
        _expect(advanced_first.attempt_count == 1, 'New structured step did not start at attempt one.', failures)

    word_problem = state.model_copy(update={
        'active_task_id': 'word-task',
        'current_step_id': '',
        'active_problem': 'Seven boxes hold two balls each.',
        'current_step': '7 x 2',
        'current_question': 'What is 7 x 2?',
        'attempt_count': 0,
        'attempts_per_step': {},
    })
    conceptual = state.model_copy(update={
        'active_task_id': 'concept-task',
        'current_step_id': '',
        'active_problem': 'Equivalent fractions',
        'current_step': 'Explain equivalent fractions',
        'current_question': 'Why do we multiply the top and bottom by the same number?',
        'attempt_count': 0,
        'attempts_per_step': {},
    })
    _expect(register_answer_attempt(word_problem).attempt_count == 1, 'Word problem did not use the shared attempt policy.', failures)
    _expect(register_answer_attempt(conceptual).attempt_count == 1, 'Conceptual problem did not use the shared attempt policy.', failures)
    _expect(attempt_scope_key(word_problem) != attempt_scope_key(conceptual), 'Different tasks shared an attempt scope.', failures)

    leaked_new_task = third.model_copy(update={
        'active_task_id': 'task-new',
        'current_step_id': 'new-step',
        'current_step': '9 + 4',
        'current_question': 'What is 9 + 4?',
        'attempt_count': 3,
        'answer_revealed': True,
    })
    isolated_new_task = register_answer_attempt(leaked_new_task)
    _expect(isolated_new_task.attempt_count == 1, 'A new task inherited the previous task attempt count.', failures)

    legacy = ensure_task_lifecycle(TutoringState(
        current_subject='Math',
        active_problem='8 + 5',
        current_question='What is 8 + 5?',
        attempt_count=2,
        problem_status='awaiting_step',
    ))
    _expect(register_answer_attempt(legacy).attempt_count == 3, 'Legacy attempt state was not migrated into the scoped policy.', failures)

    if failures:
        print('Tutor attempt policy check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor attempt policy check passed.')
    print('- All Math problem types use task-and-step-scoped attempts.')
    print('- First, second, and third answers map to small hint, strong hint, and reveal.')
    print('- Emotion, help, and tutor-feedback interruptions preserve the current count.')
    print('- New steps start at attempt one without losing earlier audit history.')


if __name__ == '__main__':
    main()
