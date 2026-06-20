import asyncio
from pathlib import Path

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
from backend.app.models import ChatOpeningRequest, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    stored_messages: list[object] = []
    thread_count = 0

    async def create_thread(self, *args, **kwargs):
        self.__class__.thread_count += 1
        return {'id': f'subject-baseline-thread-{self.thread_count}'}

    async def store_message(self, *args, **kwargs):
        self.stored_messages.append(args[-1])
        return {'id': 'subject-baseline-message'}


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


class _SubjectRouter:
    generated_subjects: list[tuple[str, str]] = []

    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        subject = next((name for name in ('Math', 'ELA', 'Writing') if f'Subject: {name}' in system), '')
        self.generated_subjects.append((purpose, subject))
        if purpose == 'opening':
            text = 'Hi Sajjad! How are you feeling today?'
        elif subject == 'Math':
            text = 'The numerator is the top number. In 3/4, what is the numerator?'
        elif subject == 'ELA':
            text = 'Look for the idea supported by the details. What idea do the details repeat?'
        else:
            text = 'A stronger verb makes the action clearer. Which verb could replace ran?'
        return LLMResult(text=text, provider='subject_baseline_fake', model='deterministic')


class _WordProblemRouter:
    async def generate(self, system: str, user: str, purpose: str = 'classifier') -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='subject_baseline_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'subject-baseline-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _opening(subject: str):
    return await main_module.chat_opening(ChatOpeningRequest(
        student=StudentProfile(name='Sajjad', grade=4),
        subject=subject,
        topic='general practice',
    ))


async def _send(
    subject: str,
    message: str,
    state: TutoringState | None = None,
    history: list | None = None,
    thread_id: str | None = None,
    previous_subject: str | None = None,
):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Sajjad', grade=4),
        subject=subject,
        topic='general practice',
        message=message,
        history=history or [],
        tutoring_state=state or TutoringState(current_subject=subject),
        thread_id=thread_id,
        previous_subject=previous_subject,
    ))


def _check_frontend_entry_contracts(failures: list[str]) -> None:
    root = Path(__file__).resolve().parents[2]
    learning_view = (root / 'frontend/src/views/LearningView.tsx').read_text(encoding='utf-8')
    app = (root / 'frontend/src/App.tsx').read_text(encoding='utf-8')

    _expect("initialSubject = 'Math'" in learning_view, 'Start Learning no longer defaults to Math.', failures)
    _expect('initialSubject="Math"' in app, 'Practice Math no longer opens the Math tutor.', failures)
    _expect('initialSubject="ELA"' in app, 'Practice Reading no longer opens the ELA tutor.', failures)
    _expect('initialSubject="Writing"' in app, 'Practice Writing no longer opens the Writing tutor.', failures)


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
    main_module.LLMRouter = _SubjectRouter
    word_problem_module.LLMRouter = _WordProblemRouter
    _MemoryChatStore.stored_messages = []
    _MemoryChatStore.thread_count = 0
    _SubjectRouter.generated_subjects = []
    try:
        _check_frontend_entry_contracts(failures)

        prompts = {
            'Math': 'What does numerator mean?',
            'ELA': 'Help me find the main idea in a passage about bees.',
            'Writing': 'How can I make my writing more descriptive?',
        }
        for subject, prompt in prompts.items():
            opening = await _opening(subject)
            _expect(bool(opening.reply.strip()), f'{subject} opening was empty.', failures)
            _expect(opening.history_saved, f'{subject} opening was not persisted.', failures)

            response = await _send(subject, prompt)
            _expect(bool(response.reply.strip()), f'{subject} chat response was empty.', failures)
            _expect(response.tutoring_state.current_subject == subject, f'{subject} chat changed its current subject.', failures)

        ela_boundary = await _send('ELA', '7/8 + 1/8')
        _expect(ela_boundary.model == 'deterministic-subject-boundary', 'ELA no longer redirects a Math expression.', failures)
        _expect('working on reading' in ela_boundary.reply.lower(), 'ELA boundary reply no longer identifies reading.', failures)

        writing_boundary = await _send('Writing', '12 x 4')
        _expect(writing_boundary.model == 'deterministic-subject-boundary', 'Writing no longer redirects a Math expression.', failures)
        _expect('working on writing' in writing_boundary.reply.lower(), 'Writing boundary reply no longer identifies writing.', failures)

        old_math_state = TutoringState(
            current_subject='Math',
            active_problem='3/4 + 1/4',
            current_question='What is 3/4 + 1/4?',
            expected_answer='1',
            attempt_count=2,
            mode='practice',
            status='waiting_for_student',
        )
        reading_switch = await _send(
            'Math',
            'switch to reading',
            old_math_state,
            history=[{'role': 'msalisia', 'content': 'What is 3/4 + 1/4?'}],
            thread_id='stale-math-thread',
        )
        _expect(reading_switch.resolved_subject == 'ELA' and reading_switch.subject_changed, 'Math to Reading was not resolved by the backend.', failures)
        _expect(reading_switch.tutoring_state.current_subject == 'ELA', 'Reading switch returned the wrong tutoring subject.', failures)
        _expect(not reading_switch.tutoring_state.active_problem and reading_switch.tutoring_state.attempt_count == 0, 'Reading switch retained Math task state.', failures)
        _expect(reading_switch.thread_id != 'stale-math-thread', 'Reading switch reused the stale Math thread.', failures)

        writing_switch = await _send('ELA', 'move over to writing', reading_switch.tutoring_state, thread_id=reading_switch.thread_id)
        _expect(writing_switch.resolved_subject == 'Writing' and writing_switch.subject_changed, 'Reading to Writing was not resolved by the backend.', failures)
        _expect(writing_switch.tutoring_state.current_subject == 'Writing', 'Writing switch returned the wrong tutoring subject.', failures)
        _expect(writing_switch.thread_id != reading_switch.thread_id, 'Writing switch reused the Reading thread.', failures)

        math_switch = await _send('Writing', 'change back to maths', writing_switch.tutoring_state, thread_id=writing_switch.thread_id)
        _expect(math_switch.resolved_subject == 'Math' and math_switch.subject_changed, 'Writing to Math was not resolved by the backend.', failures)
        _expect(math_switch.tutoring_state.current_subject == 'Math', 'Math switch returned the wrong tutoring subject.', failures)
        _expect(math_switch.thread_id != writing_switch.thread_id, 'Math switch reused the Writing thread.', failures)

        modern_reading_switch = await _send(
            'ELA',
            'switch to reading',
            TutoringState(current_subject='ELA'),
            previous_subject='Math',
        )
        _expect(modern_reading_switch.subject_changed, 'Frontend-isolated switch did not preserve the previous-subject signal.', failures)
        _expect(modern_reading_switch.model == 'deterministic-subject-switch', 'Backend did not own the typed switch confirmation.', failures)

        safety_state = TutoringState(
            current_subject='Math',
            mode='safety_support',
            status='waiting_for_trusted_adult',
            emotional_support_mode='safety',
        )
        blocked_switch = await _send('Math', 'switch to reading', safety_state, thread_id='safety-thread')
        _expect(blocked_switch.resolved_subject == 'Math' and not blocked_switch.subject_changed, 'Safety support allowed a subject transition.', failures)
        _expect(blocked_switch.model == 'deterministic-safety-support-lock', 'Subject wording bypassed the safety-support response.', failures)
        _expect(blocked_switch.tutoring_state.mode == 'safety_support', 'Subject wording cleared the safety-support state.', failures)

        generated = set(_SubjectRouter.generated_subjects)
        for subject in ('Math', 'ELA', 'Writing'):
            _expect(('opening', subject) in generated, f'{subject} opening prompt did not carry its subject.', failures)
            _expect(('chat', subject) in generated, f'{subject} chat prompt did not carry its subject.', failures)

        stored_subjects = {message.subject for message in _MemoryChatStore.stored_messages}
        _expect(stored_subjects == {'Math', 'ELA', 'Writing'}, 'Persisted messages lost one or more subject labels.', failures)
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
        print('Tutor subject baseline check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor subject baseline check passed.')
    print('- Start Learning and explicit practice entry subjects remain mapped correctly.')
    print('- Math, Reading, and Writing openings, chat routing, boundaries, and persistence remain intact.')
    print('- Backend subject routing isolates Math, Reading, and Writing transitions before tutor processing.')


if __name__ == '__main__':
    main()
