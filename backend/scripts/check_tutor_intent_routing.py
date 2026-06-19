import asyncio

from backend.app.main import (
    _emotion_interruption_reply,
    _math_topic_switch_state,
    _should_grade_tutor_practice,
)
from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.services.tutor_intent_classifier import TutorIntentClassifier
from backend.app.tutoring_logic import build_chat_directives


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def main() -> None:
    failures: list[str] = []
    classifier = TutorIntentClassifier()
    state = TutoringState(
        current_subject='Math',
        active_problem='11 x 6',
        current_step='What is 11 x 6?',
        current_question='What is 11 x 6?',
        expected_answer='66',
        attempt_count=1,
        tutor_practice_question_id='practice-11x6',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    history = [ChatHistoryItem(role='msalisia', content='Question: What is 11 x 6?')]

    cases = [
        ('66', 'answer_current_step'),
        ('I want to learn fractions', 'topic_switch'),
        ('There are 7 boxes and each box holds 2 balls. How many balls fill the boxes?', 'new_problem'),
        ('Why do we multiply by 6?', 'related_question'),
        ('Help me understand this', 'help_request'),
        ('I am tired', 'emotion'),
        ("Why is this so hard? I'm frustrated", 'emotion'),
        ("I don't feel safe", 'emotion'),
        ('I need a break', 'pause'),
        ("I'm back", 'resume'),
        ('You already asked this question', 'meta_feedback'),
    ]
    results = {}
    for message, expected_label in cases:
        result = await classifier.classify_if_needed('Math', message, history, state)
        results[message] = result
        _expect(result.label == expected_label, f'{message!r} classified as {result.label!r}, expected {expected_label!r}.', failures)

    _expect(results['I want to learn fractions'].requested_topic == 'fraction', 'Fraction topic request did not preserve its requested topic.', failures)
    _expect(results['I am tired'].emotion == 'tired', 'Tired emotional message did not preserve its emotion label.', failures)
    _expect(_should_grade_tutor_practice(state, results['66'].label), 'A numeric practice answer was not allowed into grading.', failures)
    for message, _ in cases[1:]:
        _expect(not _should_grade_tutor_practice(state, results[message].label), f'Non-answer message {message!r} was allowed into practice grading.', failures)

    for message in ('I want to learn fractions', 'I am tired', 'Why do we multiply by 6?', 'Help me understand this'):
        result = results[message]
        _, _, _, routed_state = build_chat_directives(
            message,
            history,
            state,
            assisted_intent_label=result.label,
        )
        _expect(routed_state.attempt_count != state.attempt_count + 1, f'Non-answer message {message!r} increased the attempt count.', failures)

    emotional_state = state.model_copy(update={'student_answer': 'I am tired', 'correctness_status': ''})
    emotional_reply = _emotion_interruption_reply('tired', emotional_state)
    _expect('problem is saved' in emotional_reply.lower(), 'Emotional reply did not preserve the active problem explicitly.', failures)
    _expect('good try' not in emotional_reply.lower(), 'Emotional reply used wrong-answer language.', failures)

    switched_state = _math_topic_switch_state(state, 'I want to learn fractions', 'fraction')
    _expect(switched_state.skill == 'fraction', 'Topic switch did not preserve the requested Math topic.', failures)
    _expect(switched_state.attempt_count == 0, 'Topic switch carried a wrong-answer attempt into the new topic.', failures)
    _expect(not switched_state.current_question and not switched_state.active_problem, 'Topic switch kept the abandoned routine practice question active.', failures)

    if failures:
        print('Tutor intent routing check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor intent routing check passed.')
    print('- Numeric answers remain gradeable.')
    print('- Topic switches, word problems, related questions, help, emotions, pauses, and tutor feedback are not graded as answers.')
    print('- Emotional messages preserve the problem without wrong-answer language.')
    print('- Math topic switches clear routine practice attempts and retain the requested topic.')


if __name__ == '__main__':
    asyncio.run(main())
