from backend.app.models import TutoringState
from backend.app.utils.tutor_surface_parity import math_fallback_reply


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []

    active_step = TutoringState(
        current_subject='Math',
        current_question='What is -9 + 5?',
        current_step='What is -9 + 5?',
        expected_answer='-4',
        attempt_count=1,
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    )
    active_reply = math_fallback_reply(active_step)
    _expect(
        'Here is the saved step to try.' in active_reply
        and 'What is -9 + 5?' in active_reply,
        'Active Math fallback did not stay grounded on the current step.',
        failures,
    )
    _expect(
        "Let's stay with the current Math problem" not in active_reply,
        'Active Math fallback still used the old repetitive repair wording.',
        failures,
    )

    continuation_state = TutoringState(
        current_subject='Math',
        problem_status='finished',
        mode='awaiting_more_practice_choice',
        status='waiting_for_student',
        continuation_origin_problem='-9 + 5',
        continuation_origin_answer='-4',
    )
    continuation_reply = math_fallback_reply(continuation_state)
    _expect(
        'another practice question' in continuation_reply.lower()
        and 'new math problem' in continuation_reply.lower(),
        'Finished Math fallback did not stay in continuation-choice mode.',
        failures,
    )

    idle_state = TutoringState(current_subject='Math')
    idle_reply = math_fallback_reply(idle_state)
    _expect(
        'send me the math problem you want to work on' in idle_reply.lower(),
        'Idle Math fallback did not ask for a fresh Math problem cleanly.',
        failures,
    )

    if failures:
        print('Tutor fallback-tightening check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor fallback-tightening check passed.')
    print('- Active Math fallback stays on the verified step instead of drifting into generic tutoring.')
    print('- Finished Math fallback stays inside continuation choice instead of reopening broad chat fallback.')
    print('- Idle Math fallback asks for one clear Math problem in short child-friendly language.')


if __name__ == '__main__':
    main()
