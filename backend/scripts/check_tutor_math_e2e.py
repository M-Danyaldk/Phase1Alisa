import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'e2e-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'e2e-message'}


class _LearningProfile:
    async def context_for_child_subject(self, child_id, subject):
        return None


class _LearningMemory:
    async def relevant_for_child_subject(self, *args, **kwargs):
        return []

    def memory_directives(self, memory):
        return []

    async def record_exchange_summary(self, *args, **kwargs):
        return None


class _DeterministicRouter:
    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        if 'Attempt count: 1' in user:
            text = 'Nice try. 7 × 2 = 12. What is 7 × 2?'
        elif 'Attempt count: 2' in user:
            text = 'Hint: Think of 7 equal groups of 2. What is 7 × 2?'
        elif 'Attempt count: 3' in user:
            text = 'Now we can reveal it: 7 × 2 = 14. **Final answer:** 14'
        else:
            text = 'Let’s work on one verified step. What number should we calculate first?'
        return LLMResult(text=text, provider='e2e_fake', model='deterministic', fallback_used=False)


class _WordProblemRouter:
    async def generate(self, system: str, user: str, purpose: str = 'classifier') -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='e2e_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'e2e-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send(message: str, state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Sajjad', grade=4),
        subject='Math',
        topic='general practice',
        message=message,
        tutoring_state=state,
    ))


async def _run() -> list[str]:
    failures: list[str] = []
    originals = {
        'require_child_access': main_module.require_child_access,
        'ChatStore': main_module.ChatStore,
        'LearningProfileService': main_module.LearningProfileService,
        'LearningMemoryService': main_module.LearningMemoryService,
        'LLMRouter': main_module.LLMRouter,
        'WordProblemLLMRouter': word_problem_module.LLMRouter,
    }
    main_module.require_child_access = _fake_access
    main_module.ChatStore = _MemoryChatStore
    main_module.LearningProfileService = _LearningProfile
    main_module.LearningMemoryService = _LearningMemory
    main_module.LLMRouter = _DeterministicRouter
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        initial = TutoringState(current_subject='Math')
        direct_arithmetic = await _send('9 + 10', initial)
        _expect(direct_arithmetic.model == 'deterministic-arithmetic_single_step-start', 'Bare arithmetic did not start deterministic student-entered Math flow.', failures)
        _expect(direct_arithmetic.tutoring_state.active_problem == '9 + 10', 'Bare arithmetic did not store the active problem.', failures)
        _expect(direct_arithmetic.tutoring_state.current_question == 'What is 9 + 10?', 'Bare arithmetic did not store the visible current question.', failures)
        _expect(direct_arithmetic.tutoring_state.expected_answer == '19', 'Bare arithmetic did not store the expected answer.', failures)
        direct_correct = await _send('19', direct_arithmetic.tutoring_state)
        _expect(direct_correct.model == 'deterministic-student-arithmetic-completion', 'Correct bare arithmetic answer did not use deterministic completion.', failures)
        _expect(direct_correct.tutoring_state.final_answer == '19', 'Correct bare arithmetic answer did not store the final answer.', failures)
        _expect(direct_correct.tutoring_state.active_task_id == '', 'Correct bare arithmetic answer left the task active.', failures)

        reveal_start = await _send('12 - 20', initial)
        reveal_wrong_1 = await _send('10', reveal_start.tutoring_state)
        reveal_wrong_2 = await _send('12', reveal_wrong_1.tutoring_state)
        reveal_wrong_3 = await _send('14', reveal_wrong_2.tutoring_state)
        _expect(reveal_wrong_1.model.endswith('progressive-attempt-hint-1'), 'First wrong bare arithmetic answer did not use hint level 1.', failures)
        _expect(reveal_wrong_2.model.endswith('progressive-attempt-hint-2'), 'Second wrong bare arithmetic answer did not use hint level 2.', failures)
        _expect(reveal_wrong_3.model == 'deterministic-student-arithmetic-reveal', 'Third wrong bare arithmetic answer did not use deterministic reveal.', failures)
        _expect('**Final answer:** -8.' in reveal_wrong_3.reply, 'Third wrong bare arithmetic answer did not reveal the final answer.', failures)
        _expect(reveal_wrong_3.tutoring_state.final_answer == '-8', 'Third wrong bare arithmetic answer did not store the revealed answer.', failures)
        _expect(reveal_wrong_3.tutoring_state.active_task_id == '', 'Third wrong bare arithmetic answer left the task active.', failures)

        topic_started = await _send('teach me fraction', initial)
        topic_state = topic_started.tutoring_state
        _expect(topic_started.model == 'deterministic-math-topic-switch', 'Topic request did not use deterministic topic-start flow.', failures)
        _expect('A fraction shows part of a whole.' in topic_started.reply, 'Topic-start reply did not include the fraction explanation.', failures)
        _expect('Example:' in topic_started.reply, 'Topic-start reply did not include an example.', failures)
        _expect(topic_state.mode == 'tutor_practice_question', 'Topic-start did not enter tutor-practice mode.', failures)
        _expect(topic_state.current_question == 'What fraction shows 1 part out of 4 equal parts?', 'Topic-start did not store the starter question.', failures)
        _expect(topic_state.expected_answer == '1/4', 'Topic-start did not store the expected answer.', failures)
        _expect(topic_state.attempt_count == 0, 'Topic-start counted the topic request as an answer attempt.', failures)

        practice_to_student_problem = await _send('There are 3 boxes with 2 balls in each box. How many balls are there?', topic_state)
        aligned_state = practice_to_student_problem.tutoring_state
        _expect(practice_to_student_problem.model == 'deterministic-structured-word-problem', 'Tutor-practice to student-entered word problem did not use the structured Math path.', failures)
        _expect(aligned_state.problem_status != 'tutor_practice' and aligned_state.mode != 'tutor_practice_question', 'Student-entered problem stayed trapped in tutor-practice mode.', failures)
        _expect(aligned_state.current_question != topic_state.current_question, 'Student-entered problem kept the old tutor-practice question active.', failures)
        _expect(aligned_state.tutor_practice_question_id == '' and not aligned_state.tutor_practice_hint_1 and not aligned_state.tutor_practice_explanation, 'Student-entered problem kept tutor-practice metadata after switching flows.', failures)
        _expect(not aligned_state.support_per_step and not aligned_state.attempts_per_step, 'Student-entered problem kept tutor-practice attempt or hint history after switching flows.', failures)
        _expect(aligned_state.helper_branch.status == 'idle' and not aligned_state.queued_followup_questions, 'Student-entered problem kept tutor-practice helper or queued follow-up state.', failures)
        _expect(aligned_state.expected_answer == '6', 'Student-entered problem did not store its own expected answer after leaving tutor practice.', failures)

        ambiguous_from_practice = await _send('A shop sold 15 items. How many are left?', topic_state)
        ambiguous_practice_state = ambiguous_from_practice.tutoring_state
        _expect(ambiguous_from_practice.model == 'deterministic-word-problem-clarification', 'Ambiguous student-entered problem from tutor practice did not enter clarification.', failures)
        _expect(ambiguous_practice_state.problem_status != 'tutor_practice' and ambiguous_practice_state.mode == 'clarify_word_problem', 'Ambiguous student-entered problem from tutor practice stayed trapped in tutor-practice mode.', failures)
        _expect(ambiguous_practice_state.tutor_practice_question_id == '' and not ambiguous_practice_state.tutor_practice_hint_1, 'Ambiguous student-entered problem from tutor practice kept tutor-practice metadata.', failures)

        practice_hint_1 = await _send('give me a hint', topic_state)
        practice_hint_2 = await _send("I still don't understand", practice_hint_1.tutoring_state)
        practice_wrong = await _send('2/4', practice_hint_2.tutoring_state)
        practice_support = next(iter(practice_wrong.tutoring_state.support_per_step.values()), None)
        _expect(
            practice_wrong.tutoring_state.attempt_count == 1
            and practice_support is not None
            and practice_support.help_level == 3,
            f'A wrong practice answer after two hints did not advance to worked-substep guidance: attempts={practice_wrong.tutoring_state.attempt_count}, support={practice_wrong.tutoring_state.support_per_step!r}, model={practice_wrong.model}, first={practice_hint_1.tutoring_state.support_per_step!r}, second={practice_hint_2.tutoring_state.support_per_step!r}, reply={practice_wrong.reply!r}.',
            failures,
        )

        topic_help = await _send('what is the denominator in this fraction?', topic_state)
        helped_state = topic_help.tutoring_state
        _expect(topic_help.model == 'deterministic-tutor-math-practice-support', 'Topic help did not use deterministic tutor-practice support.', failures)
        _expect('bottom number' in topic_help.reply.lower(), 'Topic help did not explain the denominator.', failures)
        _expect(helped_state.active_task_id == topic_state.active_task_id, 'Topic help interruption changed the active lesson task.', failures)
        _expect(helped_state.current_question == topic_state.current_question, 'Topic help interruption changed the starter question.', failures)
        _expect(helped_state.expected_answer == '1/4', 'Topic help interruption lost the expected answer.', failures)
        _expect(helped_state.attempt_count == 0, 'Topic help interruption counted as an answer attempt.', failures)

        topic_answer = await _send('1/4', helped_state)
        _expect(topic_answer.model == 'deterministic-tutor-math-practice-check', 'Topic starter answer did not use tutor-practice checking.', failures)
        _expect(topic_answer.tutoring_state.final_answer == '1/4', 'Topic starter answer did not finish with the expected answer.', failures)
        _expect(
            topic_answer.tutoring_state.problem_status == 'finished'
            and topic_answer.tutoring_state.mode == 'awaiting_more_practice_choice'
            and topic_answer.tutoring_state.continuation_origin_answer == '1/4',
            'Finished topic starter did not enter continuation-choice mode cleanly.',
            failures,
        )
        _expect(
            any(
                record.status == 'completed'
                and record.problem_text == 'What fraction shows 1 part out of 4 equal parts?'
                and record.final_answer == '1/4'
                for record in topic_answer.tutoring_state.task_records
            ),
            'Topic starter completion was not recorded in lifecycle history.',
            failures,
        )
        _expect(topic_answer.tutoring_state.active_task_id == '', 'Finished topic starter task remained active.', failures)

        negative_practice = await _send(
            'just okay',
            TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'),
        )
        _expect(
            negative_practice.model == 'deterministic-tutor-math-starter'
            and negative_practice.tutoring_state.problem_status == 'tutor_practice',
            'Opening mini-check did not start a tutor-practice Math question.',
            failures,
        )
        if negative_practice.tutoring_state.current_question == 'What is -9 + 5?':
            first_wrong_negative = await _send('4', negative_practice.tutoring_state)
            corrected_negative = await _send('-4', first_wrong_negative.tutoring_state)
            _expect(
                corrected_negative.model == 'deterministic-tutor-math-practice-check',
                f'Correct second answer on negative-number tutor practice used {corrected_negative.model} instead of tutor-practice checking.',
                failures,
            )
            _expect(
                "Yes, that's correct!" in corrected_negative.reply and corrected_negative.tutoring_state.final_answer == '-4',
                'Correct second answer on negative-number tutor practice was not accepted.',
                failures,
            )
            _expect(
                'keep the answer hidden' not in corrected_negative.reply.lower(),
                'Correct second answer on negative-number tutor practice was incorrectly hidden behind the response guard.',
                failures,
            )

        started = await _send('There are 7 boxes and each box has space for 2 balls. How many balls are needed?', topic_answer.tutoring_state)
        state = started.tutoring_state
        _expect(started.model == 'deterministic-structured-word-problem', 'Word problem did not enter deterministic structured flow.', failures)
        _expect(state.expected_answer == '14' and state.current_question, 'Word problem did not store its verified current step.', failures)
        _expect(state.display_answer == '14 balls', 'Word problem did not store its contextual answer.', failures)
        task_id = state.active_task_id

        first_help = await _send('give me a hint', state)
        second_help = await _send("I still don't understand", first_help.tutoring_state)
        third_help = await _send('help me again', second_help.tutoring_state)
        hint_support = next(iter(third_help.tutoring_state.support_per_step.values()), None)
        _expect(
            third_help.tutoring_state.attempt_count == 0,
            'Repeated help requests were counted as answer attempts.',
            failures,
        )
        _expect(
            hint_support is not None
            and hint_support.shown_hint_ids == ['concept', 'strategy', 'worked_substep'],
            f'Endpoint help did not advance through three distinct hints: {third_help.tutoring_state.support_per_step!r}; models={first_help.model},{second_help.model},{third_help.model}.',
            failures,
        )
        state = started.tutoring_state

        emotional = await _send("I'm bad at math", state)
        state = emotional.tutoring_state
        _expect(state.mode == 'emotional_checkin', 'Discouragement did not enter emotional support.', failures)
        _expect(state.active_task_id == task_id and state.expected_answer == '14', 'Emotional interruption lost the active task.', failures)

        continued = await _send('one tiny step', state)
        state = continued.tutoring_state
        _expect(state.mode == 'practice' and state.active_task_id == task_id, 'Tiny-step choice did not restore the same task.', failures)

        first_wrong = await _send('10', state)
        state = first_wrong.tutoring_state
        _expect(state.attempt_count == 1, 'First wrong answer did not register exactly once.', failures)
        _expect(first_wrong.model == 'deterministic-progressive-attempt-hint-1', 'First wrong answer did not use deterministic progressive guidance.', failures)
        _expect(state.current_question and state.problem_status != 'finished', 'Response repair did not keep the current question active.', failures)
        _expect('= 12' not in first_wrong.reply, 'Bad arithmetic reached the student response.', failures)

        boundary = await _send('Tell me about photosynthesis', state)
        state = boundary.tutoring_state
        _expect(state.attempt_count == 1 and state.expected_answer == '14', 'Subject boundary erased the active Math attempt or answer.', failures)

        second_wrong = await _send('11', state)
        state = second_wrong.tutoring_state
        _expect(state.attempt_count == 2 and not state.answer_revealed, 'Second attempt did not retain the hint-stage state.', failures)

        third_wrong = await _send('13', state)
        state = third_wrong.tutoring_state
        _expect('14 balls' in third_wrong.reply, f'One-step reveal omitted the answer unit: {third_wrong.reply!r}.', failures)
        _expect('7 × 2 = 14' in third_wrong.reply, 'Third attempt did not permit the verified reveal.', failures)
        _expect(state.active_task_id == '', 'Completed one-step task remained active.', failures)
        _expect(any(record.status == 'completed' for record in state.task_records), 'Completed task was not recorded in lifecycle history.', failures)

        repeated = await _send('There are 7 boxes and each box has space for 2 balls. How many balls are needed?', state)
        _expect(bool(repeated.tutoring_state.active_task_id) and repeated.tutoring_state.expected_answer == '14', 'Repeating a completed word problem did not start a fresh task.', failures)

        multi = await _send('An auditorium has 28 rows with 35 seats in each row. If 180 students attend, how many seats are empty?', state)
        multi_state = multi.tutoring_state
        _expect(bool(multi_state.ordered_steps) and multi_state.expected_answer == '980', 'Multi-step word problem did not start at multiplication.', failures)
        wrong_structured = await _send('900', multi_state)
        multi_state = wrong_structured.tutoring_state
        _expect(multi_state.attempt_count == 1, 'Structured wrong answer did not enter the hint ladder.', failures)
        restated_step = await _send('28 x 35', multi_state)
        multi_state = restated_step.tutoring_state
        _expect(multi_state.attempt_count == 1, f'Restating the structured step changed its attempt history to {multi_state.attempt_count}.', failures)
        step_one = await _send('980', multi_state)
        multi_state = step_one.tutoring_state
        _expect(multi_state.expected_answer == '800', 'Multi-step problem did not advance to subtraction.', failures)
        finished = await _send('800', multi_state)
        _expect(finished.tutoring_state.final_answer == '800', 'Multi-step journey did not finish with 800.', failures)
        _expect('800 empty seats' in finished.reply, 'Multi-step completion omitted the contextual answer label.', failures)
        _expect(finished.tutoring_state.active_task_id == '', 'Finished multi-step task remained active.', failures)

        unit_multi = await _send('A theater has 20 rows with 30 seats in each row. If 100 students attend, how many seats are empty?', finished.tutoring_state)
        unit_state = unit_multi.tutoring_state
        unit_step_one = await _send('600', unit_state)
        unit_state = unit_step_one.tutoring_state
        unit_finished = await _send('500 balls', unit_state)
        _expect('500 empty seats' in unit_finished.reply, 'Contradictory-unit answer did not keep the verified contextual answer.', failures)
        _expect('not **ball**' in unit_finished.reply, 'Contradictory-unit answer did not explain the unit correction.', failures)
        clean_after_unit_state = unit_finished.tutoring_state

        fraction_story = await _send('A pizza has 8 slices and Mia ate 3 slices. What fraction did Mia eat?', clean_after_unit_state)
        _expect(fraction_story.tutoring_state.expected_answer == '3/8', 'Fraction word problem did not store 3/8 as the expected answer.', failures)
        _expect(fraction_story.tutoring_state.current_step == '3 / 8', 'Fraction word problem did not build the eaten/whole expression.', failures)

        missing_info = await _send('A shop sold 15 items. How many are left?', clean_after_unit_state)
        _expect(missing_info.model == 'deterministic-word-problem-clarification', 'Missing-information word problem did not use clarification path.', failures)
        _expect('start' in missing_info.reply.lower(), 'Missing-information reply did not ask for the starting amount.', failures)

        safety_problem = await _send('There are 3 boxes with 4 balls in each box. How many balls are there?', finished.tutoring_state)
        safety = await _send("I don't feel safe", safety_problem.tutoring_state)
        _expect(safety.tutoring_state.mode == 'safety_support', 'High-distress endpoint message did not enter safety mode.', failures)
        _expect(safety.tutoring_state.active_task_id == '', 'Safety escalation did not pause the learning task.', failures)
        locked = await _send('continue', safety.tutoring_state)
        _expect(locked.model == 'deterministic-safety-support-lock', 'Safety mode allowed an automatic lesson resume.', failures)
        _expect(locked.tutoring_state.mode == 'safety_support' and locked.tutoring_state.active_task_id == '', 'Safety lock did not remain active.', failures)

        ambiguous = await _send('There are 7 red cards and 3 blue cards. How many should I use?', TutoringState(current_subject='Math'))
        _expect(ambiguous.model == 'deterministic-word-problem-clarification', 'Ambiguous word problem did not request clarification.', failures)
        clarified = await _send('the total', ambiguous.tutoring_state)
        _expect(clarified.tutoring_state.expected_answer == '10', 'Word-problem clarification did not resolve into the intended total.', failures)
    finally:
        for name, value in originals.items():
            if name == 'WordProblemLLMRouter':
                word_problem_module.LLMRouter = value
            else:
                setattr(main_module, name, value)
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor Math endpoint E2E check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor Math endpoint E2E check passed.')
    print('- Word problem, emotion, continuation, attempts, repair, and completion work as one journey.')
    print('- Multi-step word problems advance and close through the real chat endpoint.')


if __name__ == '__main__':
    main()
