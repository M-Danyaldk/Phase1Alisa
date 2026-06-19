import asyncio

import backend.app.services.voice_service as voice_module
from backend.app.models import StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult


class _MemoryChatStore:
    async def create_thread(self, *args, **kwargs):
        return {'id': 'voice-e2e-thread'}

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


async def _turn(service, transcript: str, state: TutoringState):
    return await service._generate_tutoring_response(
        parent_id='voice-parent',
        child={'id': 'voice-child', 'name': 'Sajjad', 'grade_level': '4'},
        student=StudentProfile(name='Sajjad', grade=4),
        subject='Math',
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=[],
        tutoring_state=state,
        thread_id=None,
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

        shared = await _turn(service, '24 balls are shared equally among 6 boxes. How many balls go in each box?', TutoringState(current_subject='Math'))
        _expect(shared['tutoring_state'].expected_answer == '4', 'Voice equal-sharing word problem was not division.', failures)

        crisis = await _turn(service, "I don't feel safe", state)
        locked = await _turn(service, 'continue', crisis['tutoring_state'])
        _expect(locked['model'] == 'deterministic-voice-safety-support-lock', 'Voice safety mode allowed an automatic resume.', failures)
        _expect(locked['tutoring_state'].active_task_id == '', 'Voice safety lock reactivated a learning task.', failures)
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


if __name__ == '__main__':
    main()
