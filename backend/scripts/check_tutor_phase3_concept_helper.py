import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult
from backend.app.tutor_math_practice_support import build_tutor_practice_support_reply


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'phase3-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'phase3-message'}


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
        return LLMResult(text='Fallback deterministic tutor reply.', provider='phase3_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='phase3_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'phase3-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _fraction_compare_state() -> TutoringState:
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
        tutor_practice_question_id='phase3-fraction-compare',
        tutor_practice_topic='equivalent fractions',
        tutor_practice_hint_1='Both fractions have the same denominator, so compare the numerators.',
        tutor_practice_hint_2='Both fractions are sixths. Compare 5 and 4.',
        tutor_practice_explanation='5/6 is larger than 4/6 because 5 is greater than 4.',
    )


async def _send(message: str, state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='equivalent fractions',
        message=message,
        history=[ChatHistoryItem(role='msalisia', content=state.current_question or 'Opening check-in')],
        tutoring_state=state,
    ))


async def _run() -> list[str]:
    failures: list[str] = []
    originals = {
        'main_require_child_access': main_module.require_child_access,
        'main_ChatStore': main_module.ChatStore,
        'main_LearningProfileService': main_module.LearningProfileService,
        'main_LearningMemoryService': main_module.LearningMemoryService,
        'main_LLMRouter': main_module.LLMRouter,
        'word_problem_LLMRouter': word_problem_module.LLMRouter,
    }
    main_module.require_child_access = _fake_access
    main_module.ChatStore = _MemoryChatStore
    main_module.LearningProfileService = _LearningProfile
    main_module.LearningMemoryService = _LearningMemory
    main_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        state = _fraction_compare_state()

        denominator_reply, denominator_state = build_tutor_practice_support_reply(state, 'what is denominator?')
        _expect('bottom number' in denominator_reply.lower(), 'Denominator support did not define denominator.', failures)
        _expect('denominator is 6' in denominator_reply.lower(), 'Denominator support did not use the active fraction denominator.', failures)
        _expect('4 equal parts' not in denominator_reply.lower(), 'Denominator support still contains the old hardcoded denominator.', failures)
        _expect(denominator_state.current_question == state.current_question, 'Denominator support changed the active question.', failures)
        _expect(denominator_state.expected_answer == '5/6', 'Denominator support lost the expected answer.', failures)

        numerator_reply, _ = build_tutor_practice_support_reply(state, 'what is numerator?')
        _expect('numerators are 5 and 4' in numerator_reply.lower(), 'Numerator support did not explain the active numerators.', failures)
        _expect('talking about 1 part' not in numerator_reply.lower(), 'Numerator support still contains the old hardcoded numerator.', failures)

        definition_reply, definition_state = build_tutor_practice_support_reply(state, 'what is fraction?')
        _expect('part of a whole' in definition_reply.lower(), 'Fraction support did not answer the concept question.', failures)
        _expect('5/6 and 4/6' in definition_reply, 'Fraction support did not connect back to the active fractions.', failures)
        _expect(definition_state.current_question == state.current_question, 'Fraction support changed the active question.', failures)

        first_hint = await _send('give me a hint', state)
        denominator_chat = await _send('what is denominator?', first_hint.tutoring_state)
        _expect(denominator_chat.model == 'deterministic-tutor-math-practice-support', 'Chat denominator question did not use tutor-practice support.', failures)
        _expect('denominator is 6' in denominator_chat.reply.lower(), 'Chat denominator support did not use the active denominator.', failures)
        _expect(denominator_chat.tutoring_state.current_question == state.current_question, 'Chat denominator support changed current question.', failures)
        _expect(denominator_chat.tutoring_state.expected_answer == '5/6', 'Chat denominator support lost expected answer.', failures)
        _expect(denominator_chat.tutoring_state.attempt_count == 0, 'Chat support request counted as an answer attempt.', failures)

        correct = await _send('5/6', denominator_chat.tutoring_state)
        _expect(correct.model == 'deterministic-tutor-math-practice-check', 'Correct answer after support was not graded by tutor-practice check.', failures)
        _expect(correct.tutoring_state.final_answer == '5/6', 'Correct answer after support did not finish with the expected answer.', failures)
        _expect(correct.tutoring_state.problem_status == 'finished', 'Correct answer after support did not finish the task.', failures)
    finally:
        main_module.require_child_access = originals['main_require_child_access']
        main_module.ChatStore = originals['main_ChatStore']
        main_module.LearningProfileService = originals['main_LearningProfileService']
        main_module.LearningMemoryService = originals['main_LearningMemoryService']
        main_module.LLMRouter = originals['main_LLMRouter']
        word_problem_module.LLMRouter = originals['word_problem_LLMRouter']
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor Phase 3 concept/helper check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 3 concept/helper check passed.')
    print('- Fraction concept helpers derive numerator and denominator from the active question.')
    print('- Helper interruptions preserve gradeable tutor-practice state and accept the next correct answer.')


if __name__ == '__main__':
    main()
