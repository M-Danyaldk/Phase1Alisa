import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'opening-mixed-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'opening-mixed-message'}


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
        return LLMResult(text='LLM fallback should not own mixed opening math.', provider='fake', model='fake')


class _WordProblemRouter:
    async def generate(self, system: str, user: str, purpose: str = 'classifier') -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='fake',
            model='fake',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'opening-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _opening_state() -> TutoringState:
    return TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin')


def _opening_history() -> list[ChatHistoryItem]:
    return [
        ChatHistoryItem(
            role='msalisia',
            content='Hey TestOne! How are you doing today? Once you let me know, I will ask one quick Math question.',
        )
    ]


async def _send(message: str, state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='TestOne', grade=4),
        subject='Math',
        topic='general practice',
        message=message,
        history=_opening_history(),
        tutoring_state=state,
    ))


async def main() -> None:
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
    main_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        confused = await _send('I feel confused but I want help with 12 - 20', _opening_state())
        _expect(confused.model == 'deterministic-opening-mixed-math-start', f'Mixed opening arithmetic used {confused.model}.', failures)
        _expect(confused.tutoring_state.problem_kind == 'opening_arithmetic', 'Mixed opening arithmetic did not create opening_arithmetic state.', failures)
        _expect(confused.tutoring_state.current_question == 'What is 12 - 20?', 'Mixed opening arithmetic did not store the current question.', failures)
        _expect(confused.tutoring_state.expected_answer == '-8', 'Mixed opening arithmetic did not store expected answer -8.', failures)
        _expect('Thanks for telling me' in confused.reply, 'Mixed opening arithmetic did not acknowledge the feeling.', failures)

        confused_answer = await _send('-8', confused.tutoring_state)
        _expect(confused_answer.model == 'deterministic-opening-mixed-math-completion', f'Mixed opening correct answer used {confused_answer.model}.', failures)
        _expect(confused_answer.tutoring_state.final_answer == '-8', 'Mixed opening arithmetic did not keep final answer after completion.', failures)
        _expect(
            any(record.status == 'completed' and record.problem_text == '12 - 20' and record.final_answer == '-8' for record in confused_answer.tutoring_state.task_records),
            'Mixed opening arithmetic did not complete lifecycle history.',
            failures,
        )
        _expect('Now finish the original problem' not in confused_answer.reply, 'Mixed opening arithmetic still used substep completion wording.', failures)

        happy = await _send('I am happy and what is -9 + 5?', _opening_state())
        _expect(happy.model == 'deterministic-opening-mixed-math-start', 'Happy opening plus equation did not start a locked Math task.', failures)
        _expect(happy.tutoring_state.expected_answer == '-4', 'Happy opening plus equation did not store expected answer -4.', failures)

        conceptual = await _send('I am doing well and which is larger: 7/8 or 5/8?', _opening_state())
        _expect(conceptual.model == 'deterministic-fraction_comparison-lock', f'Mixed opening conceptual prompt used {conceptual.model}.', failures)
        _expect(conceptual.tutoring_state.current_question == 'Which is larger: 7/8 or 5/8?', 'Mixed opening conceptual prompt kept non-math prefix in current question.', failures)
        _expect(conceptual.tutoring_state.expected_answer == '7/8', 'Mixed opening conceptual prompt lost expected answer.', failures)

        normal = await _send('just okay', _opening_state())
        _expect(normal.model == 'deterministic-tutor-math-starter', 'Normal opening feeling/acknowledgement no longer starts mini-check practice.', failures)
        _expect(normal.tutoring_state.problem_status == 'tutor_practice', 'Normal opening mini-check did not enter tutor practice.', failures)
    finally:
        main_module.require_child_access = originals['require_child_access']
        main_module.ChatStore = originals['ChatStore']
        main_module.LearningProfileService = originals['LearningProfileService']
        main_module.LearningMemoryService = originals['LearningMemoryService']
        main_module.LLMRouter = originals['LLMRouter']
        word_problem_module.LLMRouter = originals['WordProblemLLMRouter']

    if failures:
        raise AssertionError('\n'.join(failures))
    print('Tutor opening mixed Math check passed.')
    print('- Opening feelings plus Math tasks start locked Math state instead of semantic clarification.')
    print('- Normal opening check-in still starts the tutor-practice mini-check.')


if __name__ == '__main__':
    asyncio.run(main())
