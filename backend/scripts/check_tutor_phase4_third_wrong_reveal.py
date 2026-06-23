from backend.app.models import TutoringState
from backend.app.services.tutor_math_response_guard import TutorMathResponseGuard
from backend.app.utils.tutor_surface_parity import tutor_practice_answer_reply


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _display_question(text: str) -> str:
    return text


def _practice_state(
    *,
    question: str,
    expected_answer: str,
    explanation: str,
    skill: str,
) -> TutoringState:
    return TutoringState(
        current_subject='Math',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
        active_problem=question,
        current_question=question,
        current_step=question,
        expected_answer=expected_answer,
        attempt_count=3,
        hint_given=True,
        answer_revealed=True,
        tutor_practice_question_id=f'phase4-third-wrong-{skill}',
        tutor_practice_topic=skill,
        tutor_practice_hint_1='Use the important numbers from the question.',
        tutor_practice_hint_2='Check the answer form before you reply.',
        tutor_practice_explanation=explanation,
    )


def main() -> None:
    failures: list[str] = []
    guard = TutorMathResponseGuard()
    cases = [
        {
            'label': 'single-step arithmetic',
            'question': 'What is 7 x 2?',
            'expected': '14',
            'wrong': '12',
            'explanation': '7 x 2 = 14.',
            'must_include': '14',
        },
        {
            'label': 'fraction comparison',
            'question': 'Which is larger: 5/6 or 4/6?',
            'expected': '5/6',
            'wrong': '4/6',
            'explanation': '5/6 is larger than 4/6 because 5 is greater than 4.',
            'must_include': '5/6',
        },
        {
            'label': 'word-problem practice',
            'question': 'There are 28 pencils. If 4 pencils go in each cup, how many cups are needed?',
            'expected': '7',
            'wrong': '5',
            'explanation': '28 / 4 = 7, so 7 cups are needed.',
            'must_include': '7',
        },
        {
            'label': 'worded unit-fraction answer',
            'question': 'How many fourths make one whole?',
            'expected': '4',
            'wrong': '3',
            'explanation': 'Four fourths make one whole.',
            'must_include': 'The answer is 4.',
        },
        {
            'label': 'yes-no concept',
            'question': 'Is 3/6 equivalent to 1/2?',
            'expected': 'yes',
            'wrong': 'no',
            'explanation': 'Yes. 3/6 simplifies to 1/2.',
            'must_include': 'yes',
        },
    ]

    for case in cases:
        state = _practice_state(
            question=case['question'],
            expected_answer=case['expected'],
            explanation=case['explanation'],
            skill=case['label'],
        )
        reply, next_state = tutor_practice_answer_reply(
            state,
            case['wrong'],
            None,
            '',
            display_question=_display_question,
        )
        guard_result = guard.validate(
            reply,
            next_state,
            intent_label='answer_current_step',
            source='deterministic-tutor-math-practice-check',
        )
        lower_reply = reply.lower()
        _expect("Nice effort. Let's finish this one together." in reply, f"{case['label']} reveal used inconsistent opening.", failures)
        _expect('Would you like another practice question?' in reply, f"{case['label']} reveal did not enter continuation choice.", failures)
        _expect(case['must_include'].lower() in lower_reply, f"{case['label']} reveal omitted the explicit expected answer.", failures)
        _expect(next_state.problem_status == 'finished', f"{case['label']} reveal did not finish the practice task.", failures)
        _expect(next_state.mode == 'awaiting_more_practice_choice', f"{case['label']} reveal did not enter continuation mode.", failures)
        _expect(next_state.answer_revealed, f"{case['label']} reveal state did not mark answer_revealed.", failures)
        _expect(next_state.final_answer == case['expected'], f"{case['label']} reveal stored the wrong final answer.", failures)
        _expect(not next_state.current_question and not next_state.expected_answer, f"{case['label']} reveal kept a gradeable stale prompt.", failures)
        _expect(guard_result.valid and not guard_result.repaired, f"{case['label']} reveal was erased by the Math response guard.", failures)

    if failures:
        print('Tutor Phase 4 third-wrong reveal check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 4 third-wrong reveal check passed.')
    print('- Tutor-practice third wrong attempts reveal consistently across question types.')
    print('- Reveals finish the task, preserve final answer, and are accepted by the response guard.')


if __name__ == '__main__':
    main()
