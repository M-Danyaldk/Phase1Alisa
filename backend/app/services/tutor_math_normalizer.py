import json
import re

from pydantic import BaseModel

from ..assessment_bank import NUMBER_WORDS
from ..assessment_validation import extract_math_expression, normalize_math_text, normalize_word_numbers_in_text, safe_eval_expression
from ..models import TutoringState
from .llm.router import LLMRouter


class MathNormalizationResult(BaseModel):
    normalized_expression: str = ''
    confidence: str = 'low'
    reason: str = ''


class TutorMathNormalizer:
    WORD_MATH_MARKERS = (
        'plus',
        'minus',
        'times',
        'multiplied by',
        'divided by',
        'over',
        'open parenthesis',
        'close parenthesis',
        'parentheses',
    )

    def should_use_fallback(self, subject: str, message: str, state: TutoringState | None = None) -> bool:
        if subject != 'Math':
            return False

        text = str(message or '').strip().lower()
        if not text:
            return False

        normalized = normalize_math_text(text)
        extracted = extract_math_expression(normalized)
        extracted_value = safe_eval_expression(extracted) if extracted else None

        has_number_words = any(re.search(rf'\b{re.escape(word)}\b', text) for word in NUMBER_WORDS.values())
        has_word_math = any(marker in text for marker in self.WORD_MATH_MARKERS)
        has_symbolic_math = bool(re.search(r'\d', text)) and any(symbol in text for symbol in ('+', '-', '*', '/', '(', ')'))
        mixed_symbolic_and_word_math = has_word_math and has_symbolic_math
        malformed_symbolic = any(token in text for token in ['//', '**', '++', '--']) or bool(re.search(r'[\+\-\*/]\s*$', text))
        mismatched_parentheses = text.count('(') != text.count(')')
        math_like_text = bool(re.search(r'\d', text)) or has_number_words or has_word_math or '(' in text or ')' in text
        active_answer_context = bool(state and (state.current_question.strip() or state.current_step.strip()))
        answer_language = bool(re.search(
            r'\b(answer|result|should be|i got|i think|probably|reckon|equals?)\b',
            text,
        ))

        # Answer interpretation belongs to the typed intent layer. Sending a
        # prose answer through the expression normalizer first can turn two
        # mentioned attempts into a fabricated expression.
        if active_answer_context and not has_word_math and not has_symbolic_math and (answer_language or has_number_words):
            return False

        if not math_like_text:
            return False
        if has_number_words and has_word_math:
            return True
        if mixed_symbolic_and_word_math:
            return True
        if extracted and extracted_value is not None and not has_number_words and not malformed_symbolic and not mismatched_parentheses:
            return False
        if malformed_symbolic or mismatched_parentheses:
            return True
        if not extracted:
            return True
        if extracted_value is None:
            return True
        return False

    async def normalize_if_needed(self, subject: str, message: str, state: TutoringState | None = None) -> MathNormalizationResult:
        if not self.should_use_fallback(subject, message, state):
            return MathNormalizationResult()
        deterministic = self._deterministic_normalize(message)
        if deterministic:
            return MathNormalizationResult(
                normalized_expression=deterministic,
                confidence='high',
                reason='deterministic_spoken_math',
            )
        result = await self._normalize_with_llm(message, state or TutoringState())
        if result.confidence not in {'high', 'medium', 'low'}:
            result.confidence = 'low'
        if result.confidence == 'low':
            return MathNormalizationResult()
        normalized = self._clean_expression(result.normalized_expression)
        if not normalized:
            return MathNormalizationResult()
        extracted = extract_math_expression(normalized) or normalized
        if safe_eval_expression(extracted) is None and not self._looks_like_multi_step_expression(extracted):
            return MathNormalizationResult()
        return result.model_copy(update={'normalized_expression': extracted})

    async def _normalize_with_llm(self, message: str, state: TutoringState) -> MathNormalizationResult:
        system = (
            'You normalize Grades 3-6 student math input into clean symbolic math. '
            'Return compact JSON only with keys: normalized_expression, confidence, reason. '
            'confidence must be one of: high, medium, low. '
            'If the math is too unclear to repair safely, return an empty normalized_expression and confidence low.'
        )
        user = (
            f'Active main problem: {state.main_problem or state.active_problem or "none"}\n'
            f'Current step: {state.current_question or state.current_step or "none"}\n'
            f'Student math input: {message}\n'
            'Rewrite the student input into a clean symbolic math expression using digits, +, -, *, /, and parentheses only. '
            'Do not solve the problem. Only normalize it.'
        )
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            return MathNormalizationResult(
                normalized_expression=str(parsed.get('normalized_expression') or ''),
                confidence=str(parsed.get('confidence') or 'low'),
                reason=str(parsed.get('reason') or ''),
            )
        except Exception:
            return MathNormalizationResult()

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

    def _clean_expression(self, expression: str) -> str:
        normalized = normalize_math_text(expression)
        normalized = normalized.replace('=', ' ')
        normalized = re.sub(r'[^0-9\+\-\*/\(\)\.\s]', ' ', normalized)
        normalized = re.sub(r'(?<![\d/])(-?\d+)\s*/\s*(-?\d+)(?![\d/])', r'\1/\2', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _deterministic_normalize(self, message: str) -> str:
        text = str(message or '').strip().lower()
        if not text:
            return ''
        if not any(marker in text for marker in self.WORD_MATH_MARKERS):
            return ''

        normalized = normalize_word_numbers_in_text(text)
        replacements = (
            ('open parenthesis', ' ( '),
            ('close parenthesis', ' ) '),
            ('open parentheses', ' ( '),
            ('close parentheses', ' ) '),
            ('multiplied by', ' * '),
            ('times', ' * '),
            ('plus', ' + '),
            ('minus', ' - '),
            ('divided by', ' / '),
            ('over', ' / '),
        )
        for old, new in replacements:
            normalized = re.sub(rf'\b{re.escape(old)}\b', new, normalized)

        normalized = normalized.replace(',', ' ')
        normalized = normalized.replace('=', ' ')
        normalized = re.sub(r'[^0-9\+\-\*/\(\)\.\s]', ' ', normalized)
        normalized = re.sub(r'(?<![\d/])(-?\d+)\s*/\s*(-?\d+)(?![\d/])', r'\1/\2', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        extracted = extract_math_expression(normalized) or normalized
        if not extracted:
            return ''
        if safe_eval_expression(extracted) is None and not self._looks_like_multi_step_expression(extracted):
            return ''
        return extracted

    def _looks_like_multi_step_expression(self, expression: str) -> bool:
        compact = str(expression or '').replace(' ', '')
        operators = len(re.findall(r'(?<!/)[+\-*](?!/)', compact))
        return operators >= 2 or ('(' in compact and ')' in compact)
