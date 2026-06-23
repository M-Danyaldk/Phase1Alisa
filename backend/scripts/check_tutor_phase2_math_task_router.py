import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
import backend.app.services.voice_service as voice_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'phase2-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'phase2-message'}


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
        return LLMResult(text='Fallback deterministic tutor reply.', provider='phase2_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='phase2_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'phase2-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send_chat(message: str, state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        message=message,
        history=[ChatHistoryItem(role='msalisia', content='Opening check-in')],
        tutoring_state=state,
    ))


async def _send_voice(service, transcript: str, state: TutoringState, history: list | None = None):
    return await service._generate_tutoring_response(
        parent_id='phase2-parent',
        child={'id': 'phase2-child', 'name': 'Dam', 'grade_level': '6'},
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=history or [],
        tutoring_state=state,
        thread_id='phase2-thread',
    )


async def _run() -> list[str]:
    failures: list[str] = []
    originals = {
        'main_require_child_access': main_module.require_child_access,
        'main_ChatStore': main_module.ChatStore,
        'main_LearningProfileService': main_module.LearningProfileService,
        'main_LearningMemoryService': main_module.LearningMemoryService,
        'main_LLMRouter': main_module.LLMRouter,
        'voice_ChatStore': voice_module.ChatStore,
        'voice_LearningProfileService': voice_module.LearningProfileService,
        'voice_LearningMemoryService': voice_module.LearningMemoryService,
        'voice_LLMRouter': voice_module.LLMRouter,
        'word_problem_LLMRouter': word_problem_module.LLMRouter,
    }
    main_module.require_child_access = _fake_access
    main_module.ChatStore = _MemoryChatStore
    main_module.LearningProfileService = _LearningProfile
    main_module.LearningMemoryService = _LearningMemory
    main_module.LLMRouter = _Router
    voice_module.ChatStore = _MemoryChatStore
    voice_module.LearningProfileService = _LearningProfile
    voice_module.LearningMemoryService = _LearningMemory
    voice_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        opening_state = TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin')
        expression = '9/8 + 7/4 x 8/9+(10 x 23/2)'
        structured = await _send_chat(expression, opening_state)
        _expect(structured.model == 'deterministic-structured-roadmap', 'Multi-step expression did not enter structured roadmap flow.', failures)
        _expect(len(structured.tutoring_state.ordered_steps) == 4, 'Multi-step expression did not produce the full step roadmap.', failures)
        _expect(structured.tutoring_state.current_question == 'What is 10 × 23/2?', 'Multi-step expression did not start on the parentheses step.', failures)
        _expect(structured.tutoring_state.expected_answer == '115', 'Multi-step expression did not store the first expected answer.', failures)

        repaired_symbol = await _send_chat('9/8 + 7/4 * 8/9+(10 ? 23/2)', opening_state)
        _expect(repaired_symbol.model == 'deterministic-structured-roadmap', 'Corrupted multiply symbol did not recover into structured roadmap flow.', failures)
        _expect('10 * 23/2' in repaired_symbol.tutoring_state.main_problem, 'Corrupted multiply symbol was not normalized safely.', failures)

        hint = await _send_chat('Give me one small hint.', structured.tutoring_state)
        _expect(hint.tutoring_state.current_question == 'What is 10 × 23/2?', 'Helper request lost the active structured step.', failures)
        _expect(hint.tutoring_state.expected_answer == '115', 'Helper request lost the structured expected answer.', failures)

        voice_service = voice_module.VoiceService()
        spoken_start = await _send_voice(voice_service, 'negative nine plus five', TutoringState(current_subject='Math'))
        _expect(spoken_start['tutoring_state'].current_question == 'What is -9 + 5?', 'Spoken negative expression lost the negative sign.', failures)
        _expect(spoken_start['tutoring_state'].expected_answer == '-4', 'Spoken negative expression did not store the expected answer.', failures)
        spoken_answer = await _send_voice(voice_service, 'negative four', spoken_start['tutoring_state'])
        _expect(spoken_answer['tutoring_state'].final_answer == '-4', 'Spoken negative answer was not accepted.', failures)

        times_start = await _send_voice(voice_service, '23 times three', TutoringState(current_subject='Math'))
        _expect(times_start['tutoring_state'].current_question == 'What is 23 x 3?', 'Spoken multiplication did not create a current question.', failures)
        _expect(times_start['tutoring_state'].expected_answer == '69', 'Spoken multiplication did not store the expected answer.', failures)
        times_answer = await _send_voice(voice_service, '69', times_start['tutoring_state'])
        _expect(times_answer['tutoring_state'].final_answer == '69', 'Spoken multiplication answer was not accepted.', failures)
    finally:
        main_module.require_child_access = originals['main_require_child_access']
        main_module.ChatStore = originals['main_ChatStore']
        main_module.LearningProfileService = originals['main_LearningProfileService']
        main_module.LearningMemoryService = originals['main_LearningMemoryService']
        main_module.LLMRouter = originals['main_LLMRouter']
        voice_module.ChatStore = originals['voice_ChatStore']
        voice_module.LearningProfileService = originals['voice_LearningProfileService']
        voice_module.LearningMemoryService = originals['voice_LearningMemoryService']
        voice_module.LLMRouter = originals['voice_LLMRouter']
        word_problem_module.LLMRouter = originals['word_problem_LLMRouter']
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor Phase 2 Math task-router check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 2 Math task-router check passed.')
    print('- Multi-step typed expressions route to structured roadmap state before answer checking.')
    print('- Spoken signed and multiplication expressions create gradeable Math state and accept correct answers.')


if __name__ == '__main__':
    main()
