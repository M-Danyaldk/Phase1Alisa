import asyncio

from backend.app.assessment_bank import version_for
from backend.app.assessment_result_items import build_question_results
from backend.app.assessment_validation import validate_assessment_answer
from backend.app.main import _text_answer_check_reply
from backend.app.models import AssessmentRequest, ChatHistoryItem, StudentProfile, TutoringState
from backend.app.services.tutor_answer_checker import TutorAnswerChecker
from backend.app.tutoring_logic import build_chat_directives, update_tutoring_state_after_reply
from backend.app.utils.multi_step_progress import (
    advance_structured_math_problem,
    build_structured_retry_reply,
    build_structured_step_reply,
    current_step_expression,
    has_structured_math_problem,
    update_multi_step_progress,
)


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def main() -> None:
    failures: list[str] = []

    # Structured math planning and progression across different operator patterns.
    math_cases = [
        ('5/6 + 7/8 * (8/9 + 9)', ['8/9 + 9', '7/8 * 89/9', '5/6 + 623/72'], '683/72'),
        ('12 + 3 * 4', ['3 * 4', '12 + 12'], '24'),
        ('18 - (4 + 5)', ['4 + 5', '18 - 9'], '9'),
        ('3/4 * 2/5 + 1/10', ['3/4 * 2/5', '3/10 + 1/10'], '2/5'),
    ]
    for problem, expected_steps, final_answer in math_cases:
        state = update_multi_step_progress(problem, TutoringState(current_subject='Math'))
        _expect(has_structured_math_problem(state), f'Structured math was not detected for {problem!r}.', failures)
        actual_steps = [step.expression for step in state.ordered_steps]
        _expect(actual_steps == expected_steps, f'Step plan mismatch for {problem!r}: {actual_steps!r}.', failures)
        running = state
        previous = state
        for step in expected_steps:
            previous = running
            running = advance_structured_math_problem(running, running.expected_answer)
        _expect(running.final_answer == final_answer, f'Final answer mismatch for {problem!r}: {running.final_answer!r}.', failures)
        final_reply = build_structured_step_reply(previous, running)
        _expect('Final answer:' in final_reply, f'Final structured reply missing final answer label for {problem!r}.', failures)

    # Structured retry replies should stay anchored to the current step.
    retry_state = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    retry_state = retry_state.model_copy(update={'attempt_count': 1})
    retry_one = build_structured_retry_reply(retry_state, 1)
    _expect('Main problem:' in retry_one and 'Current step: Step A' in retry_one, 'First structured retry reply did not include main problem and current step.', failures)
    retry_two = build_structured_retry_reply(retry_state.model_copy(update={'attempt_count': 2}), 2)
    _expect('Hint:' in retry_two and 'Turn 9 into 81/9' in retry_two, 'Second structured retry reply did not give the stronger targeted hint.', failures)

    # Short numeric reply should count as answer attempt, not a new problem.
    answer_state = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    history = [ChatHistoryItem(role='msalisia', content=answer_state.current_question)]
    _, _, _, answered_state = build_chat_directives('88/9', history, answer_state)
    _expect(answered_state.attempt_count == 1, 'Short math reply was not counted as the first answer attempt.', failures)
    _expect(answered_state.attempts_per_step.get(answered_state.current_step_id or '') == 1, 'Per-step attempt memory did not update on short math reply.', failures)

    # Helper branch and queued follow-up question flow.
    base_state = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    _, helper_task, helper_step, helper_state = build_chat_directives('what is numerator?', [], base_state)
    _expect(helper_state.helper_branch.status == 'active', 'First side question did not open helper branch.', failures)
    _expect(helper_task == 'what is numerator?', 'Helper branch did not focus first on the side question.', failures)
    _expect(current_step_expression(helper_state) == helper_step, 'Helper branch lost the original math step reference.', failures)
    returned_state = update_tutoring_state_after_reply(
        helper_state,
        'what is numerator?',
        'A numerator is the top number in a fraction. Now back to our problem. What is 8 / 9 + 9?',
    )
    _expect(returned_state.helper_branch.status == 'completed', 'Helper branch was not marked completed after reply.', failures)
    _expect(returned_state.current_question == 'What is 8 / 9 + 9?', 'Main problem was not restored after helper reply.', failures)
    _, queued_task, queued_step, queued_state = build_chat_directives(
        'what is denominator?',
        [ChatHistoryItem(role='msalisia', content=returned_state.current_question)],
        returned_state,
    )
    _expect(queued_task == base_state.main_problem, 'Second side question did not re-anchor to the main problem first.', failures)
    _expect(queued_step == base_state.current_step, 'Second side question did not keep the original current step.', failures)
    _expect(
        [item.question for item in queued_state.queued_followup_questions] == ['what is denominator?'],
        'Second side question was not queued for later.',
        failures,
    )

    finished_math = base_state
    while has_structured_math_problem(finished_math):
        finished_math = advance_structured_math_problem(finished_math, finished_math.expected_answer)
    finished_math = finished_math.model_copy(update={'queued_followup_questions': queued_state.queued_followup_questions})
    _, followup_task, _, followup_state = build_chat_directives('ok', [], finished_math)
    _expect(followup_task == 'what is denominator?', 'Queued follow-up was not surfaced after finishing the main problem.', failures)
    _expect(followup_state.helper_branch.status == 'active', 'Queued follow-up did not reopen as an active helper branch.', failures)

    # Explicit task switching should allow leaving the old problem.
    switch_state = update_multi_step_progress('12 + 3 * 4', TutoringState(current_subject='Math'))
    switch_history = [ChatHistoryItem(role='msalisia', content=switch_state.current_question)]
    switch_directives, switch_task, _, switch_next_state = build_chat_directives(
        'switch to 15 - 7 instead',
        switch_history,
        switch_state,
    )
    switch_text = ' '.join(switch_directives).lower()
    _expect('explicitly wants to switch tasks' in switch_text, 'Switch-task intent did not add the explicit switch directive.', failures)
    _expect(switch_task == 'switch to 15 - 7 instead', 'Switch-task flow did not move to the new requested task.', failures)
    _expect(switch_next_state.helper_branch.status != 'active', 'Switch-task flow incorrectly opened a helper branch.', failures)

    # Short rude or frustrated inputs should not be graded as answers when they are tutor concerns.
    concern_history = [ChatHistoryItem(role='msalisia', content='What is 8 / 9 + 9?')]
    _, _, _, concern_state = build_chat_directives(
        'what is going on here, you forgot the problem',
        concern_history,
        base_state.model_copy(update={'attempt_count': 1}),
    )
    _expect(concern_state.attempt_count == 0, 'Tutor-concern input was still counted as an answer attempt.', failures)
    _expect(concern_state.current_question == '', 'Tutor-concern input should clear answer-attempt state for re-grounding.', failures)

    # Repeated interruptions while the main problem is still unfinished should keep queueing later questions.
    _, chain_task, chain_step, chain_state = build_chat_directives(
        'what is a whole number?',
        [ChatHistoryItem(role='msalisia', content=returned_state.current_question)],
        queued_state,
    )
    _expect(chain_task == base_state.main_problem, 'Repeated helper interruption did not re-anchor to the main problem first.', failures)
    _expect(chain_step == base_state.current_step, 'Repeated helper interruption lost the original current step.', failures)
    _expect(
        [item.question for item in chain_state.queued_followup_questions] == ['what is denominator?', 'what is a whole number?'],
        'Repeated helper interruption did not keep queueing later questions.',
        failures,
    )

    # Assessment-side Writing and ELA validation across multiple answer shapes.
    writing_questions = version_for('Writing', 4, 1).questions
    ela_questions = version_for('ELA', 4, 1).questions
    validation_cases = [
        (writing_questions[0], 'Practice helps me get better at hard things.', 'correct'),
        (writing_questions[0], 'practice helps', 'incorrect'),
        (writing_questions[1], 'Practice builds skill because it helps you improve. It gives you another chance to learn. It also helps you feel more confident.', 'correct'),
        (writing_questions[1], 'Practice helps because you learn more. It helps.', 'partially_correct'),
        (writing_questions[2], 'The lesson was helpful because the teacher showed clear examples.', 'correct'),
        (ela_questions[0], 'jumped', 'correct'),
        (ela_questions[2], 'She does not want to go.', 'correct'),
    ]
    for question, answer, expected_status in validation_cases:
        result = validate_assessment_answer(question, answer)
        _expect(result.status == expected_status, f'Validation mismatch for {question.question!r}: got {result.status!r}, expected {expected_status!r}.', failures)

    # Child-facing assessment result details should stay specific, not vague.
    assessment_payload = AssessmentRequest(
        student=StudentProfile(name='Dam', grade=4),
        subject='Writing',
        grade=4,
        questions=[question.question for question in writing_questions],
        question_ids=[question.id for question in writing_questions],
        answers=[
            'Makes things clear.',
            'Practice helps because you learn more. It helps.',
            'The lesson was helpful because the teacher showed clear examples.',
        ],
        assessment_version=1,
    )
    question_results = build_question_results(assessment_payload)
    _expect(question_results[0].status == 'incorrect', 'Writing check-in Q1 should still be marked incorrect for a fragment answer.', failures)
    _expect('clear complete sentence' in question_results[0].child_feedback.lower(), 'Writing Q1 child feedback did not explain the sentence issue clearly.', failures)
    _expect(question_results[1].status == 'partially_correct', 'Writing check-in Q2 should be partially correct for a short explanation.', failures)
    _expect('three complete sentences' in question_results[1].child_feedback.lower(), 'Writing Q2 child feedback did not explain the missing writing target clearly.', failures)
    _expect(question_results[2].status == 'correct', 'Writing check-in Q3 should be correct for a stronger revised sentence.', failures)

    # Live tutor checker and deterministic non-math reply path.
    checker = TutorAnswerChecker()
    tutor_cases = [
        ('Writing', 'Write one clear sentence about why practice matters.', 'Practice helps me get better every day.', 'correct'),
        ('Writing', 'Write 3 sentences that explain why practice builds skill.', 'Practice helps because you learn more. It helps.', 'partially_correct'),
        ('ELA', 'Fix this sentence: she dont want to go', 'She does not want to go.', 'correct'),
    ]
    for subject, prompt, answer, expected_status in tutor_cases:
        checked = await checker.check(subject, prompt, answer)
        _expect(checked.status == expected_status, f'Live tutor check mismatch for {subject} prompt {prompt!r}: got {checked.status!r}, expected {expected_status!r}.', failures)

    text_state = TutoringState(
        current_subject='Writing',
        current_question='Write 3 sentences that explain why practice builds skill.',
        current_step='Write 3 sentences that explain why practice builds skill.',
        expected_answer='Three connected explanatory sentences with a clear reason and details.',
        attempt_count=2,
        mode='practice',
        status='waiting_for_student',
        active_problem='Write 3 sentences that explain why practice builds skill.',
    )
    partial_check = await checker.check(
        'Writing',
        text_state.current_question,
        'Practice helps because you learn more. It helps.',
        text_state.expected_answer,
    )
    partial_reply = _text_answer_check_reply(partial_check, text_state)
    _expect('Try the same question one more time' in partial_reply, 'Deterministic writing partial reply did not keep the student on the same question.', failures)
    _expect('full three-sentence target' in partial_reply, 'Deterministic writing partial reply did not explain the reason clearly.', failures)

    if failures:
        print('Tutor architecture check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor architecture check passed.')
    print('- Structured math handles multiple operator patterns and final answers.')
    print('- Structured retry replies stay anchored to the main problem and current step.')
    print('- Short numeric replies are treated as answers, not fresh problems.')
    print('- Helper branches return to the main problem and queue extra side questions.')
    print('- Queued follow-ups reappear after the main problem is finished.')
    print('- Explicit subject/task switching can leave the old problem cleanly.')
    print('- Tutor-concern inputs are re-grounded instead of graded as answers.')
    print('- Repeated helper interruptions keep queueing later questions instead of drifting.')
    print('- Writing and ELA assessment validation handles correct, partial, and incorrect cases.')
    print('- Child-facing assessment feedback explains what needs work more clearly.')
    print('- Live Writing and ELA tutor checks can score common prompts locally.')


if __name__ == '__main__':
    asyncio.run(main())
