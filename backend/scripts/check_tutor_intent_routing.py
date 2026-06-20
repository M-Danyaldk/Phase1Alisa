import asyncio

from backend.app.main import (
    _emotion_interruption_reply,
    _math_topic_switch_reply,
    _math_topic_switch_state,
    _should_grade_tutor_practice,
)
from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.services.tutor_intent_classifier import TutorIntentClassifier
from backend.app.tutoring_logic import (
    _looks_like_new_problem,
    build_chat_directives,
    build_conversation_control_reply,
    extract_followup_step,
)


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
        ('hi', 'greeting'),
        ('ok', 'acknowledge'),
        ('ok proceed with this problem', 'continue_current'),
        ('I want to learn fractions', 'topic_switch'),
        ('fractions', 'topic_switch'),
        ('frction', 'topic_switch'),
        ('teach me fracton', 'topic_switch'),
        ('lcm', 'topic_switch'),
        ('least commen multiple', 'topic_switch'),
        ('There are 7 boxes and each box holds 2 balls. How many balls fill the boxes?', 'new_problem'),
        ('Why do we multiply by 6?', 'related_question'),
        ('why do we multiply fractions here?', 'related_question'),
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
    _expect(results['fractions'].requested_topic == 'fraction', 'Bare fraction topic did not normalize to fraction.', failures)
    _expect(results['frction'].requested_topic == 'fraction', 'Misspelled fraction topic did not normalize to fraction.', failures)
    _expect(results['lcm'].requested_topic == 'lcm', 'Bare LCM topic did not normalize to lcm.', failures)
    _expect(results['least commen multiple'].requested_topic == 'lcm', 'Misspelled LCM topic did not normalize to lcm.', failures)
    _expect(results['why do we multiply fractions here?'].requested_topic == '', 'Active-problem fraction explanation was mistaken for a topic switch.', failures)
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

    greeting_reply = build_conversation_control_reply(TutoringState(current_subject='Math'), 'greeting', 'Ahsan')
    _expect(greeting_reply.startswith('Hi Ahsan!'), 'Greeting reply did not greet the student.', failures)
    _expect("that's good to hear" not in greeting_reply.lower(), 'Greeting reply still assumed a positive mood.', failures)
    acknowledgement_reply = build_conversation_control_reply(state, 'acknowledge', 'Ahsan')
    _expect('11 x 6' in acknowledgement_reply.lower(), 'Acknowledgement did not stay attached to the active Math step.', failures)

    ordinary_sentence = 'No, I want you to answer the question I just asked.'
    _expect(not _looks_like_new_problem(ordinary_sentence), 'A long conversational sentence was still classified as a new problem.', failures)
    _expect(_looks_like_new_problem('What is 64 + 55?'), 'An explicit Math expression was not classified as a new problem.', failures)

    grounded_followup = extract_followup_step(
        'Try adding the ones first: 8 + 2. What do you get?',
        'Math',
    )
    _expect('8 + 2' in grounded_followup, 'Generic Math follow-up was not grounded in its nearby expression.', failures)
    _expect(
        not extract_followup_step('Nice work. Are you ready?', 'Math'),
        'An ungrounded conversational question was stored as a Math step.',
        failures,
    )

    emotional_state = state.model_copy(update={'student_answer': 'I am tired', 'correctness_status': ''})
    emotional_reply = _emotion_interruption_reply('tired', emotional_state)
    _expect('problem is saved' in emotional_reply.lower(), 'Emotional reply did not preserve the active problem explicitly.', failures)
    _expect('good try' not in emotional_reply.lower(), 'Emotional reply used wrong-answer language.', failures)

    switched_state = _math_topic_switch_state(state, 'I want to learn fractions', 'fraction')
    _expect(switched_state.skill == 'fraction', 'Topic switch did not preserve the requested Math topic.', failures)
    _expect(switched_state.attempt_count == 0, 'Topic switch carried a wrong-answer attempt into the new topic.', failures)
    _expect(switched_state.mode == 'tutor_practice_question', 'Topic switch did not start a topic lesson practice state.', failures)
    _expect(switched_state.status == 'waiting_for_student', 'Topic lesson state is not waiting for the student answer.', failures)
    _expect(switched_state.problem_status == 'tutor_practice', 'Topic lesson was not stored as tutor practice.', failures)
    _expect(switched_state.current_question == 'What fraction shows 1 part out of 4 equal parts?', 'Fraction topic lesson did not store the starter question.', failures)
    _expect(switched_state.active_problem == switched_state.current_question, 'Topic lesson active problem and current question drifted.', failures)
    _expect(switched_state.expected_answer == '1/4', 'Fraction topic lesson did not store the expected answer.', failures)
    _expect(switched_state.tutor_practice_question_id == 'topic-lesson-fraction', 'Fraction topic lesson did not store a stable question id.', failures)
    _expect('topic-lesson-fraction' in switched_state.recent_tutor_practice_question_ids, 'Fraction topic lesson was not added to recent practice ids.', failures)
    switch_reply = _math_topic_switch_reply('fraction')
    _expect('wrong answer' not in switch_reply.lower(), 'Topic-switch reply still contains response-guard wrong-answer wording.', failures)
    _expect('fractions' in switch_reply.lower(), 'Topic-switch reply did not mention the requested topic.', failures)
    _expect('A fraction shows part of a whole.' in switch_reply, 'Fraction topic reply did not include the mini explanation.', failures)
    _expect('Example:' in switch_reply, 'Fraction topic reply did not include an example.', failures)
    _expect(switched_state.current_question in switch_reply, 'Fraction topic reply did not ask the stored starter question.', failures)

    lcm_state = _math_topic_switch_state(state, 'teach me lcm', 'lcm')
    lcm_reply = _math_topic_switch_reply('lcm')
    _expect(lcm_state.skill == 'lcm', 'LCM topic switch did not preserve the requested topic.', failures)
    _expect(lcm_state.current_question == 'What is the LCM of 3 and 4?', 'LCM topic lesson did not store the starter question.', failures)
    _expect(lcm_state.expected_answer == '12', 'LCM topic lesson did not store the expected answer.', failures)
    _expect('LCM means Least Common Multiple' in lcm_reply, 'LCM topic reply did not include the mini explanation.', failures)

    if failures:
        print('Tutor intent routing check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor intent routing check passed.')
    print('- Numeric answers remain gradeable.')
    print('- Greetings, acknowledgements, continuations, topic switches, word problems, help, emotions, pauses, and tutor feedback are not graded as answers.')
    print('- Long conversational messages are not mistaken for Math problems.')
    print('- Generic follow-up wording is anchored to a verified Math expression instead of replacing it.')
    print('- Emotional messages preserve the problem without wrong-answer language.')
    print('- Math topic switches clear routine practice attempts, teach a mini lesson, and start a checked starter question.')


if __name__ == '__main__':
    asyncio.run(main())
