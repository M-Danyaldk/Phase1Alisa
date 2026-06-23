import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult
from backend.app.services.tutor_conceptual_math import parse_conceptual_math_task


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'conceptual-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'conceptual-message'}


class _LearningProfile:
    async def context_for_child_subject(self, *args, **kwargs):
        return None


class _LearningMemory:
    async def relevant_for_child_subject(self, *args, **kwargs):
        return []

    def memory_directives(self, memory):
        return []

    async def record_exchange_summary(self, *args, **kwargs):
        return None


class _Router:
    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        return LLMResult(
            text='LLM fallback should not own clear conceptual state.',
            provider='fake',
            model='fake',
        )


class _WordProblemRouter:
    async def generate(self, system: str, user: str, purpose: str = 'classifier') -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='fake',
            model='fake',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'conceptual-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send(message: str, state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='TestOne', grade=4),
        subject='Math',
        topic='general practice',
        message=message,
        tutoring_state=state,
    ))


async def _run_endpoint_checks(failures: list[str]) -> None:
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
    main_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        start = await _send('Which is larger: 7/8 or 5/8?', TutoringState(current_subject='Math'))
        state = start.tutoring_state
        _expect(start.model == 'deterministic-fraction_comparison-lock', f'Fraction comparison did not use deterministic lock: {start.model}', failures)
        _expect(state.problem_kind == 'fraction_comparison', 'Fraction comparison did not store conceptual problem_kind.', failures)
        _expect(state.current_question == 'Which is larger: 7/8 or 5/8?', 'Fraction comparison did not preserve original prompt.', failures)
        _expect(state.expected_answer == '7/8', f'Fraction comparison expected answer was {state.expected_answer!r}.', failures)
        _expect(state.problem_status == 'awaiting_step' and state.mode == 'practice', 'Fraction comparison did not become an active practice step.', failures)
        _expect(bool(state.active_task_id), 'Fraction comparison did not create an active lifecycle task.', failures)

        wrong = await _send('5/8', state)
        _expect(wrong.tutoring_state.active_problem == state.active_problem, 'Wrong fraction answer changed the active problem.', failures)
        _expect(wrong.tutoring_state.expected_answer == '7/8', 'Wrong fraction answer lost the expected answer.', failures)
        _expect(wrong.tutoring_state.current_question == state.current_question, 'Wrong fraction answer lost the locked current question.', failures)
        _expect(wrong.tutoring_state.attempt_count == 1, 'Wrong fraction answer did not register exactly one attempt.', failures)
        _expect('Good try' in wrong.reply and '5/8' in wrong.reply, 'Wrong fraction answer did not receive explicit attempt feedback.', failures)
        _expect('3/4' not in wrong.reply, 'Wrong fraction answer leaked into a generated replacement question.', failures)

        hint = await _send('Give me one small hint.', wrong.tutoring_state)
        _expect(hint.model == 'deterministic-progressive-hint', f'Natural hint wording did not route to locked hint flow: {hint.model}', failures)
        _expect(hint.tutoring_state.active_problem == state.active_problem, 'Conceptual hint changed the active problem.', failures)
        _expect(hint.tutoring_state.current_question == state.current_question, 'Conceptual hint lost the locked question.', failures)
        _expect(hint.tutoring_state.expected_answer == '7/8', 'Conceptual hint lost the expected answer.', failures)
        _expect('3/4' not in hint.reply, 'Conceptual hint leaked into a generated replacement question.', failures)

        correct = await _send('7/8', hint.tutoring_state)
        _expect(correct.model == 'deterministic-conceptual-math-completion', f'Correct conceptual answer used {correct.model}.', failures)
        _expect(correct.tutoring_state.problem_status == 'idle' and correct.tutoring_state.active_task_id == '', 'Correct conceptual answer did not close the active task.', failures)
        _expect(correct.tutoring_state.final_answer == '7/8', 'Correct conceptual answer did not preserve final answer in live state.', failures)
        _expect(
            any(record.status == 'completed' and record.problem_text == state.active_problem and record.final_answer == '7/8' for record in correct.tutoring_state.task_records),
            'Correct conceptual answer did not complete lifecycle history with final answer.',
            failures,
        )

        decimal = await _send('Which is greater: 0.6 or 0.75?', TutoringState(current_subject='Math'))
        _expect(decimal.tutoring_state.problem_kind == 'decimal_comparison', 'Decimal comparison did not lock as conceptual math.', failures)
        _expect(decimal.tutoring_state.expected_answer == '0.75', 'Decimal comparison expected answer was not stored.', failures)
    finally:
        main_module.require_child_access = originals['require_child_access']
        main_module.ChatStore = originals['ChatStore']
        main_module.LearningProfileService = originals['LearningProfileService']
        main_module.LearningMemoryService = originals['LearningMemoryService']
        main_module.LLMRouter = originals['LLMRouter']
        word_problem_module.LLMRouter = originals['WordProblemLLMRouter']


async def main() -> None:
    failures: list[str] = []
    parser_cases = [
        ('Which is larger: 7/8 or 5/8?', 'fraction_comparison', '7/8'),
        ('Which is greater: 0.6 or 0.75?', 'decimal_comparison', '0.75'),
        ('Which is smaller: 2/3 or 3/5?', 'fraction_comparison', '3/5'),
        ('Which fraction is equivalent to 1/2: 2/4 or 3/4?', 'equivalent_fraction', '2/4'),
    ]
    for text, question_type, expected in parser_cases:
        task = parse_conceptual_math_task(text)
        _expect(task.accepted, f'Parser rejected conceptual prompt: {text}', failures)
        _expect(task.question_type == question_type, f'Parser route for {text!r} was {task.question_type!r}.', failures)
        _expect(task.expected_answer == expected, f'Parser expected answer for {text!r} was {task.expected_answer!r}.', failures)

    await _run_endpoint_checks(failures)
    if failures:
        raise AssertionError('\n'.join(failures))
    print('Tutor conceptual Math check passed.')
    print('- Fraction, decimal, smaller/larger, and equivalent-fraction prompts lock verified state before LLM wording.')
    print('- Wrong conceptual answers stay on the original prompt instead of becoming replacement questions.')


if __name__ == '__main__':
    asyncio.run(main())
