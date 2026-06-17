import json
import re
from dataclasses import dataclass
from fractions import Fraction

from ..assessment_bank import AssessmentQuestion, all_assessment_versions
from ..assessment_validation import extract_math_expression, extract_numeric_value, format_fraction, normalize_answer_text, normalize_math_text, safe_eval_expression, validate_assessment_answer
from ..services.llm.router import LLMRouter


@dataclass
class AnswerCheckResult:
    status: str = 'unclear'
    expected_answer: str = ''
    feedback_note: str = ''
    checked_expression: str = ''

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
        local_text_result = self._check_local_text_prompt(subject, question, student_answer, expected_answer)
        if local_text_result.status != 'unclear':
            return local_text_result
        if expected_answer.strip():
            text_result = self._check_text_against_expected(student_answer, expected_answer)
            if text_result.status != 'unclear':
                return text_result
        return await self._classify_with_llm(subject, question, student_answer, expected_answer)

    def check_direct_math_statement(self, message: str) -> AnswerCheckResult:
        expression = self._extract_direct_expression(message)
        stated_answer = self._extract_stated_answer(message)
        if not expression or not stated_answer:
            return AnswerCheckResult()

        expected_value = self._safe_eval_expression(expression)
        student_value = self._extract_student_math_value(stated_answer)
        if expected_value is None or student_value is None:
            return AnswerCheckResult()

        expected_answer = self._format_fraction(expected_value)
        display_expression = self._display_expression(expression)
        if expected_value == student_value:
            return AnswerCheckResult(
                status='correct',
                expected_answer=expected_answer,
                checked_expression=display_expression,
                feedback_note='Direct math answer checked deterministically.',
            )
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=expected_answer,
            checked_expression=display_expression,
            feedback_note='Direct math answer does not match the expression value.',
        )

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

    def _extract_direct_expression(self, text: str) -> str:
        normalized = normalize_math_text(text)
        match = re.search(r'(-?\d+(?:\.\d+)?)\s*([x\*\+/\-])\s*(-?\d+(?:\.\d+)?)', normalized)
        if not match:
            return ''
        operator = '*' if match.group(2) == 'x' else match.group(2)
        return f'{match.group(1)} {operator} {match.group(3)}'

    def _extract_stated_answer(self, text: str) -> str:
        normalized = normalize_math_text(text)
        answer_match = re.search(
            r'(?:my\s+answer|answer|i\s+got|i\s+think\s+it\s+is|it\s+is|equals?)\s*(?:is|=|:)?\s*(-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?)',
            normalized,
        )
        if answer_match:
            return answer_match.group(1)
        numbers = re.findall(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?', normalized)
        return numbers[-1] if len(numbers) >= 3 else ''

    def _display_expression(self, expression: str) -> str:
        return expression.replace('*', '×').replace('/', '÷')

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

    def _check_local_text_prompt(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str,
    ) -> AnswerCheckResult:
        pseudo = self._pseudo_question(subject, question, expected_answer)
        if not pseudo:
            return AnswerCheckResult()
        validation = validate_assessment_answer(pseudo, student_answer)
        if validation.status == 'needs_review':
            return AnswerCheckResult()
        return AnswerCheckResult(
            status=validation.status,
            expected_answer=validation.expected_answer,
            feedback_note=validation.feedback_note,
        )

    def _pseudo_question(self, subject: str, question: str, expected_answer: str) -> AssessmentQuestion | None:
        clean_question = str(question or '').strip()
        if not clean_question:
            return None
        lower = clean_question.lower()
        matched = self._lookup_bank_question(subject, clean_question)
        if matched:
            return matched

        if subject == 'Writing':
            if self._matches_writing_single_sentence_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'One complete sentence that stays on topic.', 'complete sentence')
            if self._matches_writing_three_sentence_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'Three connected explanatory sentences with a clear reason and details.', 'explanatory writing')
            if self._matches_writing_revision_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'A stronger sentence with more specific detail or vivid word choice.', 'revision for detail')

        if lower.startswith('fix this sentence:'):
            return self._build_pseudo_question(subject, clean_question, 'exact_text', expected_answer, 'grammar and conventions')
        if 'what does "' in lower and '" mean' in lower:
            return self._build_pseudo_question(subject, clean_question, 'keyword_text', expected_answer, 'vocabulary in context')
        if subject == 'ELA' and expected_answer.strip():
            return self._build_pseudo_question(subject, clean_question, 'keyword_text', expected_answer, 'reading comprehension')
        return None

    def _matches_writing_single_sentence_prompt(self, lower: str) -> bool:
        return lower.startswith('write one clear sentence')

    def _matches_writing_three_sentence_prompt(self, lower: str) -> bool:
        return bool(re.match(r'^write\s+(?:3|three)\s+sentences\b', lower))

    def _matches_writing_revision_prompt(self, lower: str) -> bool:
        return lower.startswith('how can you make this sentence stronger') or lower.startswith('make this sentence stronger')

    def _lookup_bank_question(self, subject: str, question: str) -> AssessmentQuestion | None:
        normalized = normalize_answer_text(question)
        if not normalized:
            return None
        for version in all_assessment_versions():
            for item in version.questions:
                if item.subject == subject and normalize_answer_text(item.question) == normalized:
                    return item
        return None

    def _build_pseudo_question(
        self,
        subject: str,
        question: str,
        validation_type: str,
        expected_answer: str,
        skill: str,
    ) -> AssessmentQuestion:
        accepted_answers = (expected_answer,) if expected_answer.strip() and validation_type in {'exact_text', 'keyword_text'} else ()
        return AssessmentQuestion(
            id='tutor-local-check',
            subject=subject,
            grade=4,
            version=0,
            position=1,
            skill=skill,
            question=question,
            validation_type=validation_type,
            expected_answer=expected_answer,
            accepted_answers=accepted_answers,
            rubric=(),
            next_topic_if_incorrect=skill,
            child_correct_feedback='',
            child_incorrect_feedback='',
        )

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
