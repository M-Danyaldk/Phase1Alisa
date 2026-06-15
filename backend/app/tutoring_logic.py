import hashlib
import re

from .models import ChatHistoryItem, TutorHelperBranch, TutorQueuedQuestion, TutoringState

DIRECT_HELP_PHRASES = [
    'solve',
    'solution',
    'answer',
    'give me',
    'help me',
    "i don't know",
    'i dont know',
    'stuck',
    'explain',
    'show me',
    'do it',
    'what is the answer',
]

CONFUSED_PHRASES = [
    'no',
    "i don't know",
    'i dont know',
    'i do not know',
    "i am stuck",
    "i'm stuck",
    'stuck',
    'help me',
    'what?',
    'how?',
]

CONTEXT_CLARIFICATION_PHRASES = [
    'we were on',
    'we are on',
    'we were working on',
    'we are working on',
    'we just did',
    'last question was',
    'the question was',
    'you asked',
    'you were asking',
    'i was doing',
    'i am doing',
    'i meant',
    'that was about',
    'we were talking about',
]

TUTOR_CONCERN_PHRASES = [
    'you should know',
    'do you remember',
    'you forgot',
    'is everything okay',
    'are you okay',
    'what happened',
    'why did you',
    'that is not what',
    'that was not what',
    'we already',
    'you switched',
    'wrong subject',
    'not reading',
    'not fractions',
]

HOMEWORK_SKIP_PHRASES = [
    'homework',
    'worksheet',
    'assignment',
    'uploaded',
    'upload',
    'skip it',
    'skip this',
    'skip the check',
    'skip check',
    'no check',
    'straight to homework',
    'just homework',
]

SWITCH_TASK_PHRASES = [
    'switch',
    'new problem instead',
    'leave this',
    'skip this problem',
    'do this instead',
    'different problem instead',
]

ACTION_INTENTS = {
    'hint': ['hint', 'give me a hint', 'help without answer'],
    'explain_again': ['explain again', 'say it another way', 'again', "i still don't get it", 'i still do not get it'],
    'example': ['example', 'give me an example', 'show example'],
    'check_answer': ['check my answer', 'is this right', 'is my answer right', 'check this'],
}


def _normalized(text: str) -> str:
    return ' '.join(text.lower().strip().split())


def _contains_any(text: str, phrases: list[str]) -> bool:
    normalized = _normalized(text)
    return any(phrase in normalized for phrase in phrases)


def detect_direct_help_intent(message: str) -> bool:
    return _contains_any(message, DIRECT_HELP_PHRASES)


def detect_homework_or_skip_intent(message: str) -> bool:
    normalized = _normalized(message)
    return normalized == 'skip' or any(phrase in normalized for phrase in HOMEWORK_SKIP_PHRASES)


def detect_confused_intent(message: str) -> bool:
    return _contains_any(message, CONFUSED_PHRASES)


def detect_context_clarification_intent(message: str) -> bool:
    return _contains_any(message, CONTEXT_CLARIFICATION_PHRASES)


def detect_tutor_concern_intent(message: str) -> bool:
    normalized = _normalized(message)
    if _contains_any(message, TUTOR_CONCERN_PHRASES):
        return True
    return bool(re.search(r'\b(why|how)\s+(did|are|were|can)\s+you\b', normalized))


def detect_definition_intent(message: str) -> bool:
    text = _normalized(message)
    if any(char.isdigit() for char in message) and any(symbol in message for symbol in ['+', '-', '*', '/', '=', '×', '÷']):
        return False
    return bool(re.search(r'^(what is|what are|what does|what means|define|how do i)\b', text))


def detect_switch_task_intent(message: str) -> bool:
    return _contains_any(message, SWITCH_TASK_PHRASES)


def detect_math_expression(message: str) -> bool:
    if not any(char.isdigit() for char in message):
        return False
    if re.search(r'\d\s*[xX]\s*\d', message):
        return True
    return any(symbol in message for symbol in ['+', '-', '*', '/', '=', '×', '÷'])


def detect_action_intent(message: str) -> str:
    text = _normalized(message)
    for action, phrases in ACTION_INTENTS.items():
        if any(phrase in text for phrase in phrases):
            return action
    return ''


def _looks_like_short_reply(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False
    if detect_math_expression(message):
        return False
    if len(text) <= 20:
        return True
    if text in {'no', 'yes', 'okay', 'ok', 'what?', 'how?', "i don't know", 'i dont know', 'i do not know'}:
        return True
    return False


def _looks_like_new_problem(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False
    if _looks_like_short_reply(message):
        return False
    if detect_math_expression(message):
        return True

    starters = (
        'what is',
        'what are',
        'solve',
        'teach me',
        'tell me about',
        'help me with',
        'fix this sentence',
        'fix this',
        'write',
        'read this',
        'explain',
    )
    return text.startswith(starters) or len(text) > 24


def _looks_like_answer_to_current_math_step(message: str, current_question: str) -> bool:
    text = _normalized(message)
    if not current_question.strip() or not text:
        return False
    if text in {'yes', 'no', 'ok', 'okay'}:
        return False
    if not any(char.isdigit() for char in message):
        return False
    if len(text) > 32:
        return False
    if detect_math_expression(message):
        return True
    return bool(re.fullmatch(r'-?\d+(?:\.\d+)?', text))


def _question_id(text: str) -> str:
    return hashlib.sha1(_normalized(text).encode('utf-8')).hexdigest()[:12]


def _same_prompt(left: str, right: str) -> bool:
    return _normalized(left) == _normalized(right)


def _has_unfinished_main_problem(state: TutoringState) -> bool:
    if state.main_problem.strip():
        return state.problem_status not in {'finished', 'idle'}
    if state.current_question.strip() or state.current_step.strip():
        return True
    return bool(state.active_problem.strip() and state.status not in {'finished', 'idle'})


def _has_used_helper_branch(state: TutoringState) -> bool:
    return bool(state.helper_branch.question and state.helper_branch.status in {'active', 'completed'})


def _append_queued_followup_question(state: TutoringState, message: str, subject: str = '') -> list[TutorQueuedQuestion]:
    question = message.strip()
    if not question:
        return list(state.queued_followup_questions)

    normalized_question = _normalized(question)
    existing = list(state.queued_followup_questions)
    for queued in existing:
        if _same_prompt(queued.question, normalized_question):
            return existing

    if state.helper_branch.question and _same_prompt(state.helper_branch.question, normalized_question):
        return existing

    existing.append(TutorQueuedQuestion(
        question_id=_question_id(question),
        question=question,
        subject=subject or state.current_subject,
        source='student',
        status='queued',
    ))
    return existing


def infer_skill(subject: str, topic: str, message: str) -> str:
    text = _normalized(f'{subject} {topic} {message}')
    if 'lcm' in text or 'least common multiple' in text:
        return 'LCM'
    if 'fraction' in text or re.search(r'\d+/\d+', text):
        return 'Fractions'
    if any(word in text for word in ['multiply', 'multiplication']) or '×' in message or '*' in message:
        return 'Multiplication'
    if any(word in text for word in ['divide', 'division']) or '÷' in message:
        return 'Division'
    if any(word in text for word in ['main idea', 'inference', 'reading']):
        return 'Reading'
    if any(word in text for word in ['sentence', 'paragraph', 'writing']):
        return 'Writing'
    return topic.strip().title() if topic.strip() else 'Practice'


def _extract_last_assistant_question(history: list[ChatHistoryItem]) -> str:
    for item in reversed(history):
        if item.role == 'msalisia' and '?' in item.content:
            return item.content.strip()
    return ''


def _same_question(left: str, right: str) -> bool:
    return _normalized(left).rstrip('?') == _normalized(right).rstrip('?')


def _is_substep_of_active_problem(active_problem: str, current_step: str) -> bool:
    active = _normalized(active_problem).rstrip('?')
    step = _normalized(current_step).rstrip('?')
    if not active or not step or active == step:
        return False
    return detect_math_expression(active_problem) or detect_math_expression(current_step)


def is_answering_tutor_question(history: list[ChatHistoryItem]) -> bool:
    if not history:
        return False
    previous = history[-1]
    return previous.role == 'msalisia' and '?' in previous.content


def _is_opening_human_moment_question(content: str) -> bool:
    text = _normalized(content)
    mood_markers = (
        'how are you',
        'how are you doing',
        'how are you feeling',
        'how do you feel',
        'how is your day',
        "how's your day",
        "how's it going",
        "what's going on",
        'what is going on',
        'tell me how you are',
        'tell me how you feel',
    )
    learning_markers = (
        'before we start',
        'before we get going',
        'then we can',
        'after you check in',
        'one small learning step',
        'good to see you',
        'glad you are here',
        'hoping i would see you',
    )
    if not any(marker in text for marker in mood_markers):
        return False
    if any(marker in text for marker in learning_markers):
        return True
    task_markers = ('solve ', 'what is ', 'what are ', 'answer ', 'calculate ', 'explain ')
    return len(text) <= 260 and not any(marker in text for marker in task_markers)


def _is_opening_followup(history: list[ChatHistoryItem], state: TutoringState) -> bool:
    if not is_answering_tutor_question(history):
        return False
    if state.current_question.strip() or state.current_step.strip():
        return False
    return _is_opening_human_moment_question(history[-1].content)


def infer_active_problem(message: str, history: list[ChatHistoryItem], state: TutoringState | None = None) -> str:
    if state and state.active_problem.strip() and detect_context_clarification_intent(message):
        return state.active_problem.strip()

    if _looks_like_new_problem(message):
        return message.strip()

    for item in reversed(history):
        if item.role == 'student' and _looks_like_new_problem(item.content):
            return item.content.strip()

    return (state.active_problem if state else '').strip()


def _base_directives() -> list[str]:
    return [
        'Keep the reply short and appropriate for Grades 3 through 6.',
        'Use the practice focus for the active subject when available; otherwise use enrolled grade.',
        'Use easy words and keep most replies to 3 short sentences or less.',
        'If you show steps, keep each step very short.',
        'Use short paragraphs and clear spacing.',
        'Use only one small example when it helps.',
        'For math, use symbols like +, −, ×, ÷, and = in a clean simple way.',
        'Do not use * for multiplication. Use ×.',
        'Do not use / for division unless it is a fraction like 1/2.',
        'Do not give long lists unless they are truly needed.',
    ]


def _structured_state_fields(state: TutoringState) -> dict:
    return {
        'problem_id': state.problem_id,
        'main_problem': state.main_problem,
        'full_problem': state.full_problem,
        'ordered_steps': state.ordered_steps,
        'current_step_index': state.current_step_index,
        'current_step_id': state.current_step_id,
        'completed_steps': state.completed_steps,
        'current_expression': state.current_expression,
        'remaining_steps': state.remaining_steps,
        'completed_step_results': state.completed_step_results,
        'step_results': state.step_results,
        'attempts_per_step': state.attempts_per_step,
        'helper_branch': state.helper_branch,
        'queued_followup_questions': state.queued_followup_questions,
        'return_step_index': state.return_step_index,
        'return_step_id': state.return_step_id,
        'final_answer': state.final_answer,
        'problem_status': state.problem_status,
    }


def build_chat_directives(message: str, history: list[ChatHistoryItem], state: TutoringState | None = None) -> tuple[list[str], str, str, TutoringState]:
    state = state or TutoringState()
    directives = _base_directives()
    active_problem = infer_active_problem(message, history, state)
    current_step = state.current_step.strip() or _extract_last_assistant_question(history)
    current_question = state.current_question.strip() or current_step
    direct_help = detect_direct_help_intent(message)
    confused = detect_confused_intent(message)
    definition = detect_definition_intent(message)
    new_problem = _looks_like_new_problem(message)
    math_expression = detect_math_expression(message)
    homework_or_skip = detect_homework_or_skip_intent(message)
    switch_task = detect_switch_task_intent(message)
    action_intent = detect_action_intent(message)
    context_clarification = detect_context_clarification_intent(message)
    tutor_concern = detect_tutor_concern_intent(message)
    skill = state.skill or infer_skill('', '', active_problem or message)
    opening_followup = _is_opening_followup(history, state)
    answer_to_current_math_step = _looks_like_answer_to_current_math_step(message, current_question or current_step)
    unfinished_main_problem = _has_unfinished_main_problem(state)
    side_question_requested = (
        unfinished_main_problem
        and not switch_task
        and not context_clarification
        and not tutor_concern
        and not homework_or_skip
        and not answer_to_current_math_step
        and (
            definition
            or (new_problem and not _same_prompt(message, active_problem or state.main_problem or state.active_problem))
        )
    )
    direct_question_override = (
        (new_problem and not answer_to_current_math_step)
        or definition
        or homework_or_skip
        or context_clarification
        or tutor_concern
        or (direct_help and math_expression)
    )
    answering_tutor_question = is_answering_tutor_question(history) and not opening_followup and not direct_question_override

    attempt_count = state.attempt_count + 1 if answering_tutor_question else 0
    attempts_per_step = dict(state.attempts_per_step)
    if answering_tutor_question and state.current_step_id:
        attempts_per_step[state.current_step_id] = attempt_count
    mode = state.mode if state.mode else 'solve'
    status = 'solving'

    if active_problem:
        directives.append(f'Keep helping with this problem or task: {active_problem}')
    if state.memory_note.strip():
        directives.append(f'Remember this from the session: {state.memory_note.strip()}')

    if switch_task:
        directives.append('The student explicitly wants to switch tasks. It is okay to leave the previous problem and move to the new requested task.')

    if opening_followup:
        directives.append('The student is answering the opening human moment. Respond to how they feel before any learning content.')
        if homework_or_skip or new_problem or direct_help:
            directives.append('The student is asking to skip the conversational check-in, go to homework, or get direct help. Respect that immediately and do not force a check-in question.')
            directives.append('Move straight into the requested task with one warm, useful next step.')
        else:
            directives.append('After the mood response, transition into a conversational Quick Check-In inside the chat.')
            directives.append('Ask exactly one tiny subject question that helps you learn what the student knows today.')
            directives.append('Make it feel like a friendly conversation, not a test. Do not use the words assessment, evaluation, skill check, or test.')
            directives.append('Use recent check-in context, parent profile notes, or the current practice focus when available; otherwise use one small enrolled-grade subject question.')
            directives.append('If the student seems tired, stressed, upset, or frustrated, make the question extra small and low-pressure.')
        next_state = TutoringState(
            **_structured_state_fields(state),
            active_problem='',
            current_subject=state.current_subject,
            current_step='',
            current_question='',
            expected_answer='',
            student_answer=message,
            correctness_status='',
            skill=skill,
            step_number=state.step_number,
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode='opening_checkin',
            status='ready_for_mini_checkin',
            memory_note=state.memory_note,
        )
        return directives, '', '', next_state

    if definition:
        directives.append('Give a short direct definition first. Then connect it back to the student’s active problem if there is one.')
        directives.append('Do not ask a new question before giving the useful definition.')

    if context_clarification:
        directives.append('The student is clarifying what the session was about, not submitting an answer. Do not mark this as correct or wrong.')
        if math_expression and state.active_problem.strip():
            directives.append('Acknowledge the clarified context, but do not replace the unfinished active problem unless the student clearly asks to switch.')
            directives.append(f'Keep the lesson anchored on the unfinished active problem first: {state.active_problem.strip()}')
        else:
            directives.append('Acknowledge the clarified context and continue from it if enough information is available.')
        if math_expression and not state.active_problem.strip():
            directives.append('The clarified context includes a math expression. Treat that expression as the active problem to resume.')

    if tutor_concern:
        directives.append('The student is expressing concern about confusion, memory, subject switching, or tutor behavior. Do not treat this as an answer submission.')
        directives.append('Acknowledge the concern briefly, be honest about the current visible context, and calmly re-ground the lesson before asking for any answer.')

    if action_intent == 'hint':
        directives.append('The student asked for a hint. Give one small hint only, then invite them to try.')
    elif action_intent == 'explain_again':
        directives.append('Explain the same idea again using simpler words and a tiny example.')
    elif action_intent == 'example':
        directives.append('Give one short example that matches the current subject and topic.')
    elif action_intent == 'check_answer':
        directives.append('Check the student answer kindly. If it is wrong, follow the attempt rule.')

    if side_question_requested and _has_used_helper_branch(state):
        queued_followup_questions = _append_queued_followup_question(state, message, state.current_subject)
        directives.append('The student asked another side question while the original problem is still unfinished.')
        directives.append('Do not open another side branch right now.')
        directives.append('Briefly re-anchor the student to the original problem, solve the next main step first, and remember the new side question for later.')
        directives.append(f'Queued follow-up question to answer after the main problem: {message.strip()}')
        structured_fields = _structured_state_fields(state)
        structured_fields['queued_followup_questions'] = queued_followup_questions
        next_state = TutoringState(
            **structured_fields,
            active_problem=state.main_problem or state.active_problem or active_problem,
            current_subject=state.current_subject,
            current_step=state.current_step,
            current_question=state.current_question or state.current_step,
            expected_answer=state.expected_answer,
            student_answer=message,
            correctness_status='',
            skill=skill,
            step_number=state.step_number or max(1, state.current_step_index + 1),
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode='practice' if (state.current_question or state.current_step) else 'solve',
            status='waiting_for_student' if (state.current_question or state.current_step) else 'solving',
            memory_note=state.memory_note,
        )
        return directives, state.main_problem or state.active_problem or active_problem, current_step, next_state

    if side_question_requested:
        helper_branch = TutorHelperBranch(
            branch_id=_question_id(message),
            branch_type='side_question',
            question=message.strip(),
            linked_step_id=state.current_step_id,
            return_step_id=state.current_step_id or state.return_step_id,
            status='active',
        )
        directives.append('The student asked a side question while the main problem is still unfinished.')
        directives.append('Answer this side question briefly and clearly first.')
        directives.append('In the same reply, bring the student back to the main problem right away.')
        directives.append('After the short side answer, restate the main problem step and ask only one small return question.')
        directives.append(f'Side question to answer briefly: {message.strip()}')
        if state.main_problem.strip():
            directives.append(f'Return immediately to the main problem: {state.main_problem.strip()}')
        structured_fields = _structured_state_fields(state)
        structured_fields['helper_branch'] = helper_branch
        structured_fields['return_step_index'] = state.current_step_index
        structured_fields['return_step_id'] = state.current_step_id or state.return_step_id
        next_state = TutoringState(
            **structured_fields,
            active_problem=state.main_problem or state.active_problem or active_problem,
            current_subject=state.current_subject,
            current_step=state.current_step,
            current_question=state.current_question or state.current_step,
            expected_answer=state.expected_answer,
            student_answer=message,
            correctness_status='',
            skill=skill,
            step_number=state.step_number or max(1, state.current_step_index + 1),
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode='helper_branch',
            status='respond_then_return',
            memory_note=state.memory_note,
        )
        return directives, message.strip(), current_step, next_state

    if (
        not unfinished_main_problem
        and state.queued_followup_questions
        and not switch_task
        and not new_problem
        and not definition
        and not direct_help
        and not homework_or_skip
        and not answering_tutor_question
    ):
        queued_question = state.queued_followup_questions[0]
        remaining_queue = list(state.queued_followup_questions[1:])
        helper_branch = TutorHelperBranch(
            branch_id=queued_question.question_id or _question_id(queued_question.question),
            branch_type='queued_followup',
            question=queued_question.question,
            linked_step_id='',
            return_step_id='',
            status='active',
        )
        directives.append('The main problem is finished, and there is a saved follow-up question from the student.')
        directives.append('Answer that queued follow-up question clearly before starting any new practice.')
        directives.append(f'Queued follow-up question to answer now: {queued_question.question}')
        structured_fields = _structured_state_fields(state)
        structured_fields['helper_branch'] = helper_branch
        structured_fields['queued_followup_questions'] = remaining_queue
        next_state = TutoringState(
            **structured_fields,
            active_problem='',
            current_subject=state.current_subject,
            current_step='',
            current_question='',
            expected_answer='',
            student_answer=message,
            correctness_status='',
            skill=skill,
            step_number=state.step_number,
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode='queued_followup',
            status='answering_saved_followup',
            memory_note=state.memory_note,
        )
        return directives, queued_question.question, '', next_state

    if not answering_tutor_question:
        mode = 'solve'
        status = 'solving'
        if (new_problem and not answer_to_current_math_step) or direct_help:
            if direct_question_override and current_step:
                directives.append('The student asked a new direct question, so answer that question before returning to any earlier quick question.')
            directives.append('The student asked a real question. Solve or explain that question first in short easy steps.')
            directives.append('Do not turn the student’s main question into a quiz before helping.')
            if math_expression:
                if direct_help:
                    directives.append('For step-by-step math help, give only the first useful worked step before asking the student to try the next small step.')
                    directives.append('Do not finish the whole problem in the first reply unless the student directly asks for the final answer.')
                else:
                    directives.append('For a fresh math problem, give the first correct worked step before you ask the student to try anything.')
                directives.append('After that first worked step, ask one tiny next-step question so the student can practice with guidance.')
        elif confused:
            directives.append('The student is confused. Help with one simple next step right away.')
        elif homework_or_skip:
            directives.append('The student wants to skip the conversational check-in or go to homework. Do not force a check-in; move into one useful learning or homework step.')
        directives.append('After the main problem is helped enough, you may ask one tiny same-topic practice question.')
        next_state = TutoringState(
            **_structured_state_fields(state),
            active_problem=active_problem,
            current_step='',
            current_question='',
            expected_answer=state.expected_answer,
            skill=skill,
            step_number=state.step_number,
            attempt_count=0,
            answer_revealed=False,
            mode=mode,
            status=status,
            memory_note=state.memory_note,
        )
        return directives, active_problem, '', next_state

    mode = 'practice'
    status = 'waiting_for_student'
    substep_of_active_problem = _is_substep_of_active_problem(active_problem, current_step or current_question)
    if current_step:
        directives.append(f'The student is answering this current question: {current_step}')
    if substep_of_active_problem:
        directives.append(f'This current question is only one step inside the active problem: {active_problem}')
        directives.append('After this step is checked or explained, return to the active problem and finish it before starting a new practice problem.')
        directives.append('Do not ask a new similar practice question until the active problem has a clear final answer, unless the student explicitly asks to switch.')
    if state.expected_answer.strip():
        directives.append(f'Expected answer or target idea if useful: {state.expected_answer.strip()}')
    directives.append('Stay on this one current question only. Do not jump to a new topic or a new part too early.')

    if attempt_count == 1:
        directives.append('This is the first attempt for the current question.')
        directives.append('If the answer is correct, praise briefly and continue.')
        directives.append('If it is wrong or the student says "I don’t know", say "Good try!" or similar, give one short hint, and ask them to try the same question again.')
        directives.append('Do not reveal the final answer on this first wrong attempt.')
    elif attempt_count == 2:
        directives.append('This is the second attempt for the current question.')
        directives.append('If the answer is correct, praise briefly and continue.')
        directives.append('If it is still wrong, do not give the correct answer yet.')
        directives.append('Give a stronger hint or one worked sub-step, but do not reveal the final answer yet. Ask the student to try once more.')
    else:
        directives.append('This is the third attempt or later for the current question.')
        if substep_of_active_problem:
            directives.append('If the answer is still wrong, give the correct answer for this step, explain it in 1 or 2 short lines, then continue the original active problem.')
            directives.append('Do not give a new similar practice question yet. First complete the original active problem.')
        else:
            directives.append('If the answer is still wrong, give the correct answer, explain it in 1 or 2 short lines, then give one new similar same-topic question.')

    if confused and attempt_count < 3:
        directives.append('The student seems unsure. Keep your hint very simple and kind.')

    structured_fields = _structured_state_fields(state)
    structured_fields['attempts_per_step'] = attempts_per_step
    next_state = TutoringState(
        **structured_fields,
        active_problem=active_problem,
        current_step=current_step,
        current_question=current_question,
        expected_answer=state.expected_answer,
        skill=skill,
        step_number=state.step_number,
        attempt_count=attempt_count,
        answer_revealed=attempt_count >= 3,
        mode=mode,
        status=status,
        memory_note=state.memory_note,
    )
    return directives, active_problem, current_step, next_state


def extract_followup_step(reply: str) -> str:
    questions = [part.strip() for part in re.findall(r'[^.!?]*\?', reply) if part.strip()]
    if questions:
        return questions[-1]
    return ''


def _build_memory_note(active_problem: str, reply: str, previous_note: str) -> str:
    reply_text = ' '.join(reply.split())

    lcm_match = re.search(r'LCM of (\d+) and (\d+) is (\d+)', reply_text, re.IGNORECASE)
    if lcm_match:
        return f'We learned that the LCM of {lcm_match.group(1)} and {lcm_match.group(2)} is {lcm_match.group(3)}.'

    fraction_match = re.search(r'(\d+/\d+)\s*\+\s*(\d+/\d+)\s*=\s*(\d+/\d+)', reply_text)
    if fraction_match:
        return f'We solved {fraction_match.group(1)} + {fraction_match.group(2)} = {fraction_match.group(3)}.'

    converted_match = re.search(r'new fraction is (\d+/\d+)', reply_text, re.IGNORECASE)
    if converted_match and active_problem:
        return f'For {active_problem}, we converted one fraction to {converted_match.group(1)}.'

    if active_problem and previous_note.strip():
        return previous_note

    if active_problem:
        return f'We are working on {active_problem}.'

    return previous_note


def update_tutoring_state_after_reply(
    state: TutoringState,
    user_message: str,
    reply: str,
) -> TutoringState:
    opening_checkin_turn = state.mode == 'opening_checkin' or state.status == 'ready_for_mini_checkin'
    active_problem = state.active_problem or ('' if opening_checkin_turn else user_message.strip())
    next_step = extract_followup_step(reply)
    current_question = state.current_question or state.current_step
    same_question = bool(next_step and current_question and _same_question(next_step, current_question))
    next_step_number = state.step_number + 1 if next_step and not same_question else state.step_number

    if state.helper_branch.status == 'active' and state.helper_branch.question:
        helper_branch = state.helper_branch.model_copy(update={'status': 'completed'})
        restored_step = state.current_step
        restored_question = state.current_question or state.current_step
        restored_expected_answer = state.expected_answer
        restored_mode = 'practice' if restored_question else 'solve'
        restored_status = 'waiting_for_student' if restored_question else 'solving'
        structured_fields = _structured_state_fields(state)
        structured_fields['helper_branch'] = helper_branch

        if state.ordered_steps and state.problem_status in {'in_progress', 'awaiting_step'}:
            return TutoringState(
                **structured_fields,
                active_problem=state.main_problem or state.active_problem,
                current_subject=state.current_subject,
                current_step=restored_step,
                current_question=restored_question,
                expected_answer=restored_expected_answer,
                student_answer=state.student_answer,
                correctness_status='',
                skill=state.skill,
                step_number=state.step_number or max(1, state.current_step_index + 1),
                attempt_count=0,
                hint_given=False,
                answer_revealed=False,
                next_similar_question='',
                mode='practice',
                status='waiting_for_student',
                memory_note=_build_memory_note(state.main_problem or state.active_problem, reply, state.memory_note),
            )

        return TutoringState(
            **structured_fields,
            active_problem=state.active_problem or state.main_problem,
            current_subject=state.current_subject,
            current_step=restored_step,
            current_question=restored_question,
            expected_answer=restored_expected_answer,
            student_answer=state.student_answer,
            correctness_status='',
            skill=state.skill,
            step_number=state.step_number,
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode=restored_mode,
            status=restored_status,
            memory_note=_build_memory_note(state.active_problem or state.main_problem, reply, state.memory_note),
        )

    if state.ordered_steps and state.current_step_id and state.problem_status in {'in_progress', 'awaiting_step'}:
        if next_step:
            return TutoringState(
                **_structured_state_fields(state),
                active_problem=active_problem,
                current_subject=state.current_subject,
                current_step=state.current_step,
                current_question=state.current_question or state.current_step,
                expected_answer=state.expected_answer,
                student_answer=state.student_answer,
                correctness_status=state.correctness_status,
                skill=state.skill,
                step_number=state.step_number or max(1, state.current_step_index + 1),
                attempt_count=state.attempt_count,
                hint_given=state.hint_given,
                answer_revealed=state.answer_revealed,
                next_similar_question='',
                mode='practice',
                status='waiting_for_student',
                memory_note=_build_memory_note(active_problem, reply, state.memory_note),
            )
        return TutoringState(
            **_structured_state_fields(state),
            active_problem=active_problem,
            current_subject=state.current_subject,
            current_step=state.current_step,
            current_question=state.current_question or state.current_step,
            expected_answer=state.expected_answer,
            student_answer=state.student_answer,
            correctness_status=state.correctness_status,
            skill=state.skill,
            step_number=state.step_number or max(1, state.current_step_index + 1),
            attempt_count=state.attempt_count,
            hint_given=state.hint_given,
            answer_revealed=state.answer_revealed,
            next_similar_question='',
            mode='practice',
            status='waiting_for_student',
            memory_note=_build_memory_note(active_problem, reply, state.memory_note),
        )

    if next_step:
        return TutoringState(
            **_structured_state_fields(state),
            active_problem=active_problem,
            current_subject=state.current_subject,
            current_step=next_step,
            current_question=next_step,
            expected_answer=state.expected_answer if same_question else '',
            student_answer=state.student_answer,
            correctness_status=state.correctness_status,
            skill=state.skill,
            step_number=next_step_number,
            attempt_count=state.attempt_count if same_question else 0,
            hint_given=state.hint_given if same_question else False,
            answer_revealed=state.answer_revealed if same_question else False,
            next_similar_question='' if same_question else next_step,
            mode='practice',
            status='waiting_for_student',
            memory_note=_build_memory_note(active_problem, reply, state.memory_note),
        )

    return TutoringState(
        **_structured_state_fields(state),
        active_problem=active_problem,
        current_subject=state.current_subject,
        current_step='',
        current_question='',
        expected_answer='',
        student_answer=state.student_answer,
        correctness_status=state.correctness_status,
        skill=state.skill,
        step_number=state.step_number,
        attempt_count=0,
        hint_given=False,
        answer_revealed=state.answer_revealed,
        next_similar_question='',
        mode='solve',
        status='finished',
        memory_note=_build_memory_note(active_problem, reply, state.memory_note),
    )
