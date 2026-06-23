from backend.app.models import TutoringState
from backend.app.services.tutor_math_response_guard import TutorMathResponseGuard
from backend.app.utils.tutor_surface_parity import tutor_practice_answer_reply


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _display_question(text: str) -> str:
    return text


def _practice_state(*, attempt_count: int = 0, hint_given: bool = False) -> TutoringState:
    question = 'What is 7 x 2?'
    return TutoringState(
        current_subject='Math',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
        active_problem=question,
        current_question=question,
        current_step=question,
        expected_answer='14',
        attempt_count=attempt_count,
        hint_given=hint_given,
        tutor_practice_question_id='phase4-guard-preserve',
        tutor_practice_hint_1='Think of 7 groups of 2.',
        tutor_practice_hint_2='Count by twos seven times.',
        tutor_practice_explanation='7 x 2 = 14.',
    )


def main() -> None:
    failures: list[str] = []
    guard = TutorMathResponseGuard()

    correct_reply, correct_state = tutor_practice_answer_reply(
        _practice_state(attempt_count=2, hint_given=True),
        '14',
        None,
        '',
        display_question=_display_question,
    )
    correct_guard = guard.validate(correct_reply, correct_state, intent_label='answer_current_step', source='deterministic-tutor-math-practice-check')
    _expect("Yes, that's correct!" in correct_reply, 'Tutor-practice correct reply did not confirm correctness.', failures)
    _expect(correct_state.problem_status == 'finished' and correct_state.final_answer == '14', 'Tutor-practice correct reply did not finish with the expected answer.', failures)
    _expect(correct_guard.valid and not correct_guard.repaired, 'Guard repaired a useful correct tutor-practice reply.', failures)
    _expect('keep the answer hidden' not in correct_guard.text.lower(), 'Guard hid a correct tutor-practice answer.', failures)

    first_wrong_reply, first_wrong_state = tutor_practice_answer_reply(
        _practice_state(attempt_count=1),
        '12',
        None,
        '',
        display_question=_display_question,
    )
    first_wrong_guard = guard.validate(first_wrong_reply, first_wrong_state, intent_label='answer_current_step', source='deterministic-tutor-math-practice-check')
    _expect(first_wrong_state.problem_status == 'tutor_practice' and first_wrong_state.attempt_count == 1, 'First wrong tutor-practice reply did not preserve active practice state.', failures)
    _expect(first_wrong_guard.valid and not first_wrong_guard.repaired, 'Guard erased a useful first-wrong hint reply.', failures)

    third_wrong_reply, third_wrong_state = tutor_practice_answer_reply(
        _practice_state(attempt_count=3, hint_given=True),
        '12',
        None,
        '',
        display_question=_display_question,
    )
    third_wrong_guard = guard.validate(third_wrong_reply, third_wrong_state, intent_label='answer_current_step', source='deterministic-tutor-math-practice-check')
    _expect("Nice effort. Let's finish this one together." in third_wrong_reply, 'Third wrong tutor-practice reply did not reveal consistently.', failures)
    _expect(third_wrong_state.problem_status == 'finished' and third_wrong_state.answer_revealed, 'Third wrong tutor-practice reply did not finish with reveal state.', failures)
    _expect(third_wrong_guard.valid and not third_wrong_guard.repaired, 'Guard erased a useful third-wrong reveal reply.', failures)

    if failures:
        print('Tutor Phase 4 guard-preserve check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 4 guard-preserve check passed.')
    print('- Guard preserves correct tutor-practice confirmations.')
    print('- Guard preserves useful wrong-answer hints and third-wrong reveals.')


if __name__ == '__main__':
    main()
