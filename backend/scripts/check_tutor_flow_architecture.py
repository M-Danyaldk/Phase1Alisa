import asyncio

from backend.app.assessment_bank import version_for
from backend.app.assessment_result_items import build_question_results
from backend.app.assessment_validation import validate_assessment_answer
from backend.app.main import _matching_structured_step, _reading_context_question, _should_send_structured_roadmap, _structured_future_step_redirect_reply, _text_answer_check_reply, _writing_context_question
from backend.app.models import AssessmentRequest, ChatHistoryItem, StudentProfile, TutoringState
from backend.app.services.voice_service import (
    _matching_structured_step as _voice_matching_structured_step,
    _reading_context_question as _voice_reading_context_question,
    _should_send_structured_roadmap as _voice_should_send_structured_roadmap,
    _structured_future_step_redirect_reply as _voice_structured_future_step_redirect_reply,
    _writing_context_question as _voice_writing_context_question,
)
from backend.app.services.tutor_answer_checker import AnswerCheckResult, TutorAnswerChecker
from backend.app.services.llm.router import LLMRouter
from backend.app.services.tutor_intent_classifier import IntentClassificationResult, TutorIntentClassifier
from backend.app.services.tutor_math_normalizer import MathNormalizationResult, TutorMathNormalizer
from backend.app.services.tutor_subject_classifier import SubjectClassificationResult, TutorSubjectClassifier
from backend.app.tutoring_logic import (
    build_subject_boundary_reply,
    build_chat_directives,
    build_new_problem_clarification_reply,
    build_resume_paused_problem_reply,
    build_switch_confirmation_reply,
    detect_action_intent,
    detect_off_subject_request,
    update_tutoring_state_after_reply,
)
from backend.app.utils.multi_step_progress import (
    advance_structured_math_problem,
    build_structured_roadmap_reply,
    build_structured_retry_reply,
    build_structured_step_focus_reply,
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
        roadmap_reply = build_structured_roadmap_reply(state)
        _expect("We're working on:" in roadmap_reply, f'Roadmap reply missing main problem label for {problem!r}.', failures)
        _expect('Step roadmap:' in roadmap_reply, f'Roadmap reply missing roadmap label for {problem!r}.', failures)
        _expect(state.ordered_steps[0].label in roadmap_reply, f'Roadmap reply missing first step label for {problem!r}.', failures)
        _expect('Easy idea:' in roadmap_reply, f'Roadmap reply missing child-friendly explanation label for {problem!r}.', failures)
        _expect("Now let's start with" in roadmap_reply, f'Roadmap reply did not announce the first step for {problem!r}.', failures)
        running = state
        previous = state
        for step in expected_steps:
            previous = running
            running = advance_structured_math_problem(running, running.expected_answer)
        _expect(running.final_answer == final_answer, f'Final answer mismatch for {problem!r}: {running.final_answer!r}.', failures)
        final_reply = build_structured_step_reply(previous, running)
        _expect('Final answer:' in final_reply, f'Final structured reply missing final answer label for {problem!r}.', failures)
        step_completion_reply = build_structured_step_reply(state, advance_structured_math_problem(state, state.expected_answer))
        _expect(f'{state.ordered_steps[0].label} complete:' in step_completion_reply, f'Step completion reply missing explicit completion label for {problem!r}.', failures)
        _expect('Now the problem becomes:' in step_completion_reply, f'Step completion reply missing updated problem label for {problem!r}.', failures)
        _expect("Now let's move to" in step_completion_reply, f'Step completion reply missing next-step transition for {problem!r}.', failures)
        _expect('Easy idea:' in step_completion_reply, f'Step completion reply missing child-friendly explanation label for {problem!r}.', failures)
        _expect('For now, keep your answer as a fraction' in step_completion_reply or 'Write the whole number' in step_completion_reply or 'Write just the value' in step_completion_reply, f'Step completion reply missing answer guidance for {problem!r}.', failures)

    roadmap_visibility_state = update_multi_step_progress('9/8 + 7/4 * 8/9 + (10 * 23/2)', TutoringState(current_subject='Math'))
    roadmap_visibility_reply = build_structured_roadmap_reply(roadmap_visibility_state)
    _expect('Step A: Solve 10/1 × 23/2' not in roadmap_visibility_reply, 'Roadmap should use the display expression form, not normalized internals.', failures)
    _expect('Step A: Solve 10 × 23/2' in roadmap_visibility_reply, 'Roadmap did not show the current explicit Step A expression.', failures)
    _expect('Step B: Solve 7/4 × 8/9' in roadmap_visibility_reply, 'Roadmap did not show the future explicit multiplication step.', failures)
    _expect('Step C: Add the fraction results' in roadmap_visibility_reply, 'Roadmap revealed the future fraction-add expression instead of a safe label.', failures)
    _expect('Step D: Add the final results' in roadmap_visibility_reply, 'Roadmap revealed the final transformed addition instead of a safe label.', failures)

    fresh_entry_previous_state = TutoringState(
        current_subject='Math',
        current_question='What is 9 / 8?',
        current_step='What is 9 / 8?',
        attempt_count=1,
        mode='practice',
        status='waiting_for_student',
        active_problem='What is 9 / 8?',
    )
    _, fresh_entry_task, fresh_entry_step, fresh_entry_state = build_chat_directives(
        '9/8 + 7/4 * 8/9 + (20 * 23/2)',
        [ChatHistoryItem(role='msalisia', content='What is 9 / 8?')],
        fresh_entry_previous_state,
    )
    fresh_entry_state = update_multi_step_progress('9/8 + 7/4 * 8/9 + (20 * 23/2)', fresh_entry_state)
    _expect(has_structured_math_problem(fresh_entry_state), 'Fresh full math entry did not initialize structured progression from an older question state.', failures)
    _expect(fresh_entry_task == '9/8 + 7/4 * 8/9 + (20 * 23/2)', 'Fresh full math entry did not replace the older quick question as the active task.', failures)
    _expect(fresh_entry_step == '', 'Fresh full math entry should not stay locked on the old quick-question step.', failures)
    _expect(
        _should_send_structured_roadmap(
            'Math',
            fresh_entry_previous_state,
            fresh_entry_state.model_copy(update={'attempt_count': 1}),
            '9/8 + 7/4 * 8/9 + (20 * 23/2)',
            fresh_entry_previous_state.problem_id,
        ),
        'Fresh full math entry did not force the roadmap when older attempt state was still present.',
        failures,
    )
    _expect(
        _voice_should_send_structured_roadmap(
            'Math',
            fresh_entry_previous_state,
            fresh_entry_state.model_copy(update={'attempt_count': 1}),
            '9/8 + 7/4 * 8/9 + (20 * 23/2)',
            fresh_entry_previous_state.problem_id,
        ),
        'Voice fresh full math entry did not force the roadmap when older attempt state was still present.',
        failures,
    )

    # Structured retry replies should stay anchored to the current step.
    retry_state = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    retry_state = retry_state.model_copy(update={'attempt_count': 1})
    retry_one = build_structured_retry_reply(retry_state, 1)
    _expect("Let's stay with Step A" in retry_one, 'First structured retry reply did not stay anchored to the current step.', failures)
    _expect('For now, keep your answer as a fraction' in retry_one, 'First structured retry reply did not include child-friendly answer guidance.', failures)
    _expect('Good try.' in retry_one, 'First structured retry reply did not use the calmer retry wording.', failures)
    _expect('The whole number needs the same bottom number as the fraction first.' in retry_one, 'First structured retry reply did not point to the next move clearly.', failures)
    retry_two = build_structured_retry_reply(retry_state.model_copy(update={'attempt_count': 2}), 2)
    _expect('We need matching pieces first.' in retry_two and 'Turn 9 into 81/9.' in retry_two, 'Second structured retry reply did not give the stronger targeted hint.', failures)
    fraction_multiply_case = update_multi_step_progress('7/4 * 8/9 + 1/2', TutoringState(current_subject='Math'))
    _expect('For fraction multiplication, do the top numbers together first.' in build_structured_retry_reply(fraction_multiply_case.model_copy(update={'attempt_count': 1}), 1), 'Fraction multiplication retry did not give a compact top/bottom hint.', failures)
    fraction_multiply_retry_two = build_structured_retry_reply(fraction_multiply_case.model_copy(update={'attempt_count': 2}), 2)
    _expect('Start with the top numbers: 7 × 8.' in fraction_multiply_retry_two, 'Fraction multiplication second hint did not scaffold the top numbers first.', failures)
    fraction_equivalent_state = advance_structured_math_problem(fraction_multiply_case, '56/36')
    _expect(fraction_equivalent_state.completed_steps[-1].endswith('= 14/9'), 'Equivalent fraction answer did not store the canonical structured step result.', failures)
    _expect(fraction_equivalent_state.step_results.get(fraction_multiply_case.current_step_id) == '14/9', 'Equivalent fraction answer polluted structured step_results.', failures)
    fraction_add_case = update_multi_step_progress('9/8 + 14/9 + 1', TutoringState(current_subject='Math'))
    fraction_add_retry_one = build_structured_retry_reply(fraction_add_case.model_copy(update={'attempt_count': 1}), 1)
    _expect('The bottom numbers are different, so we cannot add yet.' in fraction_add_retry_one, 'Unlike-denominator addition first hint did not point to the denominator mismatch.', failures)
    fraction_add_retry_two = build_structured_retry_reply(fraction_add_case.model_copy(update={'attempt_count': 2}), 2)
    _expect('8 and 9 both fit into 72.' in fraction_add_retry_two, 'Unlike-denominator addition second hint did not give the stronger common-bottom scaffold.', failures)
    whole_plus_fraction_state = update_multi_step_progress('9/8 + 7/4 * 8/9 + (10 * 23/2)', TutoringState(current_subject='Math'))
    while whole_plus_fraction_state.current_step != '193/72 + 115':
        whole_plus_fraction_state = advance_structured_math_problem(whole_plus_fraction_state, whole_plus_fraction_state.expected_answer)
    _expect('The whole number needs the same bottom number as the fraction first.' in build_structured_retry_reply(whole_plus_fraction_state.model_copy(update={'attempt_count': 1}), 1), 'Whole-number-plus-fraction retry did not point to the fraction rename.', failures)
    parentheses_state = update_multi_step_progress('9/8 + 7/4 * 8/9 + (20 * 23/2)', TutoringState(current_subject='Math'))
    parentheses_retry_one = build_structured_retry_reply(parentheses_state.model_copy(update={'attempt_count': 1}), 1)
    _expect('First do 20 × 23 = 460.' in parentheses_retry_one, 'Parentheses first hint did not show the immediate multiplication result.', failures)
    _expect('What is 460 ÷ 2?' in parentheses_retry_one, 'Parentheses first hint did not ask the aligned next question.', failures)
    parentheses_retry_two = build_structured_retry_reply(parentheses_state.model_copy(update={'attempt_count': 2}), 2)
    _expect('First do 20 × 23 = 460.' in parentheses_retry_two and 'What is 460 ÷ 2?' in parentheses_retry_two, 'Parentheses second hint did not keep the aligned next question.', failures)

    explain_again_state = update_multi_step_progress('9/8 + 7/4 * 8/9 + (20 * 23/2)', TutoringState(current_subject='Math'))
    explain_again_reply = build_structured_step_focus_reply(
        explain_again_state,
        intro='No problem. Let me say it in a simpler way.',
    )
    _expect('20 × 23/2' in explain_again_reply, 'Explain-again same-step reply did not stay anchored to the real current step.', failures)
    _expect('What is 20 × 23/2?' in explain_again_reply, 'Explain-again same-step reply did not end with the original current-step question.', failures)
    _expect('What is 20 × 23?' not in explain_again_reply, 'Explain-again same-step reply drifted into a hidden micro-step question.', failures)
    _expect(detect_action_intent('which step?') == 'clarify_prompt', 'Clarification phrase was not recognized as a clarification action.', failures)
    _expect(detect_action_intent('what do you mean') == 'clarify_prompt', 'Clarification wording was not classified as clarify_prompt.', failures)
    clarification_history = [ChatHistoryItem(role='msalisia', content=explain_again_state.current_question)]
    _, clarification_task, clarification_step, clarification_state = build_chat_directives(
        'which step?',
        clarification_history,
        explain_again_state,
    )
    _expect(clarification_state.attempt_count == 0, 'Clarification phrase was incorrectly counted as an answer attempt.', failures)
    _expect(clarification_task == explain_again_state.main_problem, 'Clarification phrase did not stay anchored to the main problem.', failures)
    _expect(clarification_step == explain_again_state.current_step, 'Clarification phrase did not stay anchored to the current step.', failures)
    clarification_reply = build_structured_step_focus_reply(
        explain_again_state,
        intro='No problem. Let me show exactly what this step is asking.',
    )
    _expect('This part: Step A' in clarification_reply, 'Clarification same-step reply did not restate the current step.', failures)
    _expect('What is 20 × 23/2?' in clarification_reply, 'Clarification same-step reply did not return to the original step question.', failures)

    # Short numeric reply should count as answer attempt, not a new problem.
    answer_state = update_multi_step_progress('5/6 + 7/8 * (8/9 + 9)', TutoringState(current_subject='Math'))
    history = [ChatHistoryItem(role='msalisia', content=answer_state.current_question)]
    _, _, _, answered_state = build_chat_directives('88/9', history, answer_state)
    _expect(answered_state.attempt_count == 1, 'Short math reply was not counted as the first answer attempt.', failures)
    _expect(answered_state.attempts_per_step.get(answered_state.current_step_id or '') == 1, 'Per-step attempt memory did not update on short math reply.', failures)

    _, _, _, phrase_answer_state = build_chat_directives('i think it is 88/9', history, answer_state)
    _expect(phrase_answer_state.attempt_count == 1, 'Short phrased math reply was not counted as the first answer attempt.', failures)

    clarify_state = answer_state.model_copy(update={
        'mode': 'clarify_new_problem',
        'status': 'waiting_for_clarification',
        'pending_input_kind': 'new_math_expression',
        'pending_new_problem': '12 - 20',
    })
    _, clarify_current_task, clarify_current_step, clarify_current_state = build_chat_directives(
        'part of this problem',
        [ChatHistoryItem(role='msalisia', content='part of this problem, or a new problem?')],
        clarify_state,
    )
    _expect(clarify_current_state.mode == 'practice', 'Clarification reply for the current problem did not restore normal practice mode.', failures)
    _expect(clarify_current_state.pending_new_problem == '' and clarify_current_state.pending_input_kind == '', 'Clarification reply for the current problem did not clear the pending clarification fields.', failures)
    _expect(clarify_current_task == answer_state.main_problem, 'Clarification reply for the current problem did not re-anchor the active task.', failures)
    _expect(clarify_current_step == answer_state.current_step, 'Clarification reply for the current problem did not restore the current step.', failures)

    _, clarify_new_task, clarify_new_step, clarify_new_state = build_chat_directives(
        'solve the new problem first',
        [ChatHistoryItem(role='msalisia', content='part of this problem, or a new problem?')],
        clarify_state,
    )
    _expect(clarify_new_state.mode == 'solve' and clarify_new_state.status == 'solving', 'Clarification reply for the new problem did not switch into solving mode.', failures)
    _expect(clarify_new_state.pending_new_problem == '' and clarify_new_state.pending_input_kind == '', 'Clarification reply for the new problem did not clear the pending clarification fields.', failures)
    _expect(clarify_new_task == '12 - 20', 'Clarification reply for the new problem did not promote the pending new problem into the active task.', failures)
    _expect(clarify_new_step == '', 'Clarification reply for the new problem should not keep the old step active.', failures)
    _expect(clarify_new_state.paused_main_problem == answer_state.main_problem, 'Clarification reply for the new problem did not preserve the original main problem for return.', failures)

    # Low-confidence intent fallback should classify ambiguous messages without taking over tutor control.
    classifier = TutorIntentClassifier()
    _expect(
        classifier.should_use_fallback('Math', 'i think it becomes 89/9', history, answer_state),
        'Intent fallback did not trigger for an ambiguous current-step answer.',
        failures,
    )

    async def fake_answer_classifier(subject, message, history_items, state):
        return IntentClassificationResult(label='answer_current_step', confidence='high', reason='Student appears to be giving the step answer.')

    classifier._classify_with_llm = fake_answer_classifier
    answer_intent = await classifier.classify_if_needed('Math', 'i think it becomes 89/9', history, answer_state)
    _, _, _, llm_answer_state = build_chat_directives('i think it becomes 89/9', history, answer_state, assisted_intent_label=answer_intent.label)
    _expect(answer_intent.label == 'answer_current_step', 'Intent fallback did not return the mocked answer_current_step label.', failures)
    _expect(llm_answer_state.attempt_count == 1, 'Intent fallback did not convert the ambiguous answer into a checked step attempt.', failures)

    async def fake_related_classifier(subject, message, history_items, state):
        return IntentClassificationResult(label='related_question', confidence='high', reason='Student is asking about the current step.')

    classifier._classify_with_llm = fake_related_classifier
    related_intent = await classifier.classify_if_needed('Math', 'no i mean how did that become 89/9?', history, answer_state)
    _, _, _, llm_related_state = build_chat_directives('no i mean how did that become 89/9?', history, answer_state, assisted_intent_label=related_intent.label)
    _expect(llm_related_state.helper_branch.status == 'active', 'Intent fallback did not convert the ambiguous question into a related helper branch.', failures)

    # Symbolic step echoes should be recognized as selecting the current step, not solving it.
    roadmap_state = update_multi_step_progress('5/6 + 3/4 * 2/3', TutoringState(current_subject='Math'))
    current_step_match = _matching_structured_step(roadmap_state, roadmap_state.current_step)
    _expect(current_step_match is not None and current_step_match.step_id == roadmap_state.current_step_id, 'Current structured step expression was not recognized as the active step.', failures)
    future_step_match = _matching_structured_step(roadmap_state, '5/6 + 1/2')
    _expect(future_step_match is not None and future_step_match.step_id != roadmap_state.current_step_id, 'Future structured step expression was not recognized inside the roadmap.', failures)
    redirect_reply = _structured_future_step_redirect_reply(roadmap_state, future_step_match)
    _expect('comes later' in redirect_reply and 'This part:' in redirect_reply, 'Future structured step redirect reply did not keep the tutor anchored on the current step.', failures)
    voice_current_step_match = _voice_matching_structured_step(roadmap_state, roadmap_state.current_step)
    _expect(voice_current_step_match is not None and voice_current_step_match.step_id == roadmap_state.current_step_id, 'Voice path did not recognize the active structured step expression.', failures)
    voice_future_step_match = _voice_matching_structured_step(roadmap_state, '5/6 + 1/2')
    _expect(voice_future_step_match is not None and voice_future_step_match.step_id != roadmap_state.current_step_id, 'Voice path did not recognize a future structured step expression.', failures)
    voice_redirect_reply = _voice_structured_future_step_redirect_reply(roadmap_state, voice_future_step_match)
    _expect('comes later' in voice_redirect_reply and 'This part:' in voice_redirect_reply, 'Voice future structured step redirect reply did not stay anchored on the current step.', failures)

    restarted_state = advance_structured_math_problem(roadmap_state, roadmap_state.expected_answer)
    restarted_state = update_multi_step_progress('5/6 + 3/4 * 2/3', restarted_state)
    _expect(restarted_state.current_step_index == 0, 'Re-entering the same full problem did not restart at the first step.', failures)
    _expect(restarted_state.completed_steps == [], 'Re-entering the same full problem did not clear completed steps.', failures)
    _expect(restarted_state.current_question == roadmap_state.current_question, 'Re-entering the same full problem did not restore the first question.', failures)
    _expect(restarted_state.problem_status == 'awaiting_step', 'Re-entering the same full problem did not return to awaiting-step status.', failures)

    finished_restart_state = update_multi_step_progress('12 + 3 * 4', TutoringState(current_subject='Math'))
    while has_structured_math_problem(finished_restart_state):
        finished_restart_state = advance_structured_math_problem(finished_restart_state, finished_restart_state.expected_answer)
    finished_restart_state = update_multi_step_progress('12 + 3 * 4', finished_restart_state)
    _expect(finished_restart_state.current_step_index == 0, 'Finished structured problem did not restart cleanly when entered again.', failures)
    _expect(finished_restart_state.final_answer == '', 'Finished structured problem restart did not clear the old final answer.', failures)
    _expect(
        _voice_should_send_structured_roadmap(
            'Math',
            restarted_state.model_copy(update={
                'completed_steps': ['Step A'],
                'completed_step_results': {'step_a': '1/2'},
                'step_results': {'step_a': '1/2'},
                'current_step_index': 1,
                'problem_status': 'awaiting_step',
            }),
            roadmap_state,
            '5/6 + 3/4 * 2/3',
            roadmap_state.problem_id,
        ),
        'Voice roadmap parity check did not trigger for re-entering the same finished or partially completed problem.',
        failures,
    )

    async def fake_switch_classifier(subject, message, history_items, state):
        return IntentClassificationResult(label='switch_request', confidence='high', reason='Student wants to do the new problem first.')

    classifier._classify_with_llm = fake_switch_classifier
    switch_intent = await classifier.classify_if_needed('Math', 'maybe do 12-20 first', history, answer_state)
    switch_directives_llm, switch_task_llm, _, switch_state_llm = build_chat_directives(
        'maybe do 12-20 first',
        history,
        answer_state,
        assisted_intent_label=switch_intent.label,
    )
    _expect('explicitly wants to switch tasks' in ' '.join(switch_directives_llm).lower(), 'Intent fallback did not turn the ambiguous request into a switch directive.', failures)
    _expect(switch_task_llm == 'maybe do 12-20 first', 'Intent fallback did not preserve the new switched task text.', failures)
    _expect(switch_state_llm.paused_main_problem == answer_state.main_problem, 'Intent fallback switch path did not park the original main problem.', failures)

    # Math normalization fallback should repair malformed or word-based math only when deterministic parsing is weak.
    math_normalizer = TutorMathNormalizer()
    _expect(
        math_normalizer.should_use_fallback('Math', 'nine over eight plus seven over four times eight over nine', TutoringState(current_subject='Math')),
        'Math normalizer did not trigger for math written mostly in words.',
        failures,
    )
    _expect(
        math_normalizer.should_use_fallback('Math', '9/8 + 7/4 * 8/9 + (10 * 23/2', TutoringState(current_subject='Math')),
        'Math normalizer did not trigger for mismatched parentheses in a math expression.',
        failures,
    )
    _expect(
        not math_normalizer.should_use_fallback('Math', '9/8 + 7/4 * 8/9 + (10 * 23/2)', TutoringState(current_subject='Math')),
        'Math normalizer incorrectly triggered for a clean symbolic expression.',
        failures,
    )

    async def fake_math_normalizer(message, state):
        return MathNormalizationResult(
            normalized_expression='9/8 + 7/4 * 8/9',
            confidence='high',
            reason='Converted number words into a clean symbolic expression.',
        )

    math_normalizer._normalize_with_llm = fake_math_normalizer
    normalized_math = await math_normalizer.normalize_if_needed(
        'Math',
        'nine over eight plus seven over four times eight over nine',
        TutoringState(current_subject='Math'),
    )
    _expect(normalized_math.normalized_expression == '9/8 + 7/4 * 8/9', 'Math normalizer did not preserve the mocked normalized expression.', failures)
    normalized_state = update_multi_step_progress(normalized_math.normalized_expression, TutoringState(current_subject='Math'))
    _expect(has_structured_math_problem(normalized_state), 'Normalized math expression did not become a structured math problem.', failures)
    _expect(normalized_state.current_step == '7/4 * 8/9', 'Normalized math expression did not produce the expected first structural step.', failures)

    # Local classifier fallback should stay machine-readable and useful when no live model reply is available.
    router = LLMRouter()
    local_math_result = router._local_fallback(
        'classifier',
        fallback_used=True,
        system='You normalize Grades 3-6 student math input into clean symbolic math. Return compact JSON only with keys: normalized_expression, confidence, reason.',
        user='Student math input: nine over eight plus seven over four times eight over nine',
    )
    local_math_payload = MathNormalizationResult.model_validate_json(local_math_result.text)
    _expect(local_math_payload.normalized_expression == '9 / 8 + 7 / 4 * 8 / 9', 'Local classifier fallback did not return a normalized word-math expression.', failures)
    _expect(local_math_payload.confidence == 'medium', 'Local classifier fallback did not return medium confidence for normalized word-math.', failures)

    local_intent_result = router._local_fallback(
        'classifier',
        fallback_used=True,
        system='You classify a child tutor message for Grades 3-6. Return compact JSON only with keys: label, confidence, reason.',
        user='Student message: maybe do 12-20 first',
    )
    local_intent_payload = IntentClassificationResult.model_validate_json(local_intent_result.text)
    _expect(local_intent_payload.label == 'switch_request', 'Local classifier fallback did not classify an ambiguous switch request.', failures)

    local_subject_result = router._local_fallback(
        'classifier',
        fallback_used=True,
        system='You classify whether a Grades 3-6 student message fits the current tutor subject. Return compact JSON only with keys: label, confidence, reason.',
        user='Current tutor subject: Math\nStudent message: how do leaves make food?',
    )
    local_subject_payload = SubjectClassificationResult.model_validate_json(local_subject_result.text)
    _expect(local_subject_payload.label == 'off_subject', 'Local classifier fallback did not classify a science-style math interruption as off-subject.', failures)

    # Mid-flow raw expressions that do not match the current step should trigger clarification, not grading.
    clarify_directives, clarify_task, clarify_step, clarify_state = build_chat_directives('12-20', history, answer_state)
    clarify_reply = build_new_problem_clarification_reply(clarify_state)
    _expect(clarify_state.mode == 'clarify_new_problem', 'Unrelated raw math expression did not enter clarification mode.', failures)
    _expect(clarify_state.pending_new_problem == '12-20', 'Pending new problem was not saved for clarification.', failures)
    _expect(clarify_state.attempt_count == 0, 'Clarification case should not count as an answer attempt.', failures)
    _expect(clarify_task == answer_state.main_problem, 'Clarification case did not keep the original main problem active.', failures)
    _expect(clarify_step == answer_state.current_step, 'Clarification case did not preserve the current step.', failures)
    _expect('looks like a new math problem' in clarify_reply.lower(), 'Clarification reply did not say the new input looks like a new problem.', failures)
    _expect('tell me which one you want' in clarify_reply.lower(), 'Clarification reply did not use the fixed friendly choice wording.', failures)

    # Related mid-flow math questions should open a side branch instead of a clarification gate.
    _, related_task, related_step, related_state = build_chat_directives(
        'how did 8/9 + 9 become 89/9?',
        history,
        answer_state,
    )
    _expect(related_state.helper_branch.status == 'active', 'Related mid-flow math question did not open a helper branch.', failures)
    _expect(related_task == 'how did 8/9 + 9 become 89/9?', 'Related mid-flow math question did not focus on the related question first.', failures)
    _expect(related_step == answer_state.current_step, 'Related mid-flow math question lost the original current step.', failures)
    _, related_task_two, related_step_two, related_state_two = build_chat_directives(
        'how do you get 89/9 from this step?',
        history,
        answer_state,
    )
    _expect(related_state_two.helper_branch.status == 'active', 'Current-step wording did not open a helper branch for a related math question.', failures)
    _expect(related_task_two == 'how do you get 89/9 from this step?', 'Current-step wording did not focus on the related helper question first.', failures)
    _expect(related_step_two == answer_state.current_step, 'Current-step wording lost the original current step.', failures)

    # Explicit switching should park the old problem and allow a compact return later.
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
    _expect(switch_next_state.paused_main_problem == switch_state.main_problem, 'Switch-task flow did not park the original main problem.', failures)
    switch_reply = build_switch_confirmation_reply(switch_next_state, '15 - 7')
    _expect('solve this new problem first' in switch_reply.lower(), 'Switch confirmation reply did not explain the new-problem-first behavior.', failures)
    _expect('bring you back' in switch_reply.lower(), 'Switch confirmation reply did not promise a return to the parked problem.', failures)
    switched_finished_state = update_tutoring_state_after_reply(
        switch_next_state,
        'switch to 15 - 7 instead',
        '15 - 7 = 8.\n\nFinal answer: 8.',
    )
    _expect(switched_finished_state.mode == 'resume_paused_problem', 'Finished switched problem did not enter paused-problem resume mode.', failures)
    _, resumed_task, resumed_step, resumed_state = build_chat_directives('ok', [], switched_finished_state)
    resume_reply = build_resume_paused_problem_reply(resumed_state)
    _expect(resumed_state.mode == 'resume_paused_problem_notice', 'Paused problem did not reopen in resume notice mode.', failures)
    _expect(resumed_task == switch_state.main_problem, 'Paused problem resume did not restore the original main problem.', failures)
    _expect(resumed_step == switch_state.current_step, 'Paused problem resume did not restore the original current step.', failures)
    _expect(resumed_state.expected_answer == switch_state.expected_answer, 'Paused problem resume did not restore the expected answer for the current step.', failures)
    resumed_check = await TutorAnswerChecker().check('Math', resumed_state.current_question, switch_state.expected_answer, resumed_state.expected_answer)
    _expect(resumed_check.status == 'correct', 'Paused problem resume could not grade the restored current step answer.', failures)
    _expect('we finished the new problem' in resume_reply.lower(), 'Resume reply did not mention finishing the temporary switched problem.', failures)
    _expect('now let\'s return to your main problem' in resume_reply.lower(), 'Resume reply did not use the compact return wording.', failures)

    # Non-math prompt lock should not rebuild the current question from stale assistant history.
    stale_history = [ChatHistoryItem(role='msalisia', content='Try this same question again:\nWhat is the cat doing?')]
    writing_state = TutoringState(current_subject='Writing')
    _, _, rebuilt_step, rebuilt_state = build_chat_directives('Sitting on mat', stale_history, writing_state)
    _expect(rebuilt_step == '', 'Writing flow incorrectly rebuilt the current step from assistant history.', failures)
    _expect(rebuilt_state.current_question == '', 'Writing flow incorrectly locked a stale assistant question into state.', failures)

    polluted_reply = _text_answer_check_reply(
        AnswerCheckResult(status='incorrect', feedback_note='Look back at the sentence and answer only what it asks.'),
        TutoringState(current_question='Try this same question again:\nWhat is the cat doing?', attempt_count=1),
    )
    _expect(polluted_reply.count('Try this same question again:') == 1, 'Text retry reply duplicated the retry wrapper when the stored prompt was polluted.', failures)
    _expect('What is the cat doing?' in polluted_reply, 'Text retry reply lost the cleaned question prompt.', failures)

    answer_checker = TutorAnswerChecker()
    writing_three_prompt_check = answer_checker._check_local_text_prompt(
        'Writing',
        'Write three sentences that explain why practice builds skill.',
        'Practice helps you improve. It helps you remember steps. It makes hard things easier over time.',
        '',
    )
    _expect(
        writing_three_prompt_check.status != 'unclear',
        'Local Writing grader did not recognize the "write three sentences" wording variant.',
        failures,
    )
    writing_revision_prompt_check = answer_checker._check_local_text_prompt(
        'Writing',
        'Make this sentence stronger: The lesson was good.',
        'The lesson was exciting because we got to build a volcano.',
        '',
    )
    _expect(
        writing_revision_prompt_check.status != 'unclear',
        'Local Writing grader did not recognize the shorter "make this sentence stronger" wording variant.',
        failures,
    )

    # Off-subject requests should be redirected back into the active subject.
    off_subject_math_state = answer_state
    _expect(detect_off_subject_request('Math', 'what is photosynthesis?', off_subject_math_state), 'Math tutor did not flag an obvious science question as off-subject.', failures)
    _expect(detect_off_subject_request('Math', 'how do leaves make food?', off_subject_math_state), 'Math tutor did not flag a science-style interruption as off-subject.', failures)
    _expect(detect_off_subject_request('Math', 'why do plants need sunlight?', off_subject_math_state), 'Math tutor did not flag another science-style interruption as off-subject.', failures)
    off_subject_math_reply = build_subject_boundary_reply('Math', off_subject_math_state)
    _expect('right now we are working on math' in off_subject_math_reply.lower(), 'Math subject boundary reply did not keep the tutor in math.', failures)
    _expect(answer_state.main_problem.lower() in off_subject_math_reply.lower(), 'Math subject boundary reply did not mention the active main problem.', failures)
    _expect(not detect_off_subject_request('Math', 'what is numerator?', off_subject_math_state), 'Math tutor incorrectly blocked a related math definition question.', failures)
    _expect(detect_off_subject_request('ELA', '7/8 + 1/8', TutoringState(current_subject='ELA')), 'Reading tutor did not flag a math expression as off-subject.', failures)
    _expect(detect_off_subject_request('Writing', '12 x 4', TutoringState(current_subject='Writing')), 'Writing tutor did not flag a math expression as off-subject.', failures)
    _expect(detect_off_subject_request('ELA', 'Write 3 sentences about why practice matters.', TutoringState(current_subject='ELA')), 'Reading tutor did not flag an obvious writing prompt as off-subject.', failures)
    _expect(detect_off_subject_request('Writing', 'What is the main idea of this passage?', TutoringState(current_subject='Writing')), 'Writing tutor did not flag an obvious reading prompt as off-subject.', failures)
    _expect(not detect_off_subject_request('ELA', 'What is the main idea of this passage?', TutoringState(current_subject='ELA')), 'Reading tutor incorrectly blocked a reading-comprehension prompt.', failures)
    _expect(not detect_off_subject_request('Writing', 'How can you make this sentence stronger?', TutoringState(current_subject='Writing')), 'Writing tutor incorrectly blocked a writing-revision prompt.', failures)
    _expect(
        not detect_off_subject_request('Writing', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='Writing')),
        'Writing tutor incorrectly blocked a writing prompt just because it mentioned reading.',
        failures,
    )
    _expect(
        detect_off_subject_request('ELA', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='ELA')),
        'ELA tutor did not redirect a writing prompt that happened to mention reading.',
        failures,
    )
    _expect(not detect_off_subject_request('Math', 'switch to reading', off_subject_math_state), 'Explicit subject switch should not be treated as an off-subject block.', failures)

    # Subject fallback should catch uncertain off-subject cases without overriding obvious in-subject prompts.
    subject_classifier = TutorSubjectClassifier()
    _expect(
        not subject_classifier.should_use_fallback('Math', 'how do leaves make food?', off_subject_math_state),
        'Subject fallback should not trigger once the science-style interruption is caught deterministically.',
        failures,
    )
    _expect(
        not subject_classifier.should_use_fallback('Math', 'what is numerator?', off_subject_math_state),
        'Subject fallback incorrectly triggered for an in-subject math definition question.',
        failures,
    )
    _expect(
        not subject_classifier.should_use_fallback('Writing', 'Write 3 sentences about why reading every day matters.', TutoringState(current_subject='Writing')),
        'Writing subject fallback incorrectly triggered for a writing task that mentioned reading.',
        failures,
    )

    async def fake_subject_classifier(subject, message, state):
        return SubjectClassificationResult(label='off_subject', confidence='high', reason='This is a science question, not math.')

    subject_classifier._classify_with_llm = fake_subject_classifier
    subject_result = await subject_classifier.classify_if_needed('Math', 'how do machines work?', off_subject_math_state)
    _expect(subject_result.label == 'off_subject', 'Subject fallback did not preserve the mocked off_subject label.', failures)

    async def fake_in_subject_classifier(subject, message, state):
        return SubjectClassificationResult(label='in_subject', confidence='high', reason='This is still about the current math topic.')

    subject_classifier._classify_with_llm = fake_in_subject_classifier
    in_subject_result = await subject_classifier.classify_if_needed('Math', 'how do we make equal pieces here?', off_subject_math_state)
    _expect(in_subject_result.label == 'in_subject', 'Subject fallback did not preserve the mocked in_subject label.', failures)

    _expect(detect_off_subject_request('ELA', 'help me with this paragraph', TutoringState(current_subject='ELA')), 'Reading tutor did not redirect a writing-style paragraph request.', failures)
    _expect(detect_off_subject_request('Writing', 'help me understand this passage', TutoringState(current_subject='Writing')), 'Writing tutor did not redirect a reading-style passage request.', failures)
    _expect(not detect_off_subject_request('ELA', 'can you help me with this text?', TutoringState(current_subject='ELA')), 'Reading tutor incorrectly blocked an in-subject text-help prompt.', failures)
    _expect(detect_off_subject_request('ELA', 'can you help me with this sentence?', TutoringState(current_subject='ELA')), 'Reading tutor did not redirect an ambiguous sentence-help prompt into writing.', failures)
    _expect(not detect_off_subject_request('Writing', 'can you help me with this sentence?', TutoringState(current_subject='Writing')), 'Writing tutor incorrectly blocked an in-subject sentence-help prompt.', failures)
    _expect(detect_off_subject_request('Writing', 'can you help me with this text?', TutoringState(current_subject='Writing')), 'Writing tutor did not redirect an ambiguous text-help prompt into reading.', failures)
    _expect(detect_off_subject_request('Writing', 'can you help me with this passage?', TutoringState(current_subject='Writing')), 'Writing tutor did not redirect a passage-help prompt into reading.', failures)

    _expect(
        not subject_classifier.should_use_fallback('ELA', 'can you help me with this text?', TutoringState(current_subject='ELA')),
        'ELA subject fallback still triggered for a text-help prompt that should now be recognized directly.',
        failures,
    )
    _expect(
        subject_classifier.should_use_fallback('ELA', 'can you help me with this thing?', TutoringState(current_subject='ELA')),
        'ELA subject fallback did not trigger for a truly unresolved shared-language prompt.',
        failures,
    )

    async def fake_ela_subject_classifier(subject, message, state):
        return SubjectClassificationResult(label='off_subject', confidence='high', reason='This is writing work, not reading.')

    subject_classifier._classify_with_llm = fake_ela_subject_classifier
    ela_subject_result = await subject_classifier.classify_if_needed('ELA', 'can you help me with this thing?', TutoringState(current_subject='ELA'))
    _expect(ela_subject_result.label == 'off_subject', 'ELA subject fallback did not preserve the mocked off_subject label for an unresolved shared-language prompt.', failures)

    local_writing_subject = await TutorSubjectClassifier().classify_if_needed(
        'Writing',
        'Write 3 sentences about why reading every day matters.',
        TutoringState(current_subject='Writing'),
    )
    _expect(local_writing_subject.label in {'', 'ambiguous'}, 'Writing fallback unexpectedly overrode a direct in-subject writing prompt.', failures)

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
    _expect(returned_state.current_question == base_state.current_question, 'Main problem was not restored after helper reply.', failures)
    _expect(returned_state.current_step_id == base_state.current_step_id, 'Helper branch did not restore the exact structured current step ID.', failures)
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
        (writing_questions[0], 'Practice practice practice practice practice.', 'incorrect'),
        (writing_questions[1], 'Practice builds skill because it helps you improve. It gives you another chance to learn. It also helps you feel more confident.', 'correct'),
        (writing_questions[1], 'Practice helps because you learn more. It helps.', 'partially_correct'),
        (writing_questions[1], 'Practice is good. Practice is good. Practice is good.', 'incorrect'),
        (writing_questions[2], 'The lesson was helpful because the teacher showed clear examples.', 'correct'),
        (writing_questions[2], 'The lesson was good.', 'partially_correct'),
        (writing_questions[2], 'Good lesson.', 'incorrect'),
        (ela_questions[0], 'jumped', 'correct'),
        (ela_questions[1], 'One helpful action made things better.', 'correct'),
        (ela_questions[1], 'The plant looked healthy after Mia helped.', 'partially_correct'),
        (ela_questions[1], 'It is about rain and weather.', 'incorrect'),
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

    weak_writing_payload = AssessmentRequest(
        student=StudentProfile(name='Dam', grade=4),
        subject='Writing',
        grade=4,
        questions=[question.question for question in writing_questions],
        question_ids=[question.id for question in writing_questions],
        answers=[
            'Practice practice practice practice practice.',
            'Practice is good. Practice is good. Practice is good.',
            'The lesson was good.',
        ],
        assessment_version=1,
    )
    weak_results = build_question_results(weak_writing_payload)
    _expect(weak_results[0].status == 'incorrect', 'Writing Q1 should reject heavy repetition without a clear sentence idea.', failures)
    _expect(weak_results[1].status == 'incorrect', 'Writing Q2 should reject repetitive three-sentence filler.', failures)
    _expect(weak_results[2].status == 'partially_correct', 'Writing Q3 should treat a weak revision attempt as partial, not correct.', failures)

    # Live tutor checker and deterministic non-math reply path.
    checker = TutorAnswerChecker()
    tutor_cases = [
        ('Writing', 'Write one clear sentence about why practice matters.', 'Practice helps me get better every day.', 'correct'),
        ('Writing', 'Write 3 sentences that explain why practice builds skill.', 'Practice helps because you learn more. It helps.', 'partially_correct'),
        ('Writing', 'Write 3 sentences that explain why practice builds skill.', 'Practice is good. Practice is good. Practice is good.', 'incorrect'),
        ('Writing', 'How can you make this sentence stronger: The lesson was good.?', 'The lesson was helpful because the teacher showed clear examples.', 'correct'),
        ('Writing', 'How can you make this sentence stronger: The lesson was good.?', 'The lesson was good.', 'partially_correct'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'I like recess because I can run with my friends.', 'correct'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'I can run with my friends.', 'correct'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'i am good in running', 'partially_correct'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'yes I like races', 'incorrect'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'yes', 'incorrect'),
        ('Writing', '**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!', 'no', 'incorrect'),
        ('ELA', 'Read this short passage: Mia watered the class plant. After that, the plant looked healthy. What is the main idea?', 'One helpful action made things better.', 'correct'),
        ('ELA', 'Read this short passage: Mia watered the class plant. After that, the plant looked healthy. What is the main idea?', 'It is about rain and weather.', 'incorrect'),
        ('ELA', 'Read this short passage: Mia watered the class plant. After that, the plant looked healthy. What can you infer about Mia?', 'Mia was responsible and used a helpful strategy.', 'correct'),
        ('ELA', 'Read this short passage: Mia watered the class plant. After that, the plant looked healthy. What can you infer about Mia?', 'Mia was sleepy and careless.', 'incorrect'),
        ('ELA', 'Fix this sentence: she dont want to go', 'She does not want to go.', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: What did the dog do?', 'dog are running to park', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: What did the dog do?', 'the dog slept', 'incorrect'),
        ('ELA', 'Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: What did the dog do?', 'the dog ran', 'partially_correct'),
        ('ELA', 'Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: Where did the dog go?', 'to the park', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: Where did the dog go?', 'to school', 'incorrect'),
        ('ELA', 'Here is a simple sentence:\n"Mia watered the plant."\n\nQuick question: Who watered the plant?', 'Mia', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"After lunch, Sam read a book."\n\nQuick question: When did Sam read a book?', 'after lunch', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"Mia wore a coat because it was cold."\n\nQuick question: Why did Mia wear a coat?', 'because it was cold', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"First Ben washed his hands, then he ate lunch."\n\nQuick question: What happened first?', 'Ben washed his hands', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"First Ben washed his hands, then he ate lunch."\n\nQuick question: What happened next?', 'he ate lunch', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"The tiny puppy slept in the basket."\n\nQuick question: What does tiny mean?', 'small', 'correct'),
        ('ELA', 'Here is a simple sentence:\n"The tiny puppy slept in the basket."\n\nQuick question: What does tiny mean?', 'tiny', 'partially_correct'),
    ]
    for subject, prompt, answer, expected_status in tutor_cases:
        checked = await checker.check(subject, prompt, answer)
        _expect(checked.status == expected_status, f'Live tutor check mismatch for {subject} prompt {prompt!r}: got {checked.status!r}, expected {expected_status!r}.', failures)
        if 'The dog ran to the park' in prompt:
            _expect('dog are running' not in checked.feedback_note, 'Simple reading checker echoed the student grammar error as the original sentence.', failures)

    reading_history = [ChatHistoryItem(role='msalisia', content='Here is a simple sentence:\n"The dog ran to the park."\n\nQuick question: What did the dog do?')]
    context_question = _reading_context_question('What did the dog do?', reading_history)
    voice_context_question = _voice_reading_context_question('What did the dog do?', reading_history)
    _expect('"The dog ran to the park."' in context_question, 'Text chat reading check did not restore the source sentence from recent history.', failures)
    _expect('"The dog ran to the park."' in voice_context_question, 'Voice reading check did not restore the source sentence from recent history.', failures)
    where_context_question = _reading_context_question('Where did the dog go?', reading_history)
    voice_where_context_question = _voice_reading_context_question('Where did the dog go?', reading_history)
    _expect('"The dog ran to the park."' in where_context_question, 'Text chat reading check did not restore source sentence for a where question.', failures)
    _expect('"The dog ran to the park."' in voice_where_context_question, 'Voice reading check did not restore source sentence for a where question.', failures)

    writing_history = [ChatHistoryItem(role='msalisia', content='**Can you finish this sentence for me?**\n\n"I like recess because..."\n\nJust add whatever reason makes sense to you!')]
    writing_context_question = _writing_context_question('Can you finish this sentence for me?', writing_history)
    voice_writing_context_question = _voice_writing_context_question('Can you finish this sentence for me?', writing_history)
    _expect('"I like recess because..."' in writing_context_question, 'Text chat writing check did not restore the sentence-completion stem.', failures)
    _expect('"I like recess because..."' in voice_writing_context_question, 'Voice writing check did not restore the sentence-completion stem.', failures)
    completion_check = await checker.check('Writing', writing_context_question, 'I can run with my friends.')
    refusal_check = await checker.check('Writing', writing_context_question, 'no')
    _expect(completion_check.status == 'correct', 'Sentence-completion checker did not accept a valid completion-only answer.', failures)
    _expect(refusal_check.status == 'incorrect', 'Sentence-completion checker did not reject a yes/no style answer.', failures)

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
