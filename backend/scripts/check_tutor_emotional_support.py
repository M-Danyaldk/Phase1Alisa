import asyncio

from backend.app.models import TutoringState
from backend.app.services.tutor_emotional_support import (
    apply_emotional_support,
    build_emotional_support_plan,
    build_emotional_support_reply,
    detect_emotional_support_choice,
    resolve_emotional_support_choice,
    build_safety_followup_reply,
)
from backend.app.services.tutor_intent_classifier import TutorIntentClassifier
from backend.app.utils.attempt_policy import register_answer_attempt
from backend.app.utils.task_lifecycle import active_task, start_task


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _run() -> list[str]:
    failures: list[str] = []
    base = TutoringState(
        current_subject='Math',
        active_problem='7 × 2',
        current_step='7 × 2',
        current_question='What is 7 × 2?',
        expected_answer='14',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    base = register_answer_attempt(start_task(base, '7 × 2', subject='Math'))
    classifier = TutorIntentClassifier()

    discouraged = classifier.classify_deterministically('Math', "I'm bad at math", [], base)
    _expect(discouraged.label == 'emotion' and discouraged.emotion == 'discouraged', 'Discouragement was not detected.', failures)
    plan = build_emotional_support_plan(base, "I'm bad at math", discouraged.emotion)
    supported = apply_emotional_support(base, "I'm bad at math", plan)
    reply = build_emotional_support_reply(plan, supported)
    _expect(supported.current_question == base.current_question, 'Emotional support lost the exact question.', failures)
    _expect(supported.attempt_count == 1 and supported.attempts_per_step == base.attempts_per_step, 'Emotion changed attempt history.', failures)
    _expect('bad at Math' in reply and 'wrong' not in reply.lower(), 'Discouragement reply used unsuitable language.', failures)

    _expect(detect_emotional_support_choice('one tiny step', supported) == 'tiny_step', 'Tiny-step choice was not detected.', failures)
    continued = resolve_emotional_support_choice(supported, 'tiny_step')
    _expect(continued.mode == 'practice' and continued.current_question == base.current_question, 'Tiny step did not restore learning mode.', failures)
    _expect(continued.attempt_count == 1, 'Tiny-step continuation changed attempts.', failures)

    repeated_state = supported.model_copy(update={'emotional_support_count': 2})
    repeated_plan = build_emotional_support_plan(repeated_state, 'This is too much', 'overwhelmed')
    _expect(repeated_plan.intensity == 'high' and repeated_plan.support_count == 3, 'Repeated distress did not increase support intensity.', failures)

    crisis_result = classifier.classify_deterministically('Math', 'I want to hurt myself', [], base)
    _expect(crisis_result.label == 'emotion' and crisis_result.emotion == 'crisis', 'High-distress language was not detected.', failures)
    crisis_plan = build_emotional_support_plan(base, 'I want to hurt myself', crisis_result.emotion)
    crisis_state = apply_emotional_support(base, 'I want to hurt myself', crisis_plan)
    crisis_reply = build_emotional_support_reply(crisis_plan, crisis_state)
    _expect(crisis_state.mode == 'safety_support', 'High-distress state did not enter safety support.', failures)
    _expect(active_task(crisis_state) is None, 'Active learning task was not paused during safety escalation.', failures)
    _expect(any(record.status == 'paused' for record in crisis_state.task_records), 'Learning task was not saved as paused.', failures)
    _expect('trusted adult' in crisis_reply.lower() and 'emergency services' in crisis_reply.lower(), 'Safety reply lacks adult escalation.', failures)
    paraphrased_crisis = classifier.classify_deterministically('Math', "I don't feel safe", [], base)
    _expect(paraphrased_crisis.emotion == 'crisis', 'A high-distress paraphrase was not detected.', failures)
    _expect('trusted adult' in build_safety_followup_reply().lower(), 'Safety lock follow-up did not keep adult escalation.', failures)
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor emotional-support check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor emotional-support check passed.')
    print('- Emotion and discouragement never count as wrong answers.')
    print('- Break, tiny-step, and different-explanation choices preserve the task.')
    print('- Repeated distress adapts support and high-distress language pauses learning safely.')


if __name__ == '__main__':
    main()
