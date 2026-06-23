import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
import backend.app.services.voice_service as voice_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'phase4-voice-typed-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'phase4-voice-typed-message'}


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
        if 'Student says: What is fraction?' in user or 'Student says: what is fraction?' in user:
            return LLMResult(
                text='A fraction shows part of a whole. Example: 1/2 means one out of two equal parts.',
                provider='phase4_voice_typed_fake',
                model='deterministic',
            )
        return LLMResult(text='Fallback deterministic tutor reply.', provider='phase4_voice_typed_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='phase4_voice_typed_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'phase4-voice-typed-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send_chat(message: str, state: TutoringState, history: list[ChatHistoryItem] | None = None):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        message=message,
        history=history or [ChatHistoryItem(role='msalisia', content=state.current_question or 'Opening check-in')],
        tutoring_state=state,
    ))


async def _send_voice(service, transcript: str, state: TutoringState, history: list | None = None):
    return await service._generate_tutoring_response(
        parent_id='phase4-voice-typed-parent',
        child={'id': 'phase4-voice-typed-child', 'name': 'Dam', 'grade_level': '6'},
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=history or [],
        tutoring_state=state,
        thread_id='phase4-voice-typed-thread',
    )


def _fraction_practice_state() -> TutoringState:
    question = 'Which is larger: 5/6 or 4/6?'
    return TutoringState(
        current_subject='Math',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
        active_problem=question,
        current_question=question,
        current_step=question,
        expected_answer='5/6',
        tutor_practice_question_id='phase4-voice-typed-fraction',
        tutor_practice_topic='fractions',
        tutor_practice_hint_1='Both fractions have the same denominator, so compare the numerators.',
        tutor_practice_hint_2='Both fractions are sixths. Compare 5 and 4.',
        tutor_practice_explanation='5/6 is larger than 4/6 because 5 is greater than 4.',
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
        voice_service = voice_module.VoiceService()

        chat_structured = await _send_chat('9/8 + 7/4 * 8/9+(10 x 23/2)', TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        voice_structured = await _send_voice(voice_service, '9/8 + 7/4 * 8/9+(10 x 23/2)', TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        _expect(chat_structured.model == 'deterministic-structured-roadmap', 'Chat typed multi-step did not route to structured roadmap.', failures)
        _expect(voice_structured['model'] in {'deterministic-voice-structured-roadmap', 'deterministic-structured-roadmap'}, 'Voice typed multi-step did not route to structured roadmap.', failures)
        _expect(chat_structured.tutoring_state.current_question == voice_structured['tutoring_state'].current_question, 'Voice typed multi-step current question differs from chat.', failures)
        _expect(chat_structured.tutoring_state.expected_answer == voice_structured['tutoring_state'].expected_answer == '115', 'Voice typed multi-step expected answer differs from chat.', failures)
        _expect(len(chat_structured.tutoring_state.ordered_steps) == len(voice_structured['tutoring_state'].ordered_steps) == 4, 'Voice typed multi-step roadmap length differs from chat.', failures)

        chat_hint = await _send_chat('Give me one small hint.', chat_structured.tutoring_state)
        voice_hint = await _send_voice(voice_service, 'Give me one small hint.', voice_structured['tutoring_state'])
        _expect(chat_hint.tutoring_state.current_question == voice_hint['tutoring_state'].current_question, 'Voice typed helper lost a different structured current question than chat.', failures)
        _expect(chat_hint.tutoring_state.expected_answer == voice_hint['tutoring_state'].expected_answer == '115', 'Voice typed helper lost structured expected answer.', failures)

        chat_signed = await _send_chat('-15 + 2', TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        voice_signed = await _send_voice(voice_service, '-15 + 2', TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        _expect(chat_signed.tutoring_state.current_question == voice_signed['tutoring_state'].current_question == 'What is -15 + 2?', 'Voice typed signed arithmetic current question differs from chat.', failures)
        _expect(chat_signed.tutoring_state.expected_answer == voice_signed['tutoring_state'].expected_answer == '-13', 'Voice typed signed arithmetic expected answer differs from chat.', failures)
        chat_wrong_1 = await _send_chat('261', chat_signed.tutoring_state)
        chat_wrong_2 = await _send_chat('378282', chat_wrong_1.tutoring_state)
        chat_reveal = await _send_chat('666', chat_wrong_2.tutoring_state)
        voice_wrong_1 = await _send_voice(voice_service, '261', voice_signed['tutoring_state'])
        voice_wrong_2 = await _send_voice(voice_service, '378282', voice_wrong_1['tutoring_state'])
        voice_reveal = await _send_voice(voice_service, '666', voice_wrong_2['tutoring_state'])
        _expect(chat_reveal.tutoring_state.final_answer == voice_reveal['tutoring_state'].final_answer == '-13', 'Voice typed signed third-wrong reveal final answer differs from chat.', failures)
        _expect(chat_reveal.tutoring_state.problem_status == voice_reveal['tutoring_state'].problem_status == 'finished', 'Voice typed signed third-wrong reveal did not finish like chat.', failures)
        _expect('**Final answer:** -13.' in voice_reveal['assistant_text'], 'Voice typed signed third-wrong reveal omitted final answer.', failures)

        fraction_state = _fraction_practice_state()
        chat_denominator = await _send_chat('what is denominator?', fraction_state)
        voice_denominator = await _send_voice(voice_service, 'what is denominator?', fraction_state)
        _expect('denominator is 6' in chat_denominator.reply.lower(), 'Chat typed denominator helper did not use denominator 6.', failures)
        _expect('denominator is 6' in voice_denominator['assistant_text'].lower(), 'Voice typed denominator helper did not use denominator 6.', failures)
        _expect(chat_denominator.tutoring_state.current_question == voice_denominator['tutoring_state'].current_question == fraction_state.current_question, 'Voice typed denominator helper did not preserve the same current question as chat.', failures)
        _expect(chat_denominator.tutoring_state.expected_answer == voice_denominator['tutoring_state'].expected_answer == '5/6', 'Voice typed denominator helper did not preserve expected answer like chat.', failures)

        chat_arithmetic_override = await _send_chat('-152 +32', fraction_state)
        voice_arithmetic_override = await _send_voice(voice_service, '-152 +32', fraction_state)
        _expect(chat_arithmetic_override.tutoring_state.expected_answer == voice_arithmetic_override['tutoring_state'].expected_answer == '-120', 'Voice typed arithmetic override expected answer differs from chat.', failures)
        _expect(chat_arithmetic_override.tutoring_state.problem_status == voice_arithmetic_override['tutoring_state'].problem_status == 'awaiting_step', 'Voice typed arithmetic override status differs from chat.', failures)
        _expect('fraction' not in voice_arithmetic_override['assistant_text'].lower(), 'Voice typed arithmetic override leaked old fraction guidance.', failures)

        chat_concept = await _send_chat('What is fraction?', chat_reveal.tutoring_state)
        voice_concept = await _send_voice(voice_service, 'What is fraction?', voice_reveal['tutoring_state'])
        _expect('part of a whole' in chat_concept.reply.lower(), 'Chat typed concept-after-finished did not answer fraction concept.', failures)
        _expect('part of a whole' in voice_concept['assistant_text'].lower(), 'Voice typed concept-after-finished did not answer fraction concept.', failures)
        _expect('-15 + 2 = -13' not in voice_concept['assistant_text'], 'Voice typed concept-after-finished repeated the old answer.', failures)
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
        print('Tutor Phase 4 voice typed-parity check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 4 voice typed-parity check passed.')
    print('- Voice typed-style Math inputs preserve the same state outcomes as chat.')
    print('- Multi-step, signed reveal, helper, arithmetic override, and concept-after-finished flows match.')


if __name__ == '__main__':
    main()
