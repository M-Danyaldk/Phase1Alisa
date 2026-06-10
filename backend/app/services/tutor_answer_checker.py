import json
import re
from dataclasses import dataclass
from fractions import Fraction

from ..assessment_validation import extract_math_expression, extract_numeric_value, format_fraction, safe_eval_expression
from ..services.llm.router import LLMRouter


@dataclass
class AnswerCheckResult:
    status: str = 'unclear'
    expected_answer: str = ''
    feedback_note: str = ''

    @property
    def is_wrong(self) -> bool:
        return self.status in {'incorrect', 'partially_correct', 'unclear'}

    @property
    def is_correct(self) -> bool:
        return self.status == 'correct'


class TutorAnswerChecker:
    async def check(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str = '',
    ) -> AnswerCheckResult:
        math_result = self._check_math(question, student_answer, expected_answer)
        if math_result.status != 'unclear':
            return math_result
        if expected_answer.strip():
            text_result = self._check_text_against_expected(student_answer, expected_answer)
            if text_result.status != 'unclear':
                return text_result
        return await self._classify_with_llm(subject, question, student_answer, expected_answer)

    def _check_math(self, question: str, student_answer: str, expected_answer: str) -> AnswerCheckResult:
        expected_value = self._extract_expected_math_value(question, expected_answer)
        student_value = self._extract_student_math_value(student_answer)
        if expected_value is None or student_value is None:
            return AnswerCheckResult()
        if expected_value == student_value:
            return AnswerCheckResult(status='correct', expected_answer=self._format_fraction(expected_value))
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=self._format_fraction(expected_value),
            feedback_note='The numeric answer does not match the expected answer.',
        )

    def _extract_expected_math_value(self, question: str, expected_answer: str) -> Fraction | None:
        if expected_answer.strip():
            value = self._extract_student_math_value(expected_answer)
            if value is not None:
                return value
        expression = self._extract_math_expression(question)
        if not expression:
            return None
        return self._safe_eval_expression(expression)

    def _extract_student_math_value(self, answer: str) -> Fraction | None:
        return extract_numeric_value(answer)

    def _extract_math_expression(self, text: str) -> str:
        return extract_math_expression(text)

    def _safe_eval_expression(self, expression: str) -> Fraction | None:
        return safe_eval_expression(expression)

    def _check_text_against_expected(self, student_answer: str, expected_answer: str) -> AnswerCheckResult:
        student_words = self._keyword_set(student_answer)
        expected_words = self._keyword_set(expected_answer)
        if not expected_words:
            return AnswerCheckResult()
        overlap = len(student_words & expected_words) / max(len(expected_words), 1)
        if overlap >= 0.7:
            return AnswerCheckResult(status='correct', expected_answer=expected_answer)
        if overlap >= 0.35:
            return AnswerCheckResult(status='partially_correct', expected_answer=expected_answer)
        return AnswerCheckResult(status='incorrect', expected_answer=expected_answer)

    async def _classify_with_llm(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str,
    ) -> AnswerCheckResult:
        system = (
            'You are checking a Grades 3-6 tutor practice answer. '
            'Return compact JSON only with keys: status, expected_answer, feedback_note. '
            'status must be one of: correct, partially_correct, incorrect, unclear.'
        )
        user = (
            f'Subject: {subject}\n'
            f'Question: {question}\n'
            f'Expected answer if known: {expected_answer or "not provided"}\n'
            f'Student answer: {student_answer}\n'
            'Classify the student answer. If expected answer is not provided, infer the likely correct answer from the question when possible.'
        )
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            status = parsed.get('status', 'unclear')
            if status not in {'correct', 'partially_correct', 'incorrect', 'unclear'}:
                status = 'unclear'
            return AnswerCheckResult(
                status=status,
                expected_answer=str(parsed.get('expected_answer') or expected_answer or ''),
                feedback_note=str(parsed.get('feedback_note') or ''),
            )
        except Exception:
            return AnswerCheckResult()

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', text, re.S)
            if match:
                return json.loads(match.group(0))
        return {}

    def _keyword_set(self, text: str) -> set[str]:
        stop = {'the', 'a', 'an', 'is', 'are', 'to', 'of', 'and', 'in', 'it', 'this', 'that'}
        return {word for word in re.findall(r'[a-zA-Z]+', text.lower()) if word not in stop and len(word) > 2}

    def _format_fraction(self, value: Fraction) -> str:
        return format_fraction(value)
