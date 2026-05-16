import ast
import json
import operator
import re
from dataclasses import dataclass
from fractions import Fraction

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
        expression = self._extract_math_expression(answer)
        if expression:
            value = self._safe_eval_expression(expression)
            if value is not None:
                return value
        mixed = re.search(r'(-?\d+)\s+(\d+)\s*/\s*(\d+)', answer)
        if mixed:
            whole = int(mixed.group(1))
            numerator = int(mixed.group(2))
            denominator = int(mixed.group(3))
            sign = -1 if whole < 0 else 1
            return Fraction(whole, 1) + sign * Fraction(numerator, denominator)
        fraction = re.search(r'-?\d+\s*/\s*-?\d+', answer)
        if fraction:
            try:
                return Fraction(fraction.group(0).replace(' ', ''))
            except ZeroDivisionError:
                return None
        decimal = re.search(r'-?\d+(?:\.\d+)?', answer)
        if decimal:
            return Fraction(decimal.group(0))
        return None

    def _extract_math_expression(self, text: str) -> str:
        normalized = (
            text.replace('×', '*')
            .replace('Ã—', '*')
            .replace('÷', '/')
            .replace('Ã·', '/')
            .replace('−', '-')
            .replace('âˆ’', '-')
        )
        candidates = re.findall(r'[\d\s\+\-\*/\(\)\.]+', normalized)
        candidates = [candidate.strip() for candidate in candidates if any(op in candidate for op in ['+', '-', '*', '/'])]
        return max(candidates, key=len) if candidates else ''

    def _safe_eval_expression(self, expression: str) -> Fraction | None:
        try:
            tree = ast.parse(expression, mode='eval')
            return self._eval_node(tree.body)
        except Exception:
            return None

    def _eval_node(self, node: ast.AST) -> Fraction:
        operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
        }
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._eval_node(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
        raise ValueError('Unsupported math expression')

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
        if value.denominator == 1:
            return str(value.numerator)
        return f'{value.numerator}/{value.denominator}'
