import asyncio

from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.services.tutor_intent_classifier import TutorIntentClassifier
from backend.app.services.tutor_math_normalizer import TutorMathNormalizer
from backend.app.services.tutor_subject_classifier import TutorSubjectClassifier
from backend.app.tutoring_logic import build_chat_directives, detect_off_subject_request
from backend.app.utils.multi_step_progress import (
    advance_structured_math_problem,
    build_structured_roadmap_reply,
    current_step_expression,
    has_structured_math_problem,
    update_multi_step_progress,
)


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def main() -> None:
    failures: list[str] = []

    # Broad structured-math matrix across mixed operator families.
    math_cases = [
        ('(12 - 5) + 3 * 2', '13'),
        ('3/4 * 2/5 + 1/10', '2/5'),
        ('3/4 / 2/5 + 1/10', '79/40'),
        ('5/6 - 1/3 + 2/9', '13/18'),
        ('2 + 3 * 4 - 5', '9'),
        ('(7/8 + 1/8) * 3', '3'),
    ]
    for problem, final_answer in math_cases:
        state = update_multi_step_progress(problem, TutoringState(current_subject='Math'))
        _expect(has_structured_math_problem(state), f'Edge matrix did not structure {problem!r}.', failures)
        roadmap = build_structured_roadmap_reply(state)
        _expect('**Main problem:**' in roadmap and 'Step roadmap:' in roadmap, f'Roadmap formatting broke for {problem!r}.', failures)

        safety_counter = 0
        running = state
        while has_structured_math_problem(running):
            safety_counter += 1
            _expect(safety_counter <= 10, f'Step progression loop did not finish for {problem!r}.', failures)
            running = advance_structured_math_problem(running, running.expected_answer)
        _expect(running.final_answer == final_answer, f'Final answer mismatch for {problem!r}: {running.final_answer!r}.', failures)

    # Normalization matrix for word math and malformed symbolic input.
    normalizer = TutorMathNormalizer()
    normalization_cases = [
        ('twelve minus five plus three times two', '12 - 5 + 3 * 2', '13'),
        ('5 // 6 + 7/8', '5/6 + 7/8', '41/24'),
        ('((12+3)', '((12+3))', '15'),
        ('nine over eight plus seven over four times eight over nine', '9/8 + 7/4 * 8/9', '193/72'),
        ('3/4 divided by 2/5 plus 1/10', '3/4 / 2/5 + 1/10', '79/40'),
        ('9/8 plus 7/4 * 8/9', '9/8 + 7/4 * 8/9', '193/72'),
        ('5/6 minus 1/3 + 2/9', '5/6 - 1/3 + 2/9', '13/18'),
        ('one hundred twenty three minus forty five', '123 - 45', '78'),
        ('one hundred and twenty three minus forty five', '123 - 45', '78'),
        ('one hundred two plus eighteen', '102 + 18', '120'),
        ('ninety six divided by three', '96/3', '32'),
        ('one hundred forty four over twelve plus six', '144/12 + 6', '18'),
    ]
    for raw_message, normalized_expression, final_answer in normalization_cases:
        result = await normalizer.normalize_if_needed('Math', raw_message, TutoringState(current_subject='Math'))
        _expect(result.normalized_expression == normalized_expression, f'Normalizer mismatch for {raw_message!r}: {result.normalized_expression!r}.', failures)
        if result.normalized_expression:
            planned = update_multi_step_progress(result.normalized_expression, TutoringState(current_subject='Math'))
            if has_structured_math_problem(planned):
                while has_structured_math_problem(planned):
                    planned = advance_structured_math_problem(planned, planned.expected_answer)
                _expect(planned.final_answer == final_answer, f'Normalized expression did not finish correctly for {raw_message!r}.', failures)

    shorthand_cases = [
        ('2x(3+4)', '2 * (3+4)', '14'),
        ('3(4+5)', '3 * (4+5)', '27'),
        ('(2+3)4', '(2+3) * 4', '20'),
        ('(1/2)(8)', '(1/2) * (8)', '4'),
        ('2(3)(4)', '2 * (3) * (4)', '24'),
    ]
    for raw_message, extracted_expression, final_answer in shorthand_cases:
        _expect(not normalizer.should_use_fallback('Math', raw_message, TutoringState(current_subject='Math')), f'Shorthand math incorrectly triggered fallback for {raw_message!r}.', failures)
        planned = update_multi_step_progress(raw_message, TutoringState(current_subject='Math'))
        _expect(has_structured_math_problem(planned), f'Shorthand math did not become a structured problem for {raw_message!r}.', failures)
        _expect(planned.main_problem == extracted_expression, f'Shorthand math normalized to the wrong planner expression for {raw_message!r}: {planned.main_problem!r}.', failures)
        while has_structured_math_problem(planned):
            planned = advance_structured_math_problem(planned, planned.expected_answer)
        _expect(planned.final_answer == final_answer, f'Shorthand math did not finish correctly for {raw_message!r}.', failures)

    # Routing matrix for current-step answers, related questions, and true new problems.
    base = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    history = [ChatHistoryItem(role='msalisia', content=base.current_question)]

    _, task_answer, step_answer, state_answer = build_chat_directives('89/9', history, base)
    _expect(state_answer.attempt_count == 1, 'Numeric current-step answer was not counted as an answer attempt.', failures)
    _expect(step_answer == current_step_expression(base), 'Current-step answer routing lost the current step.', failures)
    _expect(state_answer.main_problem == base.main_problem, 'Current-step answer routing lost the main problem state.', failures)

    _, task_related, step_related, state_related = build_chat_directives('how do you get 89/9 from this step?', history, base)
    _expect(state_related.helper_branch.status == 'active', 'Related helper question did not open helper mode.', failures)
    _expect(task_related == 'how do you get 89/9 from this step?', 'Related helper question did not take task focus.', failures)
    _expect(step_related == current_step_expression(base), 'Related helper question lost the original step.', failures)

    _, task_new, step_new, state_new = build_chat_directives('14 + 6', history, base)
    _expect(state_new.mode == 'clarify_new_problem', 'New raw math expression did not enter clarify-new-problem mode.', failures)
    _expect(state_new.pending_new_problem == '14 + 6', 'New raw math expression was not stored for clarification.', failures)
    _expect(task_new == base.main_problem and step_new == current_step_expression(base), 'New-problem clarification did not stay anchored to the main problem.', failures)

    # Off-subject matrix across direct detection and classifier fallback.
    subject_classifier = TutorSubjectClassifier()
    _expect(detect_off_subject_request('Math', 'how do leaves make food?', base), 'Math did not directly block a science interruption.', failures)
    _expect(detect_off_subject_request('ELA', '7/8 + 1/8', TutoringState(current_subject='ELA')), 'ELA did not block a math expression.', failures)
    _expect(detect_off_subject_request('Writing', '12 x 4', TutoringState(current_subject='Writing')), 'Writing did not block a math expression.', failures)
    _expect(
        not detect_off_subject_request('Writing', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='Writing')),
        'Writing mixed-case prompt was incorrectly treated as off-subject.',
        failures,
    )
    _expect(
        detect_off_subject_request('ELA', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='ELA')),
        'ELA mixed-case prompt was not redirected into writing.',
        failures,
    )

    _expect(subject_classifier.should_use_fallback('Math', 'how do machines work?', base), 'Subject fallback did not trigger for an uncertain non-math question.', failures)
    fallback_subject = await subject_classifier.classify_if_needed('Math', 'how do machines work?', base)
    _expect(fallback_subject.label == 'off_subject', f'Subject fallback did not classify uncertain non-math math interruption safely: {fallback_subject.label!r}.', failures)
    _expect(fallback_subject.confidence in {'low', 'medium', 'high'}, 'Subject fallback returned an invalid confidence.', failures)
    _expect(
        not subject_classifier.should_use_fallback('Writing', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='Writing')),
        'Writing subject fallback incorrectly triggered for a writing task that mentions reading.',
        failures,
    )

    # Intent fallback matrix for ambiguous mid-flow language.
    intent_classifier = TutorIntentClassifier()
    _expect(intent_classifier.should_use_fallback('Math', 'maybe do 12-20 first', history, base), 'Intent fallback did not trigger for ambiguous switch wording.', failures)
    switch_intent = await intent_classifier.classify_if_needed('Math', 'maybe do 12-20 first', history, base)
    _expect(
        switch_intent.label == 'switch_request'
        or (switch_intent.label == 'clarification_about_context' and switch_intent.needs_clarification),
        f'Intent fallback neither classified nor safely clarified ambiguous switch wording: {switch_intent.label!r}.',
        failures,
    )

    _expect(intent_classifier.should_use_fallback('Math', 'i think it becomes 89/9', history, base), 'Intent fallback did not trigger for ambiguous answer wording.', failures)
    answer_intent = await intent_classifier.classify_if_needed('Math', 'i think it becomes 89/9', history, base)
    _expect(
        answer_intent.label == 'answer_current_step'
        or (answer_intent.label == 'clarification_about_context' and answer_intent.needs_clarification),
        f'Intent fallback neither classified nor safely clarified ambiguous answer wording: {answer_intent.label!r}.',
        failures,
    )

    if failures:
        print('Tutor edge matrix check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor edge matrix check passed.')
    print('- Mixed operator math plans finish correctly across several expression shapes.')
    print('- Word-math and malformed symbolic input normalize into usable expressions.')
    print('- Mid-flow answers, helper questions, and new raw expressions route to different states.')
    print('- Direct subject boundaries and uncertain subject fallback both behave safely.')
    print('- Ambiguous medium-confidence switch/answer wording is held for clarification instead of mutating state.')


if __name__ == '__main__':
    asyncio.run(main())
