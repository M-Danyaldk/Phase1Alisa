import hashlib
import re

from .assessment_validation import extract_math_expression, format_fraction, normalize_math_text, safe_eval_expression
from .models import ChatHistoryItem, TutorHelperBranch, TutorQueuedQuestion, TutoringState
from .utils.task_lifecycle import (
    can_resume_paused_task,
    complete_and_resume_latest,
    transition_to_task,
)
from .utils.attempt_policy import register_answer_attempt

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
    'explain_again': ['explain again', 'explain that again', 'explain it again', 'say it another way', 'show me again', 'one more time', "i still don't get it", 'i still do not get it'],
    'example': ['example', 'give me an example', 'show example'],
    'check_answer': ['check my answer', 'is this right', 'is my answer right', 'check this'],
    'clarify_prompt': [
        'which one',
        'which question',
        'which sentence',
        'which step',
        'this step?',
        'that step?',
        'what do you mean',
        'what does that mean',
        'what are you asking',
        'what is this asking',
        'what do i do',
        'what do you want me to do',
    ],
}

SUBJECT_SWITCH_PATTERN = re.compile(
    r'\b(?:switch|change|move|go)(?:\s+(?:subjects?|over))?\s+'
    r'(?:to|back\s+to)\s+'
    r'(maths?|mathematics|arithmetic|ela|english(?:\s+language\s+arts)?|language\s+arts|reading|writing)\b'
)
MATH_TOPIC_WORDS = {
    'math', 'fraction', 'fractions', 'numerator', 'denominator', 'lcm', 'multiply', 'multiplication',
    'divide', 'division', 'add', 'addition', 'subtract', 'subtraction', 'equation', 'expression',
    'problem', 'step', 'decimal', 'number', 'numbers', 'whole number', 'mixed number', 'simplify',
    'solve', 'sum', 'difference', 'product', 'quotient',
}
ELA_TOPIC_WORDS = {
    'reading', 'story', 'passage', 'main idea', 'inference', 'character', 'characters', 'theme',
    'meaning', 'context clue', 'vocabulary', 'evidence', 'author', 'setting', 'plot',
}
WRITING_TOPIC_WORDS = {
    'writing', 'write', 'revise', 'revision', 'rewrite', 'edit', 'essay', 'topic sentence',
    'complete sentence', 'clear sentence', 'stronger sentence', 'detail', 'details',
}
GENERAL_KNOWLEDGE_WORDS = {
    'photosynthesis', 'plant', 'plants', 'science', 'volcano', 'planet', 'president', 'country',
    'history', 'animal', 'animals', 'solar system', 'gravity', 'weather',
}
SCIENCE_TOPIC_WORDS = {
    'photosynthesis', 'plant', 'plants', 'leaf', 'leaves', 'stem', 'roots', 'root', 'flower', 'flowers',
    'sunlight', 'soil', 'water', 'air', 'oxygen', 'carbon dioxide', 'energy', 'chlorophyll',
    'science', 'gravity', 'weather', 'volcano', 'planet', 'planets', 'solar system',
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


def detect_explicit_subject_switch(message: str) -> bool:
    return resolve_explicit_subject_switch(message) is not None


def resolve_explicit_subject_switch(message: str) -> str | None:
    match = SUBJECT_SWITCH_PATTERN.search(_normalized(message))
    if not match:
        return None
    alias = match.group(1)
    if alias in {'math', 'maths', 'mathematics', 'arithmetic'}:
        return 'Math'
    if alias == 'writing':
        return 'Writing'
    return 'ELA'


def build_subject_switch_reply(subject: str) -> str:
    label = {'Math': 'math', 'ELA': 'reading', 'Writing': 'writing'}.get(subject, 'this subject')
    return f'Okay, we are working on {label} now. What would you like help with first?'


def detect_math_expression(message: str) -> bool:
    if not any(char.isdigit() for char in message):
        return False
    if re.search(r'\d\s*[xX]\s*\d', message):
        return True
    return any(symbol in message for symbol in ['+', '-', '*', '/', '=', '×', '÷'])


def _extract_number_tokens(text: str) -> set[str]:
    return set(re.findall(r'-?\d+(?:/\d+)?(?:\.\d+)?', str(text or '')))


def _looks_like_raw_math_expression_only(message: str) -> bool:
    text = str(message or '').strip()
    if not text or not detect_math_expression(text):
        return False
    cleaned = re.sub(r'[\d\s+\-*/=().xX]', '', text)
    return cleaned == ''


def detect_action_intent(message: str) -> str:
    text = _normalized(message)
    if text in {
        'which one',
        'which question',
        'which sentence',
        'which step',
        'what do you mean',
        'what does that mean',
        'what are you asking',
        'what is this asking',
        'what do i do',
        'what do you want me to do',
    }:
        return 'clarify_prompt'
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
    return text.startswith(starters)


def _looks_like_general_knowledge_question(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False
    question_like = bool(re.match(r'^(what is|what are|who is|who are|how do|how does|why do|why does|tell me about|explain)\b', text))
    if not question_like:
        return False
    return any(word in text for word in GENERAL_KNOWLEDGE_WORDS | SCIENCE_TOPIC_WORDS)


def _looks_like_reading_task(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False

    strong_phrases = (
        'main idea',
        'context clue',
        'what does',
        'what is the meaning',
        'meaning of',
        'character',
        'theme',
        'passage',
        'story',
        'vocabulary',
        'inference',
        'author',
        'setting',
        'plot',
    )
    weak_phrases = (
        'reading',
    )
    starters = (
        'read this',
        'help me understand this passage',
        'help me with this passage',
        'help me with this text',
        'can you help me with this passage',
        'can you help me with this text',
        'help me read this',
        'what does',
        'what is the main idea',
        'who is the main character',
        'what is the theme',
    )
    if text.startswith(starters):
        return True
    if any(phrase in text for phrase in strong_phrases):
        return True
    if any(phrase in text for phrase in weak_phrases):
        return not _has_strong_writing_shape(text)
    return False


def _looks_like_writing_task(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False

    strong_phrases = (
        'write one clear sentence',
        'write 3 sentences',
        'write three sentences',
        'fix this sentence',
        'make this sentence stronger',
        'how can you make this sentence stronger',
        'complete sentence',
        'topic sentence',
        'revise',
        'revision',
        'rewrite',
        'edit this',
        'writing',
        'essay',
    )
    starters = (
        'help me write',
        'help me with this paragraph',
        'help me with this sentence',
        'can you help me with this paragraph',
        'can you help me with this sentence',
        'check my sentence',
        'write ',
        'rewrite ',
        'revise ',
        'edit ',
        'fix this sentence',
        'how can you make this sentence stronger',
    )
    return text.startswith(starters) or any(phrase in text for phrase in strong_phrases)


def _has_strong_writing_shape(text: str) -> bool:
    starters = (
        'help me write',
        'help me with this paragraph',
        'help me with this sentence',
        'can you help me with this paragraph',
        'can you help me with this sentence',
        'check my sentence',
        'write ',
        'rewrite ',
        'revise ',
        'edit ',
        'fix this sentence',
        'how can you make this sentence stronger',
    )
    strong_phrases = (
        'write one clear sentence',
        'write 3 sentences',
        'write three sentences',
        'fix this sentence',
        'make this sentence stronger',
        'how can you make this sentence stronger',
        'complete sentence',
        'topic sentence',
        'revise',
        'revision',
        'rewrite',
        'edit this',
        'writing',
        'essay',
    )
    return text.startswith(starters) or any(phrase in text for phrase in strong_phrases)


def _looks_like_answer_to_current_math_step(message: str, current_question: str) -> bool:
    text = _normalized(message)
    if not current_question.strip() or not text:
        return False
    if text in {'yes', 'no', 'ok', 'okay'}:
        return False
    if not any(char.isdigit() for char in message):
        return False
    if re.fullmatch(r'-?\d+(?:/\d+)?(?:\.\d+)?', text):
        return True
    if re.fullmatch(
        r'(?:my answer|answer|answer is|it is|its|it\'s|i got|i think it is|i think)\s*-?\d+(?:/\d+)?(?:\.\d+)?',
        text,
    ):
        return True
    if len(text) > 32:
        return False
    return False


def _is_related_to_active_problem(message: str, state: TutoringState, active_problem: str, current_step: str) -> bool:
    normalized = _normalized(message)
    if not normalized:
        return False

    math_refs = [
        active_problem,
        state.main_problem,
        current_step,
        state.current_question,
        state.current_expression,
        *[step.expression for step in state.ordered_steps],
        *state.completed_steps,
        *state.completed_step_results,
        *list(state.step_results.values()),
    ]
    ref_numbers = set().union(*(_extract_number_tokens(item) for item in math_refs if item))
    message_numbers = _extract_number_tokens(message)
    shared_numbers = ref_numbers.intersection(message_numbers)

    if any(phrase in normalized for phrase in ['how', 'why', 'came', 'come', 'became', 'become', 'from', 'mean', 'explain', 'get', 'got']):
        return bool(shared_numbers)

    current_step_text = _normalized(current_step)
    if current_step_text and any(phrase in normalized for phrase in ['this step', 'that step', 'current step', 'your step']):
        return True

    if any(phrase in normalized for phrase in ['how did', 'where did', 'why is', 'why did', 'how do you get']):
        return bool(shared_numbers)

    if state.current_step_id and current_step.strip():
        current_numbers = _extract_number_tokens(current_step)
        if message_numbers and current_numbers and message_numbers.issubset(current_numbers):
            return True

    return False


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


def _has_only_quick_question_context(state: TutoringState, current_question: str) -> bool:
    if state.problem_id or state.main_problem.strip() or state.ordered_steps:
        return False
    question = (current_question or state.current_question or state.current_step or '').strip()
    active = (state.active_problem or '').strip()
    if not question:
        return False
    if not active:
        return True
    return _same_question(active, question)


def _clarification_resolution(message: str) -> str:
    text = _normalized(message)
    if not text:
        return ''
    current_problem_markers = (
        'part of this problem',
        'part of the problem',
        'part of current problem',
        'same problem',
        'current problem',
        'this problem',
    )
    new_problem_markers = (
        'new problem',
        'solve this first',
        'do this first',
        'new one first',
        'this first',
        'solve the new problem',
    )
    if any(marker in text for marker in new_problem_markers):
        return 'new_problem'
    if any(marker in text for marker in current_problem_markers):
        return 'current_problem'
    return ''


def _clear_pending_problem_fields(structured_fields: dict) -> dict:
    structured_fields['pending_input_kind'] = ''
    structured_fields['pending_new_problem'] = ''
    return structured_fields


def _current_expected_answer(state: TutoringState) -> str:
    expected = state.expected_answer.strip()
    if expected:
        return expected

    current_step_id = state.current_step_id or state.return_step_id
    for step in state.ordered_steps:
        if current_step_id and step.step_id == current_step_id and step.expected_answer.strip():
            return step.expected_answer

    current_step = state.current_step.strip()
    for step in state.ordered_steps:
        if current_step and _same_prompt(step.expression, current_step) and step.expected_answer.strip():
            return step.expected_answer

    return ''


def _paused_expected_answer(state: TutoringState) -> str:
    expected = state.paused_expected_answer.strip()
    if expected:
        return expected
    return _current_expected_answer(state)


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


def _should_use_history_question_fallback(state: TutoringState) -> bool:
    if state.problem_id or state.ordered_steps:
        return True
    if (state.current_subject or '').strip() == 'Math':
        return True
    active = state.active_problem or state.main_problem or state.full_problem
    return detect_math_expression(active)


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
        'active_task_id': state.active_task_id,
        'task_records': state.task_records,
        'problem_id': state.problem_id,
        'problem_kind': state.problem_kind,
        'word_problem_schema': state.word_problem_schema,
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
        'emotion_label': state.emotion_label,
        'emotion_intensity': state.emotion_intensity,
        'emotional_support_count': state.emotional_support_count,
        'emotional_support_mode': state.emotional_support_mode,
        'emotional_return_mode': state.emotional_return_mode,
        'emotional_return_status': state.emotional_return_status,
        'last_response_kind': state.last_response_kind,
        'last_response_source': state.last_response_source,
        'last_response_validated': state.last_response_validated,
        'last_response_repaired': state.last_response_repaired,
        'last_response_violations': state.last_response_violations,
        'tutor_practice_question_id': state.tutor_practice_question_id,
        'tutor_practice_grade': state.tutor_practice_grade,
        'tutor_practice_topic': state.tutor_practice_topic,
        'tutor_practice_hint_1': state.tutor_practice_hint_1,
        'tutor_practice_hint_2': state.tutor_practice_hint_2,
        'tutor_practice_explanation': state.tutor_practice_explanation,
        'recent_tutor_practice_question_ids': state.recent_tutor_practice_question_ids,
        'helper_branch': state.helper_branch,
        'queued_followup_questions': state.queued_followup_questions,
        'pending_input_kind': state.pending_input_kind,
        'pending_new_problem': state.pending_new_problem,
        'paused_main_problem': state.paused_main_problem,
        'paused_current_step': state.paused_current_step,
        'paused_current_question': state.paused_current_question,
        'paused_expected_answer': state.paused_expected_answer,
        'paused_completed_steps': state.paused_completed_steps,
        'return_step_index': state.return_step_index,
        'return_step_id': state.return_step_id,
        'final_answer': state.final_answer,
        'problem_status': state.problem_status,
    }


def build_chat_directives(
    message: str,
    history: list[ChatHistoryItem],
    state: TutoringState | None = None,
    assisted_intent_label: str = '',
) -> tuple[list[str], str, str, TutoringState]:
    state = state or TutoringState()
    directives = _base_directives()
    active_problem = infer_active_problem(message, history, state)
    current_step = state.current_step.strip()
    if not current_step and _should_use_history_question_fallback(state):
        current_step = _extract_last_assistant_question(history)
    current_question = state.current_question.strip() or current_step
    direct_help = detect_direct_help_intent(message)
    confused = detect_confused_intent(message)
    definition = detect_definition_intent(message)
    new_problem = _looks_like_new_problem(message)
    math_expression = detect_math_expression(message)
    raw_math_expression_only = _looks_like_raw_math_expression_only(message)
    homework_or_skip = detect_homework_or_skip_intent(message)
    switch_task = detect_switch_task_intent(message)
    action_intent = detect_action_intent(message)
    context_clarification = detect_context_clarification_intent(message)
    tutor_concern = detect_tutor_concern_intent(message)
    skill = state.skill or infer_skill('', '', active_problem or message)
    opening_followup = _is_opening_followup(history, state)
    answer_to_current_math_step = _looks_like_answer_to_current_math_step(message, current_question or current_step)
    unfinished_main_problem = _has_unfinished_main_problem(state)
    related_to_active_problem = _is_related_to_active_problem(message, state, active_problem, current_step or current_question)
    quick_question_only_context = _has_only_quick_question_context(state, current_question or current_step)
    if assisted_intent_label == 'answer_current_step':
        answer_to_current_math_step = True
    elif assisted_intent_label == 'related_question':
        related_to_active_problem = True
        new_problem = True
    elif assisted_intent_label == 'topic_switch':
        switch_task = True
        new_problem = True
    elif assisted_intent_label in {
        'greeting',
        'acknowledge',
        'continue_current',
        'help_request',
        'emotion',
        'pause',
        'meta_feedback',
    }:
        new_problem = False
    elif assisted_intent_label == 'switch_request':
        switch_task = True
        new_problem = True
    elif assisted_intent_label == 'clarification_about_context':
        context_clarification = True
    elif assisted_intent_label == 'new_problem':
        new_problem = True
    needs_new_problem_clarification = (
        unfinished_main_problem
        and raw_math_expression_only
        and not quick_question_only_context
        and not switch_task
        and not answer_to_current_math_step
        and not related_to_active_problem
    )
    if assisted_intent_label == 'new_problem' and unfinished_main_problem and not switch_task and not answer_to_current_math_step:
        needs_new_problem_clarification = True
    if unfinished_main_problem and not switch_task and (related_to_active_problem or needs_new_problem_clarification):
        active_problem = state.main_problem or state.active_problem or active_problem

    if (
        state.mode == 'resume_paused_problem'
        and state.paused_main_problem.strip()
        and can_resume_paused_task(state)
        and not switch_task
        and not new_problem
        and not homework_or_skip
        and not tutor_concern
        and not context_clarification
    ):
        restored_problem = state.paused_main_problem.strip()
        restored_step = state.paused_current_step.strip()
        restored_question = state.paused_current_question.strip() or restored_step
        restored_expected_answer = _paused_expected_answer(state)
        structured_fields = _structured_state_fields(state)
        next_state = TutoringState(
            **structured_fields,
            active_problem=restored_problem,
            current_subject=state.current_subject,
            current_step=restored_step,
            current_question=restored_question,
            expected_answer=restored_expected_answer,
            student_answer=message,
            correctness_status='',
            skill=state.skill or skill,
            step_number=state.step_number,
            attempt_count=0,
            hint_given=False,
            answer_revealed=False,
            next_similar_question='',
            mode='resume_paused_problem_notice',
            status='waiting_for_student',
            memory_note=state.memory_note,
        )
        return directives, restored_problem, restored_step, next_state
    side_question_requested = (
        unfinished_main_problem
        and not needs_new_problem_clarification
        and not switch_task
        and not context_clarification
        and not tutor_concern
        and not homework_or_skip
        and not answer_to_current_math_step
        and (
            definition
            or (
                new_problem
                and related_to_active_problem
                and not _same_prompt(message, active_problem or state.main_problem or state.active_problem)
            )
        )
    )
    direct_question_override = (
        (new_problem and not answer_to_current_math_step)
        or definition
        or homework_or_skip
        or context_clarification
        or tutor_concern
        or action_intent in {'hint', 'explain_again', 'example', 'clarify_prompt'}
        or (direct_help and math_expression)
        or assisted_intent_label in {
            'topic_switch',
            'help_request',
            'emotion',
            'pause',
            'meta_feedback',
        }
    )
    answering_tutor_question = (
        assisted_intent_label == 'answer_current_step'
        or (is_answering_tutor_question(history) and not opening_followup and not direct_question_override)
    )

    attempt_state = register_answer_attempt(state, is_answer=answering_tutor_question)
    attempt_count = attempt_state.attempt_count if answering_tutor_question else 0
    attempts_per_step = dict(attempt_state.attempts_per_step)
    mode = state.mode if state.mode else 'solve'
    status = 'solving'

    if active_problem:
        directives.append(f'Keep helping with this problem or task: {active_problem}')
    if state.memory_note.strip():
        directives.append(f'Remember this from the session: {state.memory_note.strip()}')

    if switch_task:
        directives.append('The student explicitly wants to switch tasks. It is okay to leave the previous problem and move to the new requested task.')
        if unfinished_main_problem and (state.main_problem.strip() or state.active_problem.strip()):
            directives.append('Tell the student you will solve the new problem first and then return to the earlier main problem.')

    if needs_new_problem_clarification:
        directives.append('The student just sent a new raw math expression while another problem is still unfinished.')
        directives.append('Do not treat this as the answer to the current step.')
        directives.append('Do not switch to the new expression yet.')
        directives.append('Tell the student clearly that this looks like a new problem and that you are still focused on the current problem first.')
        directives.append('Ask one short clarification question: is this part of the current problem, or do they want to solve it as a new problem?')
        structured_fields = _structured_state_fields(state)
        structured_fields['pending_input_kind'] = 'new_math_expression'
        structured_fields['pending_new_problem'] = message.strip()
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
            mode='clarify_new_problem',
            status='waiting_for_clarification',
            memory_note=state.memory_note,
        )
        return directives, state.main_problem or state.active_problem or active_problem, current_step, next_state

    if state.mode == 'clarify_new_problem':
        clarification_resolution = _clarification_resolution(message)
        if clarification_resolution == 'current_problem':
            directives.append('The student confirmed that the new expression was part of the current problem.')
            directives.append('Drop the clarification state and continue with the current main problem only.')
            structured_fields = _clear_pending_problem_fields(_structured_state_fields(state))
            restored_problem = state.main_problem or state.active_problem or active_problem
            restored_step = state.current_step.strip()
            restored_question = state.current_question.strip() or restored_step
            next_state = TutoringState(
                **structured_fields,
                active_problem=restored_problem,
                current_subject=state.current_subject,
                current_step=restored_step,
                current_question=restored_question,
                expected_answer=state.expected_answer,
                student_answer=message,
                correctness_status='',
                skill=skill,
                step_number=state.step_number or max(1, state.current_step_index + 1),
                attempt_count=0,
                hint_given=False,
                answer_revealed=False,
                next_similar_question='',
                mode='practice' if restored_question else 'solve',
                status='waiting_for_student' if restored_question else 'solving',
                memory_note=state.memory_note,
            )
            return directives, restored_problem, restored_step, next_state

        if clarification_resolution == 'new_problem':
            directives.append('The student confirmed they want to solve the new problem first.')
            directives.append('Pause the current main problem and switch cleanly to the new one.')
            new_problem_text = state.pending_new_problem.strip() or message.strip()
            structured_fields = _clear_pending_problem_fields(_structured_state_fields(state))
            structured_fields['paused_main_problem'] = state.main_problem or state.active_problem
            structured_fields['paused_current_step'] = state.current_step
            structured_fields['paused_current_question'] = state.current_question or state.current_step
            structured_fields['paused_expected_answer'] = _current_expected_answer(state)
            structured_fields['paused_completed_steps'] = list(state.completed_steps)
            next_state = TutoringState(
                **structured_fields,
                active_problem=new_problem_text,
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
                mode='solve',
                status='solving',
                memory_note=state.memory_note,
            )
            next_state = transition_to_task(
                state,
                next_state,
                new_problem_text,
                subject=state.current_subject or 'Math',
                source='student',
                previous='pause',
            )
            return directives, new_problem_text, '', next_state

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
    elif action_intent == 'clarify_prompt':
        directives.append('The student is asking what the current prompt or step means, not giving an answer.')
        directives.append('Do not mark this as correct or wrong.')
        directives.append('Clarify the same current step or question in simpler words.')
        directives.append('Restate exactly what the student should do next, then ask the same step question again.')
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
        structured_fields = _structured_state_fields(state)
        preserved_active_problem = state.main_problem or state.active_problem or active_problem
        if action_intent == 'clarify_prompt' and unfinished_main_problem:
            next_state = TutoringState(
                **structured_fields,
                active_problem=preserved_active_problem,
                current_subject=state.current_subject,
                current_step=state.current_step,
                current_question=state.current_question or state.current_step,
                expected_answer=state.expected_answer,
                skill=skill,
                step_number=state.step_number,
                attempt_count=0,
                answer_revealed=False,
                mode='practice' if (state.current_question or state.current_step) else 'solve',
                status='waiting_for_student' if (state.current_question or state.current_step) else 'solving',
                memory_note=state.memory_note,
            )
            return directives, preserved_active_problem, state.current_step, next_state
        if switch_task and unfinished_main_problem and (state.main_problem.strip() or state.active_problem.strip()):
            structured_fields['paused_main_problem'] = state.main_problem or state.active_problem
            structured_fields['paused_current_step'] = state.current_step
            structured_fields['paused_current_question'] = state.current_question or state.current_step
            structured_fields['paused_expected_answer'] = _current_expected_answer(state)
            structured_fields['paused_completed_steps'] = list(state.completed_steps)
            if active_problem == (state.main_problem or state.active_problem):
                active_problem = message.strip()
        if (new_problem and not answer_to_current_math_step) or direct_help:
            if direct_question_override and (current_step or current_question):
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
            **structured_fields,
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
        if new_problem and not answer_to_current_math_step:
            next_state = transition_to_task(
                state,
                next_state,
                active_problem,
                subject=state.current_subject or 'Math',
                source='student',
                previous='pause' if unfinished_main_problem else 'abandon',
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


def build_new_problem_clarification_reply(state: TutoringState) -> str:
    current_problem = (state.main_problem or state.active_problem or '').strip()
    current_step = (state.current_question or state.current_step or '').strip()
    pending_problem = (state.pending_new_problem or '').strip()

    lines = []
    if pending_problem:
        lines.append(f'This looks like a new math problem: {_display_math_text(pending_problem)}.')
        lines.append('')
    if current_problem:
        lines.append(f'**Main problem:** {_display_math_text(current_problem)}.')
        lines.append('')
    if current_step:
        lines.append(f'**Current step:** {_display_math_text(current_step)}')
        lines.append('')
    lines.append('Tell me which one you want:')
    lines.append('part of this problem, or a new problem?')
    return '\n'.join(lines)


def build_switch_confirmation_reply(state: TutoringState, new_problem: str) -> str:
    previous_problem = (state.paused_main_problem or state.main_problem or state.active_problem or '').strip()
    lines = [
        f'Okay, we can solve this new problem first: {_display_math_text(new_problem.strip())}',
        '',
    ]
    if previous_problem:
        lines.extend([
            f'After that, I will bring you back to: {_display_math_text(previous_problem)}',
            '',
        ])
    lines.append("Let's start with the new problem now.")
    return '\n'.join(lines)


def build_temporary_math_problem_reply(new_problem: str) -> str:
    expression = extract_math_expression(normalize_math_text(new_problem))
    if not expression:
        return ''

    value = safe_eval_expression(expression)
    if value is None:
        return ''

    display_expression = _display_math_text(expression)
    answer = format_fraction(value)
    return '\n'.join([
        f"Okay, let's solve this new problem first: {display_expression}",
        '',
        f'{display_expression} = {answer}',
    ])


def build_resume_paused_problem_reply(state: TutoringState) -> str:
    paused_problem = (
        state.paused_main_problem
        or (state.active_problem if state.mode in {'resume_paused_problem', 'resume_paused_problem_notice'} else '')
        or ''
    ).strip()
    paused_question = (
        state.paused_current_question
        or state.paused_current_step
        or (state.current_question if state.mode in {'resume_paused_problem', 'resume_paused_problem_notice'} else '')
        or state.current_step
        or ''
    ).strip()
    completed = [item for item in state.paused_completed_steps if item]

    lines = ['We finished the new problem.', '']
    if paused_problem:
        lines.append(f"**Now let's return to your main problem:** {_display_math_text(paused_problem)}")
        lines.append('')
    if completed:
        shown = _display_math_text(', '.join(completed[:3]))
        lines.append(f'**We already completed:** {shown}')
        lines.append('')
    if paused_question:
        lines.append(f'**Current step:** {_display_math_text(paused_question)}')
        lines.append('')
        lines.append("Let's keep going from here.")
    return '\n'.join(lines)


def _display_math_text(text: str) -> str:
    text = str(text or '')
    text = text.replace('->', '→')
    text = re.sub(r'(?<=\d)\s*([+\-])\s*(?=\d)', r' \1 ', text)
    text = re.sub(r'(?<=\d)\s*\*(?=\d)', ' × ', text)
    return re.sub(r'(?<!\*)\*(?!\*)', '×', text)


def detect_off_subject_request(subject: str, message: str, state: TutoringState | None = None) -> bool:
    state = state or TutoringState()
    text = _normalized(message)
    if not text or detect_explicit_subject_switch(message):
        return False
    if subject == 'Math':
        if detect_math_expression(message):
            return False
        if any(word in text for word in MATH_TOPIC_WORDS):
            return False
        if _looks_like_general_knowledge_question(message):
            return True
        if any(word in text for word in SCIENCE_TOPIC_WORDS):
            return True
        if any(word in text for word in GENERAL_KNOWLEDGE_WORDS):
            return True
        return bool(re.match(r'^(what is|who is|tell me about)\b', text))
    if subject in {'ELA', 'Writing'} and detect_math_expression(message):
        return True
    if subject == 'ELA':
        if _looks_like_writing_task(message):
            return True
        if _looks_like_reading_task(message):
            return False
        if any(word in text for word in ELA_TOPIC_WORDS):
            return False
        return any(word in text for word in GENERAL_KNOWLEDGE_WORDS)
    if subject == 'Writing':
        if _looks_like_writing_task(message):
            return False
        if _looks_like_reading_task(message):
            return True
        if any(word in text for word in WRITING_TOPIC_WORDS):
            return False
        return any(word in text for word in GENERAL_KNOWLEDGE_WORDS)
    return False


def build_subject_boundary_reply(subject: str, state: TutoringState) -> str:
    subject_label = 'math' if subject == 'Math' else ('reading' if subject == 'ELA' else 'writing')
    main_problem = (state.main_problem or state.active_problem or '').strip()
    current_step = (state.current_question or state.current_step or '').strip()

    lines = [f'That is a different kind of question, and right now we are working on {subject_label}.', '']
    if main_problem:
        lines.append(f'We are still working on: {main_problem}.')
        lines.append('')
    if current_step:
        lines.append(f'Current step: {current_step}')
        lines.append('')
        lines.append("Let's keep going with this step first.")
    else:
        lines.append(f"Let's stay with {subject_label} for now.")
    return '\n'.join(lines)


def build_conversation_control_reply(state: TutoringState, intent: str, student_name: str = '') -> str:
    """Reply to conversational control messages without changing or inventing a learning task."""
    name = str(student_name or '').strip()
    greeting = f'Hi {name}!' if name else 'Hi!'
    current = (state.current_question or state.current_step).strip()
    active = (state.active_problem or state.main_problem).strip()
    subject_label = {
        'Math': 'Math',
        'ELA': 'reading',
        'Writing': 'writing',
    }.get(state.current_subject, 'learning')

    if intent == 'greeting':
        if current:
            return f'{greeting} We can continue when you are ready.\n\n{_display_math_text(current)}'
        if active:
            return f'{greeting} We can keep working on {_display_math_text(active)} when you are ready.'
        return f'{greeting} How are you feeling today?'

    if current:
        return f"Okay. Let's continue with the current {subject_label} step.\n\n{_display_math_text(current)}"
    if active:
        return f"Okay. Let's continue with {_display_math_text(active)}."
    if intent == 'continue_current':
        return 'Okay. What would you like to continue with?'
    return 'Okay. What would you like help with?'


def extract_followup_step(reply: str, subject: str = '') -> str:
    questions = [part.strip() for part in re.findall(r'[^.!?]*\?', reply) if part.strip()]
    if not questions:
        return ''
    if subject != 'Math':
        return questions[-1]

    for question in reversed(questions):
        if detect_math_expression(question):
            return question
        normalized_question = _normalized(question).rstrip('?').strip()
        if normalized_question in {
            'what do you get',
            'what is the answer',
            "what's the answer",
            'what did you get',
            'what is your answer',
        }:
            normalized_reply = normalize_math_text(reply)
            expressions = re.findall(
                r'-?\d+(?:\.\d+)?(?:\s*[+\-*/x]\s*-?\d+(?:\.\d+)?)+',
                normalized_reply,
                re.I,
            )
            if expressions:
                return f'What is {expressions[-1].strip()}?'
        number_count = len(re.findall(r'-?\d+(?:\.\d+)?', question))
        if number_count >= 2 and re.search(
            r'\b(add|plus|sum|subtract|minus|difference|multiply|times|product|divide|groups|each|fraction)\b',
            question,
            re.I,
        ):
            return question
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
    next_step = extract_followup_step(reply, state.current_subject)
    current_question = state.current_question or state.current_step
    same_question = bool(next_step and current_question and _same_question(next_step, current_question))
    next_step_number = state.step_number + 1 if next_step and not same_question else state.step_number
    switched_away_from_paused_problem = bool(
        state.paused_main_problem.strip()
        and state.active_problem.strip()
        and state.active_problem.strip() != state.paused_main_problem.strip()
    )

    if state.helper_branch.status == 'active' and state.helper_branch.question:
        helper_branch = state.helper_branch.model_copy(update={'status': 'completed'})
        restored_step = state.current_step
        restored_question = state.current_question or state.current_step
        restored_expected_answer = state.expected_answer
        restored_mode = 'practice' if restored_question else 'solve'
        restored_status = 'waiting_for_student' if restored_question else 'solving'
        structured_fields = _clear_pending_problem_fields(_structured_state_fields(state))
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

    if switched_away_from_paused_problem and not next_step and can_resume_paused_task(state):
        return complete_and_resume_latest(state)

    if state.mode == 'tutor_practice_question' and state.problem_status == 'tutor_practice':
        return TutoringState(
            **_clear_pending_problem_fields(_structured_state_fields(state)),
            active_problem=state.active_problem,
            current_subject=state.current_subject,
            current_step=state.current_step or state.current_question,
            current_question=state.current_question or state.current_step,
            expected_answer=state.expected_answer,
            student_answer=state.student_answer,
            correctness_status='',
            skill=state.skill,
            step_number=state.step_number,
            attempt_count=state.attempt_count,
            hint_given=state.hint_given,
            answer_revealed=state.answer_revealed,
            next_similar_question='',
            mode='tutor_practice_question',
            status='waiting_for_student',
            memory_note=_build_memory_note(state.active_problem, reply, state.memory_note),
        )

    if state.ordered_steps and state.current_step_id and state.problem_status in {'in_progress', 'awaiting_step'}:
        if next_step:
            return TutoringState(
                **_clear_pending_problem_fields(_structured_state_fields(state)),
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
            **_clear_pending_problem_fields(_structured_state_fields(state)),
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
            **_clear_pending_problem_fields(_structured_state_fields(state)),
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

    terminal_state = TutoringState(
        **_clear_pending_problem_fields(_structured_state_fields(state)),
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
        mode='resume_paused_problem' if can_resume_paused_task(state) else 'solve',
        status='waiting_to_resume' if can_resume_paused_task(state) else 'finished',
        memory_note=_build_memory_note(active_problem, reply, state.memory_note),
    )
    if can_resume_paused_task(state):
        return complete_and_resume_latest(terminal_state)
    return terminal_state
