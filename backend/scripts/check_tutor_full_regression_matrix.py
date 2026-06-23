import asyncio

import backend.app.main as main_module
import backend.app.services.tutor_word_problem as word_problem_module
import backend.app.services.voice_service as voice_module
from backend.app.models import ChatHistoryItem, ChatRequest, StudentProfile, TutoringState
from backend.app.services.llm.base import LLMResult
from backend.app.tutor_math_practice_bank import TutorMathPracticeQuestion


class _MemoryChatStore:
    thread_count = 0

    async def create_thread(self, *args, **kwargs):
        self.__class__.thread_count += 1
        return {'id': f'full-regression-thread-{self.thread_count}'}

    async def store_message(self, *args, **kwargs):
        return {'id': 'full-regression-message'}


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
        lowered = user.lower()
        if 'student says: ok now' in lowered:
            return LLMResult(
                text='Great job!\n\nQuick practice question:\nWhat is -7 + 3?',
                provider='full_regression_fake',
                model='deterministic',
            )
        if 'student says: 22' in lowered:
            return LLMResult(
                text='Not quite. Try that answer again.',
                provider='full_regression_fake',
                model='deterministic',
            )
        if 'student says: 43' in lowered:
            return LLMResult(
                text=(
                    'Here is the first hint.\n\n'
                    'Focus only on the current step and identify what the question asks you to find.\n\n'
                    'Now try this step: whatever'
                ),
                provider='full_regression_fake',
                model='deterministic',
            )
        return LLMResult(
            text='Fallback deterministic tutor reply.',
            provider='full_regression_fake',
            model='deterministic',
        )


class _WordProblemRouter:
    async def generate(self, *args, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"problem_type":"word_problem","operation":"","quantities":[],"unknown_label":"","expression":"","confidence":"low"}',
            provider='full_regression_fake',
            model='deterministic',
        )


async def _fake_access(*args, **kwargs):
    return {'id': 'full-regression-parent', 'child': {}}


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _send_chat(
    message: str,
    state: TutoringState,
    *,
    subject: str = 'Math',
    history: list[ChatHistoryItem] | None = None,
    thread_id: str | None = None,
    previous_subject: str | None = None,
):
    return await main_module.chat(ChatRequest(
        student=StudentProfile(name='Dam', grade=6),
        subject=subject,
        topic='general practice',
        message=message,
        history=history or [],
        tutoring_state=state,
        thread_id=thread_id,
        previous_subject=previous_subject,
    ))


async def _send_voice(
    service,
    transcript: str,
    state: TutoringState,
    *,
    subject: str = 'Math',
    history: list | None = None,
    thread_id: str | None = None,
):
    return await service._generate_tutoring_response(
        parent_id='voice-parent',
        child={'id': 'voice-child', 'name': 'Dam', 'grade_level': '6'},
        student=StudentProfile(name='Dam', grade=6),
        subject=subject,
        topic='general practice',
        topic_source='manual',
        transcript=transcript,
        history=history or [],
        tutoring_state=state,
        thread_id=thread_id,
    )


async def _chat_matrix(failures: list[str]) -> None:
    history = [
        ChatHistoryItem(
            role='msalisia',
            content="Hey Dam! How are you doing today? After you let me know, I'm going to ask you one quick Math question so I know exactly how to help you today. Sound good?",
        )
    ]
    state = TutoringState(current_subject='Math')

    started = await _send_chat('-9 + 5', state, history=history)
    _expect(started.model == 'deterministic-arithmetic_single_step-start', 'Chat bare arithmetic did not enter deterministic student arithmetic flow.', failures)
    _expect(started.tutoring_state.expected_answer == '-4', 'Chat bare arithmetic did not store the expected answer.', failures)
    history.extend([
        ChatHistoryItem(role='student', content='-9 + 5'),
        ChatHistoryItem(role='msalisia', content=started.reply),
    ])
    wrong = await _send_chat('4', started.tutoring_state, history=history)
    history.extend([
        ChatHistoryItem(role='student', content='4'),
        ChatHistoryItem(role='msalisia', content=wrong.reply),
    ])
    corrected = await _send_chat('-4', wrong.tutoring_state, history=history)
    history.extend([
        ChatHistoryItem(role='student', content='-4'),
        ChatHistoryItem(role='msalisia', content=corrected.reply),
    ])
    _expect(
        ("Yes, that's correct!" in corrected.reply or "Yes, that's right!" in corrected.reply)
        and corrected.tutoring_state.final_answer == '-4',
        'Chat corrected negative answer was not accepted cleanly.',
        failures,
    )
    _expect(corrected.model == 'deterministic-student-arithmetic-completion', 'Chat corrected bare arithmetic answer did not use deterministic completion.', failures)
    _expect('keep the answer hidden' not in corrected.reply.lower(), 'Chat tutor-practice still hid a correct answer.', failures)
    _expect(corrected.tutoring_state.mode == 'awaiting_more_practice_choice', 'Chat corrected bare arithmetic answer did not enter continuation-choice mode.', failures)

    natural_continue = await _send_chat('tell me another one please', corrected.tutoring_state, history=history)
    _expect(
        natural_continue.model == 'deterministic-tutor-math-next-practice'
        and natural_continue.tutoring_state.mode == 'tutor_practice_question',
        'Chat natural-language continuation yes did not start the next practice question.',
        failures,
    )

    clarify_choice = await _send_chat('maybe', corrected.tutoring_state, history=history)
    _expect(
        clarify_choice.model == 'deterministic-tutor-math-practice-choice-clarify'
        and clarify_choice.tutoring_state.mode == 'awaiting_more_practice_choice',
        'Chat ambiguous continuation reply did not stay inside continuation-choice clarification.',
        failures,
    )

    stop_choice = await _send_chat('no thanks', corrected.tutoring_state, history=history)
    _expect(
        stop_choice.model == 'deterministic-tutor-math-practice-close'
        and stop_choice.tutoring_state.problem_status == 'idle'
        and stop_choice.tutoring_state.mode == 'solve',
        'Chat continuation stop did not close the finished practice cleanly.',
        failures,
    )

    explain = await _send_chat('why is that right?', corrected.tutoring_state, history=history)
    _expect(explain.model == 'deterministic-tutor-math-practice-explain', 'Chat continuation explanation did not use deterministic explain flow.', failures)
    _expect('-9 + 5' in explain.reply and '-4' in explain.reply, 'Chat continuation explanation did not stay grounded in the completed problem.', failures)

    new_problem = await _send_chat('9 + 10', explain.tutoring_state, history=history)
    _expect(new_problem.model == 'deterministic-arithmetic_single_step-start', 'Chat new problem after continuation explain did not start a fresh arithmetic task.', failures)
    _expect(new_problem.tutoring_state.expected_answer == '19', 'Chat new problem after continuation explain did not store the new expected answer.', failures)

    followup = await _send_chat('Ok now', corrected.tutoring_state, history=history)
    history.extend([
        ChatHistoryItem(role='student', content='Ok now'),
        ChatHistoryItem(role='msalisia', content=followup.reply),
    ])
    followup_question = followup.tutoring_state.current_question
    _expect(
        followup.model == 'deterministic-tutor-math-next-practice'
        and bool(followup_question)
        and followup.tutoring_state.mode == 'tutor_practice_question',
        'Chat follow-up question did not appear.',
        failures,
    )

    first_followup = await _send_chat('2', followup.tutoring_state, history=history)
    history.extend([
        ChatHistoryItem(role='student', content='2'),
        ChatHistoryItem(role='msalisia', content=first_followup.reply),
    ])
    _expect(
        '-9 + 5' not in first_followup.reply and first_followup.tutoring_state.current_question == followup_question,
        'Chat follow-up answer leaked to the previous problem.',
        failures,
    )
    _expect(first_followup.tutoring_state.attempt_count > 0 or first_followup.tutoring_state.attempts_per_step, 'Chat follow-up answer did not track attempts.', failures)

    repaired = await _send_chat('22', first_followup.tutoring_state, history=history)
    history.extend([
        ChatHistoryItem(role='student', content='22'),
        ChatHistoryItem(role='msalisia', content=repaired.reply),
    ])
    _expect('What Math problem should we work on?' not in repaired.reply, 'Chat guard fallback replaced the active follow-up prompt.', failures)

    after_repair = await _send_chat('43', repaired.tutoring_state, history=history)
    lower_reply = after_repair.reply.lower()
    _expect('what math problem should we work on?' not in lower_reply, 'Chat repair text leaked into the next prompt.', failures)
    _expect('that message will not count as an answer attempt' not in lower_reply, 'Chat repair warning leaked into the next prompt.', failures)

    practice_state = TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin')
    practice_history = [ChatHistoryItem(role='msalisia', content="Hey Dam! How are you doing today? Before we dive in, I'll ask one quick Math question so I know how to help.")]
    practice = await _send_chat('just okay', practice_state, history=practice_history)
    switched = await _send_chat(
        'There are 3 boxes with 2 balls in each box. How many balls are there?',
        practice.tutoring_state,
        history=practice_history,
    )
    _expect(switched.model == 'deterministic-structured-word-problem', 'Chat tutor-practice to student-entered problem did not use structured Math flow.', failures)
    _expect(switched.tutoring_state.problem_status != 'tutor_practice', 'Chat student-entered problem stayed trapped in tutor-practice mode.', failures)
    _expect(switched.tutoring_state.expected_answer == '6', 'Chat student-entered problem did not store its own answer.', failures)

    topic_started = await _send_chat('teach me fractions', TutoringState(current_subject='Math'))
    _expect(topic_started.model == 'deterministic-math-topic-switch', 'Chat topic lesson did not use deterministic topic entry.', failures)
    topic_answered = await _send_chat(topic_started.tutoring_state.expected_answer, topic_started.tutoring_state)
    _expect(topic_answered.model == 'deterministic-tutor-math-practice-check', 'Chat topic starter answer did not return through tutor-practice checking.', failures)
    _expect(topic_answered.tutoring_state.active_task_id == '', 'Chat topic starter left a completed task active.', failures)

    switch_source = TutoringState(
        current_subject='Math',
        active_problem='3/4 + 1/4',
        current_question='What is 3/4 + 1/4?',
        expected_answer='1',
        attempt_count=2,
        mode='practice',
        status='waiting_for_student',
    )
    switched_subject = await _send_chat(
        'switch to reading',
        switch_source,
        history=[ChatHistoryItem(role='msalisia', content='What is 3/4 + 1/4?')],
        thread_id='chat-math-thread',
    )
    _expect(switched_subject.subject_changed and switched_subject.resolved_subject == 'ELA', 'Chat subject switch did not resolve to reading.', failures)
    _expect(switched_subject.tutoring_state.current_subject == 'ELA', 'Chat subject switch returned the wrong tutoring state.', failures)
    _expect(not switched_subject.tutoring_state.active_problem and switched_subject.tutoring_state.attempt_count == 0, 'Chat subject switch retained Math state.', failures)
    _expect(switched_subject.thread_id != 'chat-math-thread', 'Chat subject switch reused the old Math thread.', failures)

    safety_state = TutoringState(
        current_subject='Math',
        mode='safety_support',
        status='waiting_for_trusted_adult',
        emotional_support_mode='safety',
    )
    blocked = await _send_chat('switch to reading', safety_state, thread_id='chat-safety-thread')
    _expect(blocked.model == 'deterministic-safety-support-lock', 'Chat safety support allowed a subject change.', failures)
    _expect(not blocked.subject_changed and blocked.resolved_subject == 'Math', 'Chat safety support changed the active subject.', failures)


async def _voice_matrix(failures: list[str]) -> None:
    service = voice_module.VoiceService()
    history = [{
        'role': 'msalisia',
        'content': "Hey Dam! How are you doing today? After you let me know, I'm going to ask you one quick Math question so I know exactly how to help you today. Sound good?",
    }]
    state = TutoringState(current_subject='Math')

    started = await _send_voice(service, '-9 + 5', state, history=history)
    history.extend([
        {'role': 'student', 'content': '-9 + 5'},
        {'role': 'msalisia', 'content': started['assistant_text']},
    ])
    wrong = await _send_voice(service, '4', started['tutoring_state'], history=history)
    history.extend([
        {'role': 'student', 'content': '4'},
        {'role': 'msalisia', 'content': wrong['assistant_text']},
    ])
    spoken_corrected = await _send_voice(service, 'negative four', wrong['tutoring_state'], history=history)
    _expect(
        ("Yes, that's correct!" in spoken_corrected['assistant_text'] or "Yes, that's right!" in spoken_corrected['assistant_text'])
        and spoken_corrected['tutoring_state'].final_answer == '-4',
        'Voice spoken corrected negative answer was not accepted cleanly.',
        failures,
    )
    corrected = await _send_voice(service, '-4', wrong['tutoring_state'], history=history)
    history.extend([
        {'role': 'student', 'content': '-4'},
        {'role': 'msalisia', 'content': corrected['assistant_text']},
    ])
    _expect(
        ("Yes, that's correct!" in corrected['assistant_text'] or "Yes, that's right!" in corrected['assistant_text'])
        and corrected['tutoring_state'].final_answer == '-4',
        'Voice corrected negative answer was not accepted cleanly.',
        failures,
    )
    _expect('keep the answer hidden' not in corrected['assistant_text'].lower(), 'Voice tutor-practice still hid a correct answer.', failures)
    _expect(corrected['tutoring_state'].mode == 'awaiting_more_practice_choice', 'Voice corrected bare arithmetic answer did not enter continuation-choice mode.', failures)

    natural_continue = await _send_voice(service, 'tell me another one please', corrected['tutoring_state'], history=history)
    _expect(
        natural_continue['model'] == 'deterministic-voice-tutor-math-next-practice'
        and natural_continue['tutoring_state'].mode == 'tutor_practice_question',
        'Voice natural-language continuation yes did not start the next practice question.',
        failures,
    )

    clarify_choice = await _send_voice(service, 'maybe', corrected['tutoring_state'], history=history)
    _expect(
        clarify_choice['model'] == 'deterministic-voice-tutor-math-practice-choice-clarify'
        and clarify_choice['tutoring_state'].mode == 'awaiting_more_practice_choice',
        'Voice ambiguous continuation reply did not stay inside continuation-choice clarification.',
        failures,
    )

    stop_choice = await _send_voice(service, 'no thanks', corrected['tutoring_state'], history=history)
    _expect(
        stop_choice['model'] == 'deterministic-voice-tutor-math-practice-close'
        and stop_choice['tutoring_state'].problem_status == 'idle'
        and stop_choice['tutoring_state'].mode == 'solve',
        'Voice continuation stop did not close the finished practice cleanly.',
        failures,
    )

    explain = await _send_voice(service, 'why is that right?', corrected['tutoring_state'], history=history)
    _expect(explain['model'] == 'deterministic-voice-tutor-math-practice-explain', 'Voice continuation explanation did not use deterministic explain flow.', failures)
    _expect('-9 + 5' in explain['assistant_text'] and '-4' in explain['assistant_text'], 'Voice continuation explanation did not stay grounded in the completed problem.', failures)

    new_problem = await _send_voice(service, '9 + 10', explain['tutoring_state'], history=history)
    _expect(new_problem['model'] == 'deterministic-arithmetic_single_step-start', 'Voice new problem after continuation explain did not start a fresh arithmetic task.', failures)
    _expect(new_problem['tutoring_state'].expected_answer == '19', 'Voice new problem after continuation explain did not store the new expected answer.', failures)

    followup = await _send_voice(service, 'Ok now', corrected['tutoring_state'], history=history)
    history.extend([
        {'role': 'student', 'content': 'Ok now'},
        {'role': 'msalisia', 'content': followup['assistant_text']},
    ])
    followup_question = followup['tutoring_state'].current_question
    _expect(
        followup['model'] == 'deterministic-voice-tutor-math-next-practice'
        and bool(followup_question)
        and followup['tutoring_state'].mode == 'tutor_practice_question',
        'Voice follow-up question did not appear.',
        failures,
    )

    first_followup = await _send_voice(service, '2', followup['tutoring_state'], history=history)
    history.extend([
        {'role': 'student', 'content': '2'},
        {'role': 'msalisia', 'content': first_followup['assistant_text']},
    ])
    _expect(
        '-9 + 5' not in first_followup['assistant_text'] and first_followup['tutoring_state'].current_question == followup_question,
        'Voice follow-up answer leaked to the previous problem.',
        failures,
    )
    _expect(first_followup['tutoring_state'].attempt_count > 0 or first_followup['tutoring_state'].attempts_per_step, 'Voice follow-up answer did not track attempts.', failures)
    repaired = await _send_voice(service, '22', first_followup['tutoring_state'], history=history)
    history.extend([
        {'role': 'student', 'content': '22'},
        {'role': 'msalisia', 'content': repaired['assistant_text']},
    ])
    _expect('What Math problem should we work on?' not in repaired['assistant_text'], 'Voice guard fallback replaced the active follow-up prompt.', failures)
    after_repair = await _send_voice(service, '43', repaired['tutoring_state'], history=history)
    lower_reply = after_repair['assistant_text'].lower()
    _expect('what math problem should we work on?' not in lower_reply, 'Voice repair text leaked into the next prompt.', failures)
    _expect('that message will not count as an answer attempt' not in lower_reply, 'Voice repair warning leaked into the next prompt.', failures)

    practice = await _send_voice(
        service,
        'just okay',
        TutoringState(current_subject='Math', mode='opening_checkin', status='ready_for_mini_checkin'),
        history=[{
            'role': 'msalisia',
            'content': "Hey Dam! How are you doing today? Before we dive in, I'll ask one quick Math question so I know how to help.",
        }],
    )
    switched = await _send_voice(
        service,
        'There are 3 boxes with 2 balls in each box. How many balls are there?',
        practice['tutoring_state'],
    )
    _expect(switched['model'] == 'deterministic-voice-structured-word-problem', 'Voice tutor-practice to student-entered problem did not use structured Math flow.', failures)
    _expect(switched['tutoring_state'].problem_status != 'tutor_practice', 'Voice student-entered problem stayed trapped in tutor-practice mode.', failures)
    _expect(switched['tutoring_state'].expected_answer == '6', 'Voice student-entered problem did not store its own answer.', failures)
    switched_subject = await _send_voice(
        service,
        'switch to reading',
        TutoringState(
            current_subject='Math',
            active_problem='3/4 + 1/4',
            current_question='What is 3/4 + 1/4?',
            expected_answer='1',
            attempt_count=2,
            mode='practice',
            status='waiting_for_student',
        ),
        thread_id='voice-math-thread',
    )
    _expect(switched_subject['subject_changed'] and switched_subject['resolved_subject'] == 'ELA', 'Voice subject switch did not resolve to reading.', failures)
    _expect(switched_subject['tutoring_state'].current_subject == 'ELA', 'Voice subject switch returned the wrong tutoring state.', failures)
    _expect(not switched_subject['tutoring_state'].active_problem and switched_subject['tutoring_state'].attempt_count == 0, 'Voice subject switch retained Math state.', failures)
    _expect(switched_subject['thread_id'] != 'voice-math-thread', 'Voice subject switch reused the old Math thread.', failures)

    safety_state = TutoringState(
        current_subject='Math',
        mode='safety_support',
        status='waiting_for_trusted_adult',
        emotional_support_mode='safety',
    )
    blocked = await _send_voice(service, 'switch to reading', safety_state)
    _expect(blocked['model'] == 'deterministic-voice-safety-support-lock', 'Voice safety support allowed a subject change.', failures)
    _expect(not blocked['subject_changed'] and blocked['resolved_subject'] == 'Math', 'Voice safety support changed the active subject.', failures)


async def _run() -> list[str]:
    failures: list[str] = []
    fixed_followup_question = TutorMathPracticeQuestion(
        id='full-regression-fixed-followup',
        grade=6,
        topic='integer operations',
        skill='integer addition',
        question='What is 5 - 9?',
        expected_answer='-4',
        accepted_answers=('-4',),
        hint_1='Think about starting at 5 and moving back 9.',
        hint_2='5 - 9 lands 4 below zero.',
        worked_explanation='5 - 9 = -4.',
        difficulty='quick',
    )
    originals = {
        'main_require_child_access': main_module.require_child_access,
        'main_ChatStore': main_module.ChatStore,
        'main_LearningProfileService': main_module.LearningProfileService,
        'main_LearningMemoryService': main_module.LearningMemoryService,
        'main_LLMRouter': main_module.LLMRouter,
        'main_select_tutor_math_question': main_module.select_tutor_math_question,
        'voice_ChatStore': voice_module.ChatStore,
        'voice_LearningProfileService': voice_module.LearningProfileService,
        'voice_LearningMemoryService': voice_module.LearningMemoryService,
        'voice_LLMRouter': voice_module.LLMRouter,
        'voice_select_tutor_math_question': voice_module.select_tutor_math_question,
        'word_problem_LLMRouter': word_problem_module.LLMRouter,
    }
    main_module.require_child_access = _fake_access
    main_module.ChatStore = _MemoryChatStore
    main_module.LearningProfileService = _LearningProfile
    main_module.LearningMemoryService = _LearningMemory
    main_module.LLMRouter = _Router
    main_module.select_tutor_math_question = lambda *args, **kwargs: fixed_followup_question
    voice_module.ChatStore = _MemoryChatStore
    voice_module.LearningProfileService = _LearningProfile
    voice_module.LearningMemoryService = _LearningMemory
    voice_module.LLMRouter = _Router
    voice_module.select_tutor_math_question = lambda *args, **kwargs: fixed_followup_question
    word_problem_module.LLMRouter = _WordProblemRouter
    _MemoryChatStore.thread_count = 0
    try:
        await _chat_matrix(failures)
        await _voice_matrix(failures)
    finally:
        main_module.require_child_access = originals['main_require_child_access']
        main_module.ChatStore = originals['main_ChatStore']
        main_module.LearningProfileService = originals['main_LearningProfileService']
        main_module.LearningMemoryService = originals['main_LearningMemoryService']
        main_module.LLMRouter = originals['main_LLMRouter']
        main_module.select_tutor_math_question = originals['main_select_tutor_math_question']
        voice_module.ChatStore = originals['voice_ChatStore']
        voice_module.LearningProfileService = originals['voice_LearningProfileService']
        voice_module.LearningMemoryService = originals['voice_LearningMemoryService']
        voice_module.LLMRouter = originals['voice_LLMRouter']
        voice_module.select_tutor_math_question = originals['voice_select_tutor_math_question']
        word_problem_module.LLMRouter = originals['word_problem_LLMRouter']
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor full regression matrix check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor full regression matrix check passed.')
    print('- Chat and voice both preserve tutor-practice, follow-up, student-entered, topic, subject-switch, and safety flows.')
    print('- High-risk cross-flow regressions stay isolated instead of leaking stale prompts, stale attempts, or stale tasks.')


if __name__ == '__main__':
    main()
