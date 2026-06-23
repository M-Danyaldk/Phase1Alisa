from backend.app.models import TutoringState
from backend.app.services.tutor_math_response_guard import TutorMathResponseGuard
from backend.app.utils.task_lifecycle import ensure_task_lifecycle


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []
    guard = TutorMathResponseGuard()
    state = TutoringState(
        current_subject='Math',
        main_problem='There are 7 boxes with 2 balls in each box.',
        active_problem='There are 7 boxes with 2 balls in each box.',
        current_step='7 * 2',
        current_question='What is 7 × 2?',
        expected_answer='14',
        attempt_count=1,
        correctness_status='incorrect',
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    )

    valid = guard.validate('Use equal groups: 7 × 2. What is 7 × 2?', state, intent_label='answer_current_step')
    _expect(valid.valid and not valid.repaired, 'A valid single-step response was rejected.', failures)

    wrong_math = guard.validate('We calculate 7 × 2 = 12. What comes next?', state, intent_label='answer_current_step')
    _expect(wrong_math.repaired and 'incorrect_arithmetic' in wrong_math.violations, 'Incorrect arithmetic was not blocked.', failures)
    _expect('= 12' not in wrong_math.text, 'Incorrect arithmetic remained in repaired output.', failures)
    _expect('Let me fix that wording' in wrong_math.text and state.current_question in wrong_math.text, 'Incorrect-arithmetic repair did not use specific saved-step wording.', failures)
    _expect("Let's stay with the current Math problem" not in wrong_math.text, 'Guard repair still used the old repetitive current-problem wording.', failures)
    audit_state = state.model_copy(update={'attempt_count': 3, 'answer_revealed': True})
    wrong_decimal = guard.validate('We calculate 2.5 + 1.5 = 5.', audit_state, intent_label='answer_current_step')
    _expect(wrong_decimal.repaired and 'incorrect_arithmetic' in wrong_decimal.violations, 'Incorrect decimal arithmetic was not blocked.', failures)
    wrong_parentheses = guard.validate('We calculate 3 × (2 + 4) = 15.', audit_state, intent_label='answer_current_step')
    _expect(wrong_parentheses.repaired and 'incorrect_arithmetic' in wrong_parentheses.violations, 'Incorrect parenthesized arithmetic was not blocked.', failures)
    wrong_claim = guard.validate('The final answer is 15.', audit_state, intent_label='answer_current_step')
    _expect(wrong_claim.repaired and 'incorrect_answer_claim' in wrong_claim.violations, 'An incorrect standalone final answer was not blocked.', failures)
    negative_state = audit_state.model_copy(update={'current_question': 'What is 10 - 12?', 'expected_answer': '-2'})
    correct_negative = guard.validate('10 - 12 = -2. The final answer is -2.', negative_state, intent_label='answer_current_step')
    _expect(correct_negative.valid, 'Correct negative arithmetic was incorrectly rejected.', failures)
    student_claim = guard.validate('Your answer is 15, so let us check it. What is 10 - 12?', negative_state, intent_label='answer_current_step')
    _expect(student_claim.valid, 'A quoted student answer was mistaken for the tutor final answer.', failures)

    correct_state = state.model_copy(update={'correctness_status': 'correct', 'attempt_count': 2})
    correct_confirmation = guard.validate("Yes, that's correct!\n\n7 Ã— 2 = 14.\n\nWould you like another practice question?", correct_state, intent_label='answer_current_step')
    _expect(correct_confirmation.valid and not correct_confirmation.repaired, 'Guard repaired a correct useful confirmation.', failures)

    finished_correct_state = state.model_copy(update={
        'active_problem': '',
        'current_question': '',
        'current_step': '',
        'expected_answer': '',
        'correctness_status': 'correct',
        'final_answer': '14',
        'problem_status': 'finished',
        'mode': 'awaiting_more_practice_choice',
    })
    finished_correct = guard.validate("Yes, that's correct!\n\n7 Ã— 2 = 14.\n\nWould you like another practice question?", finished_correct_state, intent_label='answer_current_step')
    _expect(finished_correct.valid and not finished_correct.repaired, 'Guard erased a finished correct tutor-practice reply.', failures)

    premature = guard.validate('The final answer is 14.', state, intent_label='answer_current_step')
    _expect(premature.repaired and 'premature_answer_reveal' in premature.violations, 'Early answer reveal was not blocked.', failures)
    _expect('We will keep the answer hidden for now' in premature.text and state.current_question in premature.text, 'Premature reveal repair did not re-anchor to the saved question.', failures)
    revealed_state = state.model_copy(update={'attempt_count': 3, 'answer_revealed': True})
    revealed = guard.validate('The final answer is 14.', revealed_state, intent_label='answer_current_step')
    _expect(revealed.valid, 'Third-attempt answer reveal was incorrectly blocked.', failures)
    third_reveal = guard.validate("Nice effort. Let's finish this one together.\n\n7 Ã— 2 = 14.\n\nWould you like another practice question?", revealed_state, intent_label='answer_current_step')
    _expect(third_reveal.valid and not third_reveal.repaired, 'Guard erased a valid third-wrong reveal reply.', failures)

    multiple = guard.validate('What is 7 × 2? Why do we multiply?', state, intent_label='help_request')
    _expect(multiple.repaired and multiple.text.count('?') <= 1, 'Multiple tutor questions were not reduced to one.', failures)
    _expect('I will keep this to one question.' in multiple.text and state.current_question in multiple.text, 'Multiple-question repair did not keep the exact saved question.', failures)

    missing_prompt = guard.validate('Try using equal groups.', state, intent_label='answer_current_step')
    _expect(missing_prompt.repaired and 'missing_current_step_prompt' in missing_prompt.violations, 'A retry was allowed to lose the current question.', failures)
    _expect('What is 7' in missing_prompt.text and 'Now try this step: Now try this step:' not in missing_prompt.text, 'A repaired retry did not re-anchor cleanly to the verified current step.', failures)

    stale = guard.validate('**Main problem:** 28 × 35 − 180\n\nWhat is 28 × 35?', state, intent_label='answer_current_step')
    _expect(stale.repaired and 'stale_problem_reference' in stale.violations, 'Stale problem reference was not blocked.', failures)

    lifecycle_state = ensure_task_lifecycle(state)
    corrupted_state = lifecycle_state.model_copy(update={
        'main_problem': '28 × 35 - 180',
        'active_problem': 'ok proceed to this problem',
        'current_step': 'ok proceed to this problem',
        'current_question': 'ok proceed to this problem',
    })
    repaired_corrupt = guard.validate('We calculate 7 × 2 = 12. What comes next?', corrupted_state, intent_label='answer_current_step')
    _expect(repaired_corrupt.repaired and 'What is 7 × 2?' in repaired_corrupt.text, 'Repair did not restore the verified lifecycle step.', failures)
    _expect('ok proceed' not in repaired_corrupt.text and '28 × 35' not in repaired_corrupt.text, 'Repair echoed corrupted or stale task text.', failures)

    repaired_state = guard.apply_metadata(corrupted_state, repaired_corrupt, 'test-model')
    _expect(repaired_state.active_problem == state.active_problem, 'Response metadata did not preserve the verified active problem.', failures)
    _expect(repaired_state.current_question == state.current_question, 'Response metadata did not preserve the verified current question.', failures)

    non_answer = guard.validate('Nice try, that answer is not quite right.', state, intent_label='emotion')
    _expect(non_answer.repaired and 'non_answer_graded_as_wrong' in non_answer.violations, 'Emotion was allowed to receive wrong-answer language.', failures)
    _expect('That message will not count as an answer attempt.' in non_answer.text and state.current_question in non_answer.text, 'Non-answer repair did not preserve the saved question.', failures)

    problem_only = state.model_copy(update={'current_question': '', 'current_step': '', 'active_problem': '12 - 20', 'main_problem': '12 - 20'})
    repaired_problem_only = guard.validate('', problem_only, intent_label='help_request')
    _expect('**Problem:** 12 - 20' in repaired_problem_only.text, 'Problem-only repair did not show the saved main problem.', failures)
    _expect('What Math problem should we work on?' not in repaired_problem_only.text, 'Problem-only repair fell back to the generic Math prompt.', failures)

    safe_topic_reassurance = guard.validate(
        'Sure, we can move to fractions. The earlier practice question will not count against you.',
        state.model_copy(update={'current_question': '', 'current_step': '', 'problem_status': 'idle'}),
        intent_label='topic_switch',
    )
    _expect(safe_topic_reassurance.valid and not safe_topic_reassurance.repaired, 'Safe topic-switch reassurance was incorrectly repaired.', failures)

    tagged = guard.apply_metadata(state, wrong_math, 'test-model')
    _expect(tagged.last_response_validated and tagged.last_response_repaired, 'Response validation metadata was not stored.', failures)
    _expect(tagged.last_response_violations == wrong_math.violations, 'Response violations were not auditable in state.', failures)

    if failures:
        print('Tutor Math response-guard check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor Math response-guard check passed.')
    print('- Incorrect arithmetic and premature reveals are blocked.')
    print('- Replies stay on the active problem and ask at most one question.')
    print('- Every Math response records validation metadata for debugging.')


if __name__ == '__main__':
    main()
