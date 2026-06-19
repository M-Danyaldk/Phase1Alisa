import json
import re

from pydantic import BaseModel

from ..models import ChatHistoryItem, TutoringState
from ..tutoring_logic import (
    _has_unfinished_main_problem,
    _looks_like_answer_to_current_math_step,
    _normalized,
    detect_confused_intent,
    detect_context_clarification_intent,
    detect_definition_intent,
    detect_explicit_subject_switch,
    detect_homework_or_skip_intent,
    detect_math_expression,
    detect_switch_task_intent,
    detect_tutor_concern_intent,
)
from .llm.router import LLMRouter

INTENT_LABELS = {
    'answer_current_step',
    'related_question',
    'new_problem',
    'switch_request',
    'topic_switch',
    'help_request',
    'emotion',
    'pause',
    'resume',
    'meta_feedback',
    'clarification_about_context',
    'off_subject',
    'unknown',
}

NON_ANSWER_INTENTS = {
    'related_question',
    'new_problem',
    'switch_request',
    'topic_switch',
    'help_request',
    'emotion',
    'pause',
    'resume',
    'meta_feedback',
    'clarification_about_context',
    'off_subject',
}

MATH_TOPIC_ALIASES = {
    'fraction': ('fraction', 'fractions', 'numerator', 'denominator', 'equivalent fraction'),
    'decimal': ('decimal', 'decimals'),
    'multiplication': ('multiplication', 'multiply', 'times tables', 'times table'),
    'division': ('division', 'divide'),
    'addition': ('addition', 'add'),
    'subtraction': ('subtraction', 'subtract'),
    'geometry': ('geometry', 'area', 'perimeter', 'shape', 'shapes'),
}

EMOTION_ALIASES = {
    'crisis': ('i want to die', 'kill myself', 'hurt myself', 'i want to hurt myself', 'i might hurt myself', "i don't want to be alive", 'i do not want to be alive', 'i am not safe'),
    'tired': ('i am tired', "i'm tired", 'im tired', 'feeling tired', 'too tired'),
    'frustrated': ('i am frustrated', "i'm frustrated", 'im frustrated', 'this is frustrating'),
    'upset': ('i am upset', "i'm upset", 'im upset'),
    'sad': ('i am sad', "i'm sad", 'im sad'),
    'nervous': ('i am nervous', "i'm nervous", 'im nervous', 'i am worried', "i'm worried"),
    'overwhelmed': ('i am overwhelmed', "i'm overwhelmed", 'im overwhelmed', 'this is too much'),
    'discouraged': ("i can't do this", 'i cannot do this', "i'm stupid", 'i am stupid', 'i hate math', 'i am bad at math', "i'm bad at math", 'i give up'),
}


class IntentClassificationResult(BaseModel):
    label: str = 'unknown'
    confidence: str = 'low'
    reason: str = ''
    emotion: str = ''
    requested_topic: str = ''

    @property
    def counts_as_answer(self) -> bool:
        return self.label == 'answer_current_step'


class TutorIntentClassifier:
    def classify_deterministically(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        text = _normalized(message)
        if not text:
            return IntentClassificationResult()

        emotion = self._detected_emotion(text)
        if emotion:
            return IntentClassificationResult(
                label='emotion',
                confidence='high',
                reason='Student expressed an emotional state rather than submitting an answer.',
                emotion=emotion,
            )

        if self._is_pause_request(text):
            return IntentClassificationResult(
                label='pause',
                confidence='high',
                reason='Student asked to pause or take a break.',
            )

        if self._is_resume_request(text):
            return IntentClassificationResult(
                label='resume',
                confidence='high',
                reason='Student asked to resume a saved task.',
            )

        requested_topic = self._requested_math_topic(subject, text)
        if requested_topic:
            return IntentClassificationResult(
                label='topic_switch',
                confidence='high',
                reason='Student clearly requested a different Math topic.',
                requested_topic=requested_topic,
            )

        if detect_explicit_subject_switch(message) or detect_switch_task_intent(message):
            return IntentClassificationResult(
                label='switch_request',
                confidence='high',
                reason='Student clearly asked to switch the current task.',
            )

        if detect_tutor_concern_intent(message) or re.search(
            r'\b(you already|wrong question|that was wrong|you changed|you forgot|not what i asked)\b',
            text,
        ):
            return IntentClassificationResult(
                label='meta_feedback',
                confidence='high',
                reason='Student is commenting on the tutor or the conversation flow.',
            )

        if detect_context_clarification_intent(message):
            return IntentClassificationResult(
                label='clarification_about_context',
                confidence='high',
                reason='Student is clarifying which task the conversation is about.',
            )

        if detect_homework_or_skip_intent(message):
            return IntentClassificationResult(
                label='help_request',
                confidence='high',
                reason='Student requested homework help or asked to skip the current check.',
            )

        if detect_definition_intent(message):
            return IntentClassificationResult(
                label='related_question',
                confidence='high',
                reason='Student asked for a definition or explanation.',
            )

        if self._is_help_request(text):
            return IntentClassificationResult(
                label='help_request',
                confidence='high',
                reason='Student asked for help rather than submitting an answer.',
            )

        if self._looks_like_related_question(text, state):
            return IntentClassificationResult(
                label='related_question',
                confidence='high',
                reason='Student asked why or how the current Math step works.',
            )

        if self._looks_like_word_problem(text):
            return IntentClassificationResult(
                label='new_problem',
                confidence='high',
                reason='Student supplied a new text-based Math problem.',
            )

        if _has_unfinished_main_problem(state) and _looks_like_answer_to_current_math_step(
            message,
            state.current_question or state.current_step,
        ):
            return IntentClassificationResult(
                label='answer_current_step',
                confidence='high',
                reason='Student supplied a likely answer to the active step.',
            )

        return IntentClassificationResult()

    def should_use_fallback(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> bool:
        text = _normalized(message)
        if not text:
            return False
        if not _has_unfinished_main_problem(state):
            return False
        if detect_explicit_subject_switch(message):
            return False
        if detect_switch_task_intent(message):
            return False
        if detect_context_clarification_intent(message):
            return False
        if detect_tutor_concern_intent(message):
            return False
        if detect_homework_or_skip_intent(message):
            return False
        if detect_definition_intent(message):
            return False
        if _looks_like_answer_to_current_math_step(message, state.current_question or state.current_step):
            return False

        ambiguity_markers = (
            'i think',
            'maybe',
            'i mean',
            'no i mean',
            'or',
            'instead',
            'first',
            'before',
            'after',
            'came',
            'became',
            'how did',
            'what do you mean',
        )
        mixed_math_and_text = detect_math_expression(message) and bool(re.search(r'[a-zA-Z]', message))
        ambiguous_text = any(marker in text for marker in ambiguity_markers)
        confused = detect_confused_intent(message) and len(text) > 12

        if mixed_math_and_text:
            return True
        if ambiguous_text:
            return True
        if confused:
            return True
        return False

    async def classify_if_needed(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        deterministic = self.classify_deterministically(subject, message, history, state)
        if deterministic.label != 'unknown':
            return deterministic
        if not self.should_use_fallback(subject, message, history, state):
            return IntentClassificationResult()
        result = await self._classify_with_llm(subject, message, history, state)
        if result.label not in INTENT_LABELS:
            return IntentClassificationResult()
        if result.confidence not in {'high', 'medium', 'low'}:
            result.confidence = 'low'
        if result.confidence == 'low':
            return IntentClassificationResult()
        return result

    def _detected_emotion(self, text: str) -> str:
        if re.search(
            r"\b(want to die|kill myself|hurt myself|end my life|don['’]?t (?:want to be alive|feel safe)|do not (?:want to be alive|feel safe)|not safe|better off dead)\b",
            text,
        ):
            return 'crisis'
        for emotion, phrases in EMOTION_ALIASES.items():
            if any(re.search(rf'(?<![a-z]){re.escape(phrase)}(?![a-z])', text) for phrase in phrases):
                return emotion
        return ''

    def _is_pause_request(self, text: str) -> bool:
        return bool(re.search(r'\b(pause|take a break|need a break|stop for now|come back later)\b', text))

    def _is_resume_request(self, text: str) -> bool:
        return bool(re.search(r"\b(i am back|i'm back|im back|continue|keep going|resume)\b", text))

    def _requested_math_topic(self, subject: str, text: str) -> str:
        if subject != 'Math':
            return ''
        request_shape = bool(re.search(
            r'\b(i want|i need|i would like|i\'d like|teach me|help me (?:learn|with)|can we|could we|let\'s|lets|move to|go to|practice|learn)\b',
            text,
        ))
        if not request_shape:
            return ''
        for topic, aliases in MATH_TOPIC_ALIASES.items():
            if any(re.search(rf'\b{re.escape(alias)}s?\b', text) for alias in aliases):
                return topic
        return ''

    def _is_help_request(self, text: str) -> bool:
        return bool(re.search(
            r'^(hint|help|help me|show me|explain(?: it)?|i do not know|i don\'t know|i dont know|i am stuck|i\'m stuck|im stuck)\b',
            text,
        ))

    def _looks_like_related_question(self, text: str, state: TutoringState) -> bool:
        if not _has_unfinished_main_problem(state):
            return False
        return bool(re.match(r'^(why|how|what do you mean|where did|how did|why do|why did)\b', text))

    def _looks_like_word_problem(self, text: str) -> bool:
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        if len(numbers) < 2:
            return False
        word_problem_markers = (
            'there are',
            'there were',
            'each ',
            'altogether',
            'in total',
            'how many',
            'how much',
            'left',
            'remaining',
            'capacity',
            'rows',
            'boxes',
            'students',
            'cookies',
            'balls',
            'seats',
        )
        return len(text) >= 35 and any(marker in text for marker in word_problem_markers)

    async def _classify_with_llm(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        system = (
            'You classify a child tutor message for Grades 3-6. '
            'Return compact JSON only with keys: label, confidence, reason. '
            'label must be one of: answer_current_step, related_question, new_problem, switch_request, clarification_about_context, off_subject, unknown. '
            'confidence must be one of: high, medium, low.'
        )
        recent_history = '\n'.join(f'{item.role}: {item.content}' for item in history[-4:])
        user = (
            f'Subject: {subject}\n'
            f'Active main problem: {state.main_problem or state.active_problem or "none"}\n'
            f'Current step: {state.current_question or state.current_step or "none"}\n'
            f'Recent history:\n{recent_history or "none"}\n'
            f'Student message: {message}\n'
            'Classify the message intent. Only choose answer_current_step if the student is probably answering the current step. '
            'Choose related_question if the student is asking about the current problem. '
            'Choose new_problem if the student seems to be introducing a different problem without clearly asking to switch. '
            'Choose switch_request only if the student clearly wants to do the new thing first.'
        )
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            return IntentClassificationResult(
                label=str(parsed.get('label') or 'unknown'),
                confidence=str(parsed.get('confidence') or 'low'),
                reason=str(parsed.get('reason') or ''),
            )
        except Exception:
            return IntentClassificationResult()

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', text, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return {}
        return {}
