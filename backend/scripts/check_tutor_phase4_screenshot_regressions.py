import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'phase4-screenshot-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'phase4-screenshot-message'}


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
                provider='phase4_screenshot_fake',
                model='deterministic',
            )
        return LLMResult(text='Fallback deterministic tutor reply.', provider='phase4_screenshot_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='phase4_screenshot_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'phase4-screenshot-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send(message: str, state: TutoringState, history: list[ChatHistoryItem] | None = None):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        message=message,
        history=history or [ChatHistoryItem(role='msalisia', content=state.current_question or 'Opening check-in')],
        tutoring_state=state,
    ))


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
        tutor_practice_question_id='phase4-screenshot-fraction-compare',
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
        'word_problem_LLMRouter': word_problem_module.LLMRouter,
    }
    main_module.require_child_access = _fake_access
    main_module.ChatStore = _MemoryChatStore
    main_module.LearningProfileService = _LearningProfile
    main_module.LearningMemoryService = _LearningMemory
    main_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter
    try:
        fraction_state = _fraction_practice_state()
        first_wrong = await _send('4/6', fraction_state)
        second_wrong = await _send('4', first_wrong.tutoring_state)
        correct_fraction = await _send('5/6', second_wrong.tutoring_state)
        _expect(correct_fraction.model == 'deterministic-tutor-math-practice-check', 'Screenshot fraction correction did not use tutor-practice checking.', failures)
        _expect(correct_fraction.tutoring_state.final_answer == '5/6', 'Screenshot fraction correction did not finish with 5/6.', failures)
        _expect('Would you like another practice question?' in correct_fraction.reply, 'Screenshot fraction completion did not offer continuation.', failures)

        denominator = await _send('what is denominator?', fraction_state)
        _expect('denominator is 6' in denominator.reply.lower(), 'Screenshot denominator helper did not use denominator 6.', failures)
        _expect(denominator.tutoring_state.current_question == fraction_state.current_question, 'Screenshot denominator helper changed the active fraction question.', failures)
        _expect(denominator.tutoring_state.expected_answer == '5/6', 'Screenshot denominator helper lost expected answer.', failures)

        arithmetic_override = await _send('-152 +32', fraction_state)
        _expect(arithmetic_override.model in {'deterministic-arithmetic_single_step-start', 'deterministic-structured-roadmap'}, 'Screenshot arithmetic entry from tutor practice did not start a new Math task.', failures)
        _expect(arithmetic_override.tutoring_state.current_question in {'What is -152 + 32?', 'What is -152 +32?'}, 'Screenshot arithmetic entry did not store the new question.', failures)
        _expect(arithmetic_override.tutoring_state.expected_answer == '-120', 'Screenshot arithmetic entry did not store -120.', failures)
        _expect('fraction' not in arithmetic_override.reply.lower(), 'Screenshot arithmetic entry leaked old fraction guidance.', failures)

        expression = '9/8 + 7/4 * 8/9+(10 x 23/2)'
        structured = await _send(expression, TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        _expect(structured.model == 'deterministic-structured-roadmap', 'Screenshot multi-step expression did not route to structured roadmap.', failures)
        _expect(len(structured.tutoring_state.ordered_steps) == 4, 'Screenshot multi-step expression did not keep the full roadmap.', failures)
        _expect(structured.tutoring_state.current_question == 'What is 10 × 23/2?', 'Screenshot multi-step expression did not start at the parentheses step.', failures)
        structured_hint = await _send('Give me one small hint.', structured.tutoring_state)
        _expect(structured_hint.tutoring_state.current_question == structured.tutoring_state.current_question, 'Screenshot structured helper lost current question.', failures)
        _expect('9/8 + 7/4 * 8/9' not in structured_hint.reply or 'Now try this step:' in structured_hint.reply, 'Screenshot structured helper exposed future roadmap incorrectly.', failures)
        structured_fallback = await _send('Whay', structured_hint.tutoring_state)
        _expect('What Math problem should we work on?' not in structured_fallback.reply, 'Screenshot structured fallback became generic repair text.', failures)
        _expect(structured_fallback.tutoring_state.current_question == structured.tutoring_state.current_question, 'Screenshot structured fallback lost current question.', failures)

        signed_start = await _send('-15 + 2', TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'))
        signed_wrong_1 = await _send('261', signed_start.tutoring_state)
        signed_wrong_2 = await _send('378282', signed_wrong_1.tutoring_state)
        signed_reveal = await _send('666', signed_wrong_2.tutoring_state)
        _expect(signed_reveal.model == 'deterministic-student-arithmetic-reveal', 'Screenshot signed arithmetic did not reveal on third wrong answer.', failures)
        _expect('**Final answer:** -13.' in signed_reveal.reply, 'Screenshot signed arithmetic reveal omitted -13.', failures)
        _expect('LetÃ' not in signed_reveal.reply and 'â' not in signed_reveal.reply, 'Screenshot signed arithmetic reply contains mojibake.', failures)

        concept_after_finished = await _send('What is fraction?', signed_reveal.tutoring_state)
        _expect('part of a whole' in concept_after_finished.reply.lower(), 'Screenshot finished-problem concept question did not answer fraction concept.', failures)
        _expect('-15 + 2 = -13' not in concept_after_finished.reply, 'Screenshot finished-problem concept question repeated the old answer.', failures)
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
        print('Tutor Phase 4 screenshot regression check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor Phase 4 screenshot regression check passed.')
    print('- Screenshot fraction helper, arithmetic override, multi-step, signed reveal, and concept-after-finished cases stay fixed.')


if __name__ == '__main__':
    main()
