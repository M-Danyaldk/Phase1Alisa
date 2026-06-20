import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult
from backend.app.tutor_math_topic_lessons import all_topic_lessons


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'topic-e2e-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'topic-e2e-message'}


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
        return LLMResult(
            text='Let’s stay with the active practice question.',
            provider='topic_e2e_fake',
            model='deterministic',
            fallback_used=False,
        )


class _WordProblemRouter:
    async def generate(self, system: str, user: str, purpose: str = 'classifier') -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='topic_e2e_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'topic-e2e-parent', 'child': {}}


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
        for lesson in all_topic_lessons():
            started = await _send(f'teach me {lesson.label}', TutoringState(current_subject='Math'))
            state = started.tutoring_state
            _expect(started.model == 'deterministic-math-topic-switch', f'{lesson.topic_key} did not use deterministic topic-start.', failures)
            _expect(lesson.explanation in started.reply, f'{lesson.topic_key} reply missed the explanation.', failures)
            _expect(lesson.example in started.reply, f'{lesson.topic_key} reply missed the example.', failures)
            _expect(lesson.starter_question in started.reply, f'{lesson.topic_key} reply missed the starter question.', failures)
            _expect(state.mode == 'tutor_practice_question', f'{lesson.topic_key} did not enter tutor practice mode.', failures)
            _expect(state.current_question == lesson.starter_question, f'{lesson.topic_key} stored the wrong starter question.', failures)
            _expect(state.expected_answer == lesson.expected_answer, f'{lesson.topic_key} stored the wrong expected answer.', failures)
            _expect(state.skill == lesson.topic_key, f'{lesson.topic_key} stored the wrong skill.', failures)
            _expect(state.attempt_count == 0, f'{lesson.topic_key} topic request counted as an attempt.', failures)

            answered = await _send(lesson.expected_answer, state)
            answered_state = answered.tutoring_state
            _expect(
                answered.model == 'deterministic-tutor-math-practice-check',
                f'{lesson.topic_key} starter answer did not use tutor-practice checking; got {answered.model}.',
                failures,
            )
            _expect(answered_state.final_answer == lesson.expected_answer, f'{lesson.topic_key} did not finish with the expected answer.', failures)
            _expect(answered_state.active_task_id == '', f'{lesson.topic_key} left a completed topic starter active.', failures)
            _expect(
                any(record.status == 'completed' and record.problem_text == lesson.starter_question for record in answered_state.task_records),
                f'{lesson.topic_key} completion was not recorded in task history.',
                failures,
            )
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
        print('Tutor topic endpoint matrix check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor topic endpoint matrix check passed.')
    print('- Every supported Math topic starts a deterministic mini-lesson through the real chat endpoint.')
    print('- Every topic starter answer completes through tutor-practice checking.')


if __name__ == '__main__':
    main()
