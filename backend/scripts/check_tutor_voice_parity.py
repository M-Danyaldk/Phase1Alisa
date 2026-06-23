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
        if 'Student says: Ok now' in user or 'Student says: ok now' in user:
            return LLMResult(
                text='Great job!\n\nQuick practice question:\nWhat is -7 + 3?',
                provider='voice_e2e_fake',
                model='deterministic',
            )
        if 'Student says: 22' in user:
            return LLMResult(
                text='Not quite. Try that answer again.',
                provider='voice_e2e_fake',
                model='deterministic',
            )
        if 'Student says: 43' in user:
            return LLMResult(
                text=(
                    'Here is the first hint.\n\n'
                    'Focus only on the current step and identify what the question asks you to find.\n\n'
                    'Now try this step: whatever'
                ),
                provider='voice_e2e_fake',
                model='deterministic',
            )
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

        voice_hint_1 = await _turn(service, 'give me a hint', state)
        voice_hint_2 = await _turn(service, "I still don't understand", voice_hint_1['tutoring_state'])
        voice_hint_3 = await _turn(service, 'help me again', voice_hint_2['tutoring_state'])
        voice_support = next(iter(voice_hint_3['tutoring_state'].support_per_step.values()), None)
        _expect(voice_hint_3['tutoring_state'].attempt_count == 0, 'Voice help requests changed the answer-attempt count.', failures)
        _expect(
            voice_support is not None and voice_support.shown_hint_ids == ['concept', 'strategy', 'worked_substep'],
            'Voice help did not advance through distinct progressive hints.',
            failures,
        )
        state = started['tutoring_state']

        emotion = await _turn(service, "Why is this so hard? I'm frustrated", state)
        state = emotion['tutoring_state']
        _expect(state.mode == 'emotional_checkin' and state.expected_answer == '14', 'Voice emotion handling lost the Math step.', failures)
        continued = await _turn(service, 'one tiny step', state)
        state = continued['tutoring_state']
        _expect(state.mode == 'practice' and state.expected_answer == '14', 'Voice tiny-step choice did not restore the task.', failures)

        wrong = await _turn(service, '10', state)
        state = wrong['tutoring_state']
        _expect(state.attempt_count == 1, 'Voice answer did not use the shared attempt policy.', failures)
        _expect(wrong['model'] == 'deterministic-progressive-attempt-hint-1', 'Voice wrong answer did not use deterministic progressive guidance.', failures)
        _expect('= 12' not in wrong['assistant_text'], 'Bad arithmetic reached the voice response.', failures)

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

        voice_practice = await _turn(
            service,
            'just okay',
            TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'),
            history=[{
                'role': 'msalisia',
                'content': "Hey Sajjad! How are you doing today? Before we dive in, I'll ask one quick Math question so I know how to help.",
            }],
        )
        if voice_practice['tutoring_state'].current_question == 'What is -9 + 5?':
            wrong_voice_practice = await _turn(service, '4', voice_practice['tutoring_state'])
            corrected_voice_practice = await _turn(service, '-4', wrong_voice_practice['tutoring_state'])
            _expect(
                corrected_voice_practice['model'] == 'deterministic-voice-tutor-math-practice-check',
                'Voice correct second answer on negative-number tutor practice escaped the tutor-practice checker.',
                failures,
            )
            _expect(
                "Yes, that's correct!" in corrected_voice_practice['assistant_text']
                and corrected_voice_practice['tutoring_state'].final_answer == '-4',
                'Voice correct second answer on negative-number tutor practice was not accepted.',
                failures,
            )
            _expect(
                'keep the answer hidden' not in corrected_voice_practice['assistant_text'].lower(),
                'Voice correct second answer on negative-number tutor practice was incorrectly hidden behind the response guard.',
                failures,
            )

        followup_history = [{
            'role': 'msalisia',
            'content': "Hey Dam! How are you doing today? After you let me know, I'm going to ask you one quick Math question so I know exactly how to help you today. Sound good?",
        }]
        followup_state = TutoringState(current_subject='Math')
        for transcript in ['-9 + 5', '4', '-4']:
            result = await _turn(service, transcript, followup_state, history=followup_history)
            followup_history.extend([
                {'role': 'student', 'content': transcript},
                {'role': 'msalisia', 'content': result['assistant_text']},
            ])
            followup_state = result['tutoring_state']

        voice_followup = await _turn(service, 'Ok now', followup_state, history=followup_history)
        followup_history.extend([
            {'role': 'student', 'content': 'Ok now'},
            {'role': 'msalisia', 'content': voice_followup['assistant_text']},
        ])
        _expect(
            'What is -7 + 3?' in voice_followup['assistant_text'],
            'Voice follow-up prompt did not ask the expected quick practice question.',
            failures,
        )

        first_followup_voice = await _turn(service, '2', voice_followup['tutoring_state'], history=followup_history)
        followup_history.extend([
            {'role': 'student', 'content': '2'},
            {'role': 'msalisia', 'content': first_followup_voice['assistant_text']},
        ])
        _expect(
            '-7 + 3' in first_followup_voice['assistant_text'] and '-9 + 5' not in first_followup_voice['assistant_text'],
            'Voice first answer after the follow-up question leaked back to the earlier problem.',
            failures,
        )
        _expect(
            bool(
                first_followup_voice['tutoring_state'].current_question
                or first_followup_voice['tutoring_state'].current_step
                or first_followup_voice['tutoring_state'].active_problem
            ),
            'Voice first answer after the follow-up question did not preserve active prompt state.',
            failures,
        )
        _expect(
            first_followup_voice['tutoring_state'].attempt_count > 0
            or first_followup_voice['tutoring_state'].attempts_per_step,
            'Voice first answer after the follow-up question did not register attempt tracking.',
            failures,
        )

        repaired_voice = await _turn(service, '22', first_followup_voice['tutoring_state'], history=followup_history)
        followup_history.extend([
            {'role': 'student', 'content': '22'},
            {'role': 'msalisia', 'content': repaired_voice['assistant_text']},
        ])
        _expect(
            'What Math problem should we work on?' not in repaired_voice['assistant_text'],
            'Voice guard fallback replaced the active follow-up question with a generic recovery prompt.',
            failures,
        )

        after_repair_voice = await _turn(service, '43', repaired_voice['tutoring_state'], history=followup_history)
        lower_voice_reply = after_repair_voice['assistant_text'].lower()
        _expect(
            'what math problem should we work on?' not in lower_voice_reply
            and 'that message will not count as an answer attempt' not in lower_voice_reply,
            'Voice guard repair text leaked into the next active tutoring prompt.',
            failures,
        )

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
