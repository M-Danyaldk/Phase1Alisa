import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'followup-thread'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'followup-message'}


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


class _Router:
    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        if 'Student says: Ok now' in user or 'Student says: ok now' in user:
            return LLMResult(
                text='Great job!\n\nQuick practice question:\nWhat is -7 + 3?',
                provider='followup_fake',
                model='deterministic',
            )
        if 'Student says: 22' in user:
            # This intentionally triggers the Math response guard fallback.
            return LLMResult(
                text='Not quite. Try that answer again.',
                provider='followup_fake',
                model='deterministic',
            )
        if 'Student says: 43' in user:
            return LLMResult(
                text=(
                    'Here is the first hint.\n\n'
                    'Focus only on the current step and identify what the question asks you to find.\n\n'
                    'Now try this step: whatever'
                ),
                provider='followup_fake',
                model='deterministic',
            )
        return LLMResult(text='fallback llm reply', provider='followup_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='followup_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'followup-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send(message: str, history: list[ChatHistoryItem], state: TutoringState):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject='Math',
        topic='general practice',
        message=message,
        history=history,
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
    main_module.LLMRouter = _Router
    word_problem_module.LLMRouter = _WordProblemRouter

    try:
        history = [
            ChatHistoryItem(
                role='msalisia',
                content="Hey Dam! How are you doing today? After you let me know, I'm going to ask you one quick Math question so I know exactly how to help you today. Sound good?",
            )
        ]
        state = TutoringState(current_subject='Math')

        started = await _send('-9 + 5', history, state)
        history.extend([
            ChatHistoryItem(role='student', content='-9 + 5'),
            ChatHistoryItem(role='msalisia', content=started.reply),
        ])

        wrong = await _send('4', history, started.tutoring_state)
        history.extend([
            ChatHistoryItem(role='student', content='4'),
            ChatHistoryItem(role='msalisia', content=wrong.reply),
        ])

        corrected = await _send('-4', history, wrong.tutoring_state)
        history.extend([
            ChatHistoryItem(role='student', content='-4'),
            ChatHistoryItem(role='msalisia', content=corrected.reply),
        ])

        followup = await _send('Ok now', history, corrected.tutoring_state)
        history.extend([
            ChatHistoryItem(role='student', content='Ok now'),
            ChatHistoryItem(role='msalisia', content=followup.reply),
        ])

        _expect(
            'What is -7 + 3?' in followup.reply,
            'Follow-up prompt did not ask the expected quick practice question.',
            failures,
        )

        first_followup_answer = await _send('2', history, followup.tutoring_state)
        history.extend([
            ChatHistoryItem(role='student', content='2'),
            ChatHistoryItem(role='msalisia', content=first_followup_answer.reply),
        ])

        _expect(
            '-7 + 3' in first_followup_answer.reply and '-9 + 5' not in first_followup_answer.reply,
            'First answer after the follow-up question leaked back to the earlier problem instead of the new practice question.',
            failures,
        )
        _expect(
            bool(
                first_followup_answer.tutoring_state.current_question
                or first_followup_answer.tutoring_state.current_step
                or first_followup_answer.tutoring_state.active_problem
            ),
            'First answer after the follow-up question did not preserve any active prompt state.',
            failures,
        )
        _expect(
            first_followup_answer.tutoring_state.attempt_count > 0
            or first_followup_answer.tutoring_state.attempts_per_step,
            'First answer after the follow-up question did not register attempt tracking.',
            failures,
        )

        repaired = await _send('22', history, first_followup_answer.tutoring_state)
        history.extend([
            ChatHistoryItem(role='student', content='22'),
            ChatHistoryItem(role='msalisia', content=repaired.reply),
        ])

        _expect(
            'What Math problem should we work on?' not in repaired.reply,
            'Guard fallback replaced the active follow-up question with a generic recovery prompt.',
            failures,
        )

        after_repair = await _send('43', history, repaired.tutoring_state)

        lower_reply = after_repair.reply.lower()
        _expect(
            'what math problem should we work on?' not in lower_reply
            and 'that message will not count as an answer attempt' not in lower_reply,
            'A guard repair message leaked into the next active tutoring prompt.',
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
        print('Tutor follow-up transition check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor follow-up transition check passed.')
    print('- Follow-up practice questions become active prompts with tracked attempts.')
    print('- Guard recovery text does not become the next tutoring prompt.')


if __name__ == '__main__':
    main()
