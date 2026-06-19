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
        started = await _send('There are 7 boxes and each box has space for 2 balls. How many balls are needed?', initial)
        state = started.tutoring_state
        _expect(started.model == 'deterministic-structured-word-problem', 'Word problem did not enter deterministic structured flow.', failures)
        _expect(state.expected_answer == '14' and state.current_question, 'Word problem did not store its verified current step.', failures)
        task_id = state.active_task_id

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
        _expect('incorrect_arithmetic' in state.last_response_violations, 'Bad generated arithmetic was not repaired at the endpoint.', failures)
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
        _expect(finished.tutoring_state.active_task_id == '', 'Finished multi-step task remained active.', failures)

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
