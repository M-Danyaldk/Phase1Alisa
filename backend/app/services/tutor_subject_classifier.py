import json
import re

from pydantic import BaseModel

from ..models import TutoringState
from ..tutoring_logic import (
    ELA_TOPIC_WORDS,
    GENERAL_KNOWLEDGE_WORDS,
    MATH_TOPIC_WORDS,
    WRITING_TOPIC_WORDS,
    _normalized,
    _looks_like_reading_task,
    _looks_like_writing_task,
    detect_explicit_subject_switch,
    detect_math_expression,
    detect_off_subject_request,
)
from .llm.router import LLMRouter


class SubjectClassificationResult(BaseModel):
    label: str = 'ambiguous'
    confidence: str = 'low'
    reason: str = ''


class TutorSubjectClassifier:
    def should_use_fallback(self, subject: str, message: str, state: TutoringState | None = None) -> bool:
        state = state or TutoringState()
        text = _normalized(message)
        if not text:
            return False
        if detect_explicit_subject_switch(message):
            return False
        if detect_off_subject_request(subject, message, state):
            return False

        subject_words = self._subject_words(subject)
        request_like = bool(re.match(r'^(what|who|how|why|tell me|explain|help me|can you help|can you explain|can you check)\b', text))
        has_math = detect_math_expression(message)
        has_subject_words = any(word in text for word in subject_words)
        has_general_knowledge = any(word in text for word in GENERAL_KNOWLEDGE_WORDS)

        if subject == 'Math':
            if has_math or has_subject_words:
                return False
            return request_like or has_general_knowledge

        if subject == 'ELA':
            if has_math:
                return False
            if _looks_like_reading_task(message):
                return False
            if _looks_like_writing_task(message):
                return False
            if has_subject_words:
                return False
            return request_like or has_general_knowledge

        if subject == 'Writing':
            if has_math:
                return False
            if _looks_like_writing_task(message):
                return False
            if _looks_like_reading_task(message):
                return False
            if has_subject_words:
                return False
            return request_like or has_general_knowledge

        return False

    async def classify_if_needed(self, subject: str, message: str, state: TutoringState | None = None) -> SubjectClassificationResult:
        state = state or TutoringState()
        if not self.should_use_fallback(subject, message, state):
            return SubjectClassificationResult()
        result = await self._classify_with_llm(subject, message, state)
        if result.label not in {'in_subject', 'off_subject', 'explicit_subject_switch', 'ambiguous'}:
            return SubjectClassificationResult()
        if result.confidence not in {'high', 'medium', 'low'}:
            result.confidence = 'low'
        if result.confidence == 'low':
            return SubjectClassificationResult()
        return result

    async def _classify_with_llm(self, subject: str, message: str, state: TutoringState) -> SubjectClassificationResult:
        system = (
            'You classify whether a Grades 3-6 student message fits the current tutor subject. '
            'Return compact JSON only with keys: label, confidence, reason. '
            'label must be one of: in_subject, off_subject, explicit_subject_switch, ambiguous. '
            'confidence must be one of: high, medium, low.'
        )
        user = (
            f'Current tutor subject: {subject}\n'
            f'Active main problem or task: {state.main_problem or state.active_problem or "none"}\n'
            f'Current step: {state.current_question or state.current_step or "none"}\n'
            f'Student message: {message}\n'
            'Classify whether the message should stay in the current subject, is off-subject, explicitly asks to switch subject, or is ambiguous.'
        )
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            return SubjectClassificationResult(
                label=str(parsed.get('label') or 'ambiguous'),
                confidence=str(parsed.get('confidence') or 'low'),
                reason=str(parsed.get('reason') or ''),
            )
        except Exception:
            return SubjectClassificationResult()

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

    def _subject_words(self, subject: str) -> set[str]:
        if subject == 'Math':
            return MATH_TOPIC_WORDS
        if subject == 'ELA':
            return ELA_TOPIC_WORDS
        if subject == 'Writing':
            return WRITING_TOPIC_WORDS
        return set()
