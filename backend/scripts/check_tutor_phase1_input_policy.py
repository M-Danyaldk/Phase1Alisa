import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
import backend.app.services.voice_service as voice_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'phase1-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'phase1-message'}


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
    calls: list[tuple[str, str]] = []

    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        self.__class__.calls.append((purpose, user))
        return LLMResult(
            text='A fraction shows part of a whole. Example: 1/2 means one out of two equal parts.',
            provider='phase1_fake',
            model='deterministic',
        )


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='phase1_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'phase1-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send_chat(
    message: str,
    state: TutoringState,
    *,
    subject: str = 'Math',
    surface_context: str = 'start_learning',
):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject=subject,
        topic='general practice',
        surface_context=surface_context,
        message=message,
        history=[ChatHistoryItem(role='msalisia', content='Final answer: -13. Would you like another practice question?')],
        tutoring_state=state,
    ))


async def _send_voice(
    service,
    transcript: str,
    state: TutoringState,
    *,
    subject: str = 'Math',
    surface_context: str = 'start_learning',
):
    return await service._generate_tutoring_response(
        parent_id='phase1-parent',
        child={'id': 'phase1-child', 'name': 'Dam', 'grade_level': '6'},
        student=StudentProfile(name='Dam', grade=6),
        subject=subject,
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=[{'role': 'msalisia', 'content': 'Final answer: -13. Would you like another practice question?'}],
        tutoring_state=state,
        thread_id='phase1-thread',
        surface_context=surface_context,
    )


def _finished_math_state() -> TutoringState:
    return TutoringState(
        current_subject='Math',
        mode='awaiting_more_practice_choice',
        status='waiting_for_student',
        problem_status='finished',
        final_answer='-13',
        continuation_origin_problem='-15 + 2',
        continuation_origin_answer='-13',
        continuation_origin_explanation='-15 + 2 = -13.',
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
    _Router.calls = []
    try:
        concept = await _send_chat('What is fraction?', _finished_math_state())
        _expect(concept.model == 'deterministic', 'Finished Math concept question did not reach the LLM concept-answer path.', failures)
        _expect('part of a whole' in concept.reply.lower(), 'Finished Math concept question did not answer the requested concept.', failures)
        _expect('-15 + 2 = -13' not in concept.reply, 'Finished Math concept question repeated the prior answer instead of answering the concept.', failures)
        _expect(any(purpose == 'chat' for purpose, _ in _Router.calls), 'Concept question did not call the chat LLM.', failures)

        blocked = await _send_chat('switch to reading', TutoringState(current_subject='Math'), surface_context='math_tutor')
        _expect(blocked.model == 'deterministic-subject-switch-blocked', 'Locked Math surface did not block a subject switch.', failures)
        _expect(blocked.resolved_subject == 'Math' and not blocked.subject_changed, 'Locked Math surface mutated the active subject.', failures)
        _expect(blocked.tutoring_state.current_subject == 'Math', 'Locked Math surface returned the wrong state subject.', failures)

        allowed = await _send_chat('switch to reading', TutoringState(current_subject='Math'), surface_context='start_learning')
        _expect(allowed.subject_changed and allowed.resolved_subject == 'ELA', 'Start Learning did not allow an explicit subject switch.', failures)

        voice_service = voice_module.VoiceService()
        voice_blocked = await _send_voice(voice_service, 'switch to reading', TutoringState(current_subject='Math'), surface_context='math_tutor')
        _expect(voice_blocked['model'] == 'deterministic-voice-subject-switch-blocked', 'Locked Math voice surface did not block a subject switch.', failures)
        _expect(voice_blocked['resolved_subject'] == 'Math' and not voice_blocked['subject_changed'], 'Locked Math voice surface mutated the active subject.', failures)

        voice_concept = await _send_voice(voice_service, 'What is fraction?', _finished_math_state())
        _expect(voice_concept['model'] == 'deterministic', 'Voice finished Math concept question did not reach the LLM concept-answer path.', failures)
        _expect('part of a whole' in voice_concept['assistant_text'].lower(), 'Voice concept question did not answer the requested concept.', failures)
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
        print('Tutor Phase 1 input policy check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 1 input policy check passed.')
    print('- Concept questions during continuation mode answer the requested concept instead of replaying the last problem.')
    print('- Subject switching is allowed only on the Start Learning surface and blocked on locked tutor surfaces.')


if __name__ == '__main__':
    main()
