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
    detect_direct_help_intent,
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
    'clarification_about_context',
    'off_subject',
    'unknown',
}


class IntentClassificationResult(BaseModel):
    label: str = 'unknown'
    confidence: str = 'low'
    reason: str = ''


class TutorIntentClassifier:
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
