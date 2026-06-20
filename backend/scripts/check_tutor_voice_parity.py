import asyncio

import backend.app.services.voice_service as voice_module
from backend.app.models import StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    thread_count = 0

    async def create_thread(self, *args, **kwargs):
        self.__class__.thread_count += 1
        return {'id': f'voice-e2e-thread-{self.thread_count}'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'voice-e2e-message'}


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
            text='Nice try. 7 × 2 = 12. What is 7 × 2?',
            provider='voice_e2e_fake',
            model='deterministic',
        )


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _turn(
    service,
    transcript: str,
    state: TutoringState,
    subject: str = 'Math',
    history: list | None = None,
    thread_id: str | None = None,
):
    return await service._generate_tutoring_response(
        parent_id='voice-parent',
        child={'id': 'voice-child', 'name': 'Sajjad', 'grade_level': '4'},
        student=StudentProfile(name='Sajjad', grade=4),
        subject=subject,
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=history or [],
        tutoring_state=state,
        thread_id=thread_id,
    )


async def _run() -> list[str]:
    failures: list[str] = []
    originals = {
        'ChatStore': voice_module.ChatStore,
        'LearningProfileService': voice_module.LearningProfileService,
        'LearningMemoryService': voice_module.LearningMemoryService,
        'LLMRouter': voice_module.LLMRouter,
    }
    voice_module.ChatStore = _MemoryChatStore
    voice_module.LearningProfileService = _LearningProfile
    voice_module.LearningMemoryService = _LearningMemory
    voice_module.LLMRouter = _Router
    _MemoryChatStore.thread_count = 0
    try:
        service = voice_module.VoiceService()
        started = await _turn(service, 'There are 7 boxes and each box holds 2 balls. How many balls are there?', TutoringState(current_subject='Math'))
        state = started['tutoring_state']
        _expect(started['model'] == 'deterministic-voice-structured-word-problem', 'Voice word problem did not use the structured schema.', failures)
        _expect(state.expected_answer == '14' and bool(state.active_task_id), 'Voice word problem lost its answer or lifecycle task.', failures)

        emotion = await _turn(service, "Why is this so hard? I'm frustrated", state)
        state = emotion['tutoring_state']
        _expect(state.mode == 'emotional_checkin' and state.expected_answer == '14', 'Voice emotion handling lost the Math step.', failures)
        continued = await _turn(service, 'one tiny step', state)
        state = continued['tutoring_state']
        _expect(state.mode == 'practice' and state.expected_answer == '14', 'Voice tiny-step choice did not restore the task.', failures)

        wrong = await _turn(service, '10', state)
        state = wrong['tutoring_state']
        _expect(state.attempt_count == 1, 'Voice answer did not use the shared attempt policy.', failures)
        _expect('incorrect_arithmetic' in state.last_response_violations and '= 12' not in wrong['assistant_text'], 'Voice response guard did not repair bad arithmetic.', failures)

        reading_switch = await _turn(service, 'switch to reading', state, thread_id='stale-math-thread')
        reading_state = reading_switch['tutoring_state']
        _expect(reading_switch['model'] == 'deterministic-voice-subject-switch', 'Spoken Math to Reading did not use voice subject routing.', failures)
        _expect(reading_switch['resolved_subject'] == 'ELA' and reading_switch['subject_changed'], 'Spoken Math to Reading returned the wrong subject metadata.', failures)
        _expect(reading_state.current_subject == 'ELA' and reading_state.attempt_count == 0 and not reading_state.active_problem, 'Spoken Reading switch retained Math state.', failures)
        _expect(reading_switch['thread_id'] != 'stale-math-thread', 'Spoken Reading switch reused the Math thread.', failures)

        writing_switch = await _turn(service, 'move over to writing', reading_state, subject='ELA', thread_id=reading_switch['thread_id'])
        writing_state = writing_switch['tutoring_state']
        _expect(writing_switch['resolved_subject'] == 'Writing' and writing_switch['subject_changed'], 'Spoken Reading to Writing returned the wrong subject.', failures)
        _expect(writing_state.current_subject == 'Writing' and writing_switch['thread_id'] != reading_switch['thread_id'], 'Spoken Writing switch reused Reading state or thread.', failures)

        math_switch = await _turn(service, 'change back to maths', writing_state, subject='Writing', thread_id=writing_switch['thread_id'])
        _expect(math_switch['resolved_subject'] == 'Math' and math_switch['subject_changed'], 'Spoken Writing to Math returned the wrong subject.', failures)
        _expect(math_switch['tutoring_state'].current_subject == 'Math' and math_switch['thread_id'] != writing_switch['thread_id'], 'Spoken Math switch reused Writing state or thread.', failures)

        shared = await _turn(service, '24 balls are shared equally among 6 boxes. How many balls go in each box?', TutoringState(current_subject='Math'))
        _expect(shared['tutoring_state'].expected_answer == '4', 'Voice equal-sharing word problem was not division.', failures)

        crisis = await _turn(service, "I don't feel safe", state)
        locked = await _turn(service, 'continue', crisis['tutoring_state'])
        _expect(locked['model'] == 'deterministic-voice-safety-support-lock', 'Voice safety mode allowed an automatic resume.', failures)
        _expect(locked['tutoring_state'].active_task_id == '', 'Voice safety lock reactivated a learning task.', failures)
        blocked_switch = await _turn(service, 'switch to reading', crisis['tutoring_state'])
        _expect(blocked_switch['model'] == 'deterministic-voice-safety-support-lock', 'Spoken subject switch bypassed voice safety support.', failures)
        _expect(blocked_switch['resolved_subject'] == 'Math' and not blocked_switch['subject_changed'], 'Voice safety support changed subjects.', failures)
    finally:
        for name, value in originals.items():
            setattr(voice_module, name, value)
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor voice-parity check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor voice-parity check passed.')
    print('- Voice uses the same word schema, lifecycle, attempts, emotional policy, and response guard as chat.')
    print('- Spoken Math, Reading, and Writing switches isolate state and threads while preserving the safety lock.')


if __name__ == '__main__':
    main()
