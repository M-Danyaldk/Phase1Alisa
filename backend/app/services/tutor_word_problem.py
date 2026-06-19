import json
import re
from collections import Counter
from fractions import Fraction

from pydantic import BaseModel, Field

from ..assessment_validation import format_fraction, normalize_word_numbers_in_text, safe_eval_expression
from ..models import TutoringState
from ..utils.task_lifecycle import transition_to_task
from .llm.router import LLMRouter

NUMBER_TOKEN = r'(?<![\d/])-?\d+(?:/\d+|\.\d+)?(?![\d/])'


class WordProblemQuantity(BaseModel):
    value: str
    label: str = ''
    role: str = 'given'


class StructuredWordProblem(BaseModel):
    original_text: str = ''
    problem_type: str = 'word_problem'
    operation: str = ''
    quantities: list[WordProblemQuantity] = Field(default_factory=list)
    unknown_label: str = ''
    expression: str = ''
    expected_answer: str = ''
    confidence: str = 'low'
    source: str = 'none'
    validation_status: str = 'rejected'

    @property
    def accepted(self) -> bool:
        return self.validation_status == 'verified' and bool(self.expression and self.expected_answer)


class TutorWordProblemInterpreter:
    """Interpret prose with an LLM, but trust only deterministically verified math."""

    def is_candidate(self, subject: str, message: str) -> bool:
        if subject != 'Math':
            return False
        text = self._clean_problem_text(message)
        if len(re.findall(NUMBER_TOKEN, text)) < 2:
            return False
        markers = (
            'each', 'every', 'altogether', 'in total', 'total', 'left', 'remain',
            'shared', 'equally', 'per ', 'more', 'sold', 'gave', 'ate', 'empty',
            'capacity', 'rows', 'boxes', 'groups', 'how many',
        )
        has_words = bool(re.search(r'[a-zA-Z]{3,}', text))
        return has_words and any(marker in text for marker in markers)

    async def interpret_if_needed(self, subject: str, message: str) -> StructuredWordProblem:
        if not self.is_candidate(subject, message):
            return StructuredWordProblem(original_text=message)

        deterministic = self._deterministic_parse(message)
        verified = self._validate(message, deterministic)
        if verified.accepted:
            return verified

        proposed = await self._interpret_with_llm(message)
        return self._validate(message, proposed)

    def _deterministic_parse(self, message: str) -> StructuredWordProblem:
        text = self._clean_problem_text(message)
        values = re.findall(NUMBER_TOKEN, text)
        if len(values) < 2:
            return StructuredWordProblem(original_text=message)

        expression = ''
        operation = ''
        asks_for_group_count = self._asks_for_group_count(text)
        asks_for_difference = bool(re.search(r'\bhow (?:many|much) (?:more|fewer|less)\b|\bdifference\b', text))
        inverse_more_relation = bool(re.search(r'\b(?:is|which is)\s+\d+(?:/\d+|\.\d+)?\s+more than\b', text))
        if len(values) == 2 and (asks_for_difference or inverse_more_relation):
            expression, operation = self._positive_difference_expression(values), 'subtraction'
        elif len(values) == 3 and any(word in text for word in ('sold', 'gave away', 'ate ', 'eaten')) and any(word in text for word in ('more', 'baked', 'received', 'added')):
            expression, operation = f'{values[0]} - {values[1]} + {values[2]}', 'subtract_then_add'
        elif len(values) == 2 and (asks_for_group_count or self._has_equal_sharing(text)):
            expression, operation = self._division_expression(text, values), 'division'
        elif len(values) in {2, 3} and ('each' in text or 'every' in text or 'per ' in text or 'capacity' in text):
            if len(values) == 3 and any(word in text for word in ('empty', 'left', 'remain', 'attending', 'used')):
                expression, operation = f'{values[0]} * {values[1]} - {values[2]}', 'multiply_then_subtract'
            elif len(values) == 2:
                expression, operation = f'{values[0]} * {values[1]}', 'multiplication'
        elif len(values) == 2 and any(word in text for word in ('altogether', 'in total', 'total', 'combined', 'more')):
            expression, operation = f'{values[0]} + {values[1]}', 'addition'
        elif len(values) == 2 and any(word in text for word in ('left', 'remain', 'sold', 'gave away', 'ate ', 'eaten', 'empty', 'occupied', 'used')):
            expression, operation = f'{values[0]} - {values[1]}', 'subtraction'

        return StructuredWordProblem(
            original_text=message,
            operation=operation,
            quantities=[WordProblemQuantity(value=value) for value in values],
            expression=expression,
            confidence='high' if expression else 'low',
            source='deterministic',
        )

    async def _interpret_with_llm(self, message: str) -> StructuredWordProblem:
        system = (
            'You structure Grades 3-6 math word problems. Return compact JSON only with keys: '
            'problem_type, operation, quantities, unknown_label, expression, confidence. '
            'quantities is a list of objects with value, label, role. Use only numbers stated by the student. '
            'The expression may use digits, parentheses, +, -, *, and /. Do not calculate the answer. '
            'If the operation is ambiguous, return an empty expression and low confidence.'
        )
        user = f'Student word problem: {message}'
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            return StructuredWordProblem(
                original_text=message,
                problem_type=str(parsed.get('problem_type') or 'word_problem'),
                operation=str(parsed.get('operation') or ''),
                quantities=parsed.get('quantities') or [],
                unknown_label=str(parsed.get('unknown_label') or ''),
                expression=str(parsed.get('expression') or ''),
                confidence=str(parsed.get('confidence') or 'low'),
                source='llm',
            )
        except Exception:
            return StructuredWordProblem(original_text=message)

    def _validate(self, message: str, proposed: StructuredWordProblem) -> StructuredWordProblem:
        expression = re.sub(r'\s+', ' ', str(proposed.expression or '')).strip()
        if proposed.confidence not in {'high', 'medium'} or not expression:
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})
        if re.search(r'[^0-9+\-*/().\s]', expression):
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})

        source_numbers = Counter(self._canonical_numbers(message))
        expression_numbers = Counter(self._canonical_numbers(expression))
        if not expression_numbers or any(count > source_numbers[number] for number, count in expression_numbers.items()):
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})
        if len(expression) > 120 or len(expression_numbers) > 4:
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})
        if not self._operation_matches_text(message, expression):
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})

        value = safe_eval_expression(expression)
        if value is None:
            return proposed.model_copy(update={'validation_status': 'rejected', 'expected_answer': ''})
        return proposed.model_copy(update={
            'expression': expression,
            'expected_answer': format_fraction(value),
            'validation_status': 'verified',
        })

    def _canonical_numbers(self, text: str) -> list[str]:
        values = re.findall(NUMBER_TOKEN, self._clean_problem_text(text))
        canonical: list[str] = []
        for value in values:
            try:
                canonical.append(str(Fraction(value)))
            except Exception:
                continue
        return canonical

    def _clean_problem_text(self, text: str) -> str:
        cleaned = str(text or '').lower()
        cleaned = re.sub(r'\[(?:cite|citation|ref|reference)[^\]]*\]', ' ', cleaned, flags=re.I)
        cleaned = re.sub(r'\bquestion\s+\d+\s*[:.)-]\s*', ' ', cleaned, flags=re.I)
        cleaned = re.sub(r'\bgrade\s+\d+\b', ' ', cleaned, flags=re.I)
        cleaned = normalize_word_numbers_in_text(cleaned)
        return ' '.join(cleaned.split())

    def _operation_matches_text(self, message: str, expression: str) -> bool:
        text = self._clean_problem_text(message)
        compact = expression.replace(' ', '')
        if re.search(r'\bhow (?:many|much) (?:more|fewer|less)\b|\bdifference\b|\b(?:is|which is)\s+\d+(?:/\d+|\.\d+)?\s+more than\b', text):
            return '-' in compact
        if self._asks_for_group_count(text) or self._has_equal_sharing(text):
            return '/' in compact
        if any(marker in text for marker in ('each', 'every', 'per ', 'capacity')):
            return '*' in compact
        if any(marker in text for marker in ('altogether', 'in total', 'total', 'combined')) and not any(marker in text for marker in ('left', 'remain', 'sold', 'gave away')):
            return '+' in compact
        if any(marker in text for marker in ('left', 'remain', 'sold', 'gave away', 'ate ', 'eaten', 'empty', 'occupied', 'used')):
            return '-' in compact
        return True

    def _asks_for_group_count(self, text: str) -> bool:
        return bool(re.search(
            r'\bhow many\s+(?:boxes|bags|groups|rows|teams|baskets|containers|packs|trays)\b',
            text,
        )) and any(marker in text for marker in ('each', 'per ', 'capacity', 'hold', 'fit'))

    def _has_equal_sharing(self, text: str) -> bool:
        direct_markers = ('shared equally', 'divided equally', 'split equally', 'shared among', 'divided among', 'equally among', 'equally into')
        return any(marker in text for marker in direct_markers) or (
            'equally' in text and bool(re.search(r'\b(?:share|shares|shared|split|divide|divides|divided|distribute|distributed)\b', text))
        )

    def _positive_difference_expression(self, values: list[str]) -> str:
        return self._larger_first_expression(values, '-')

    def _division_expression(self, text: str, values: list[str]) -> str:
        group_nouns = r'boxes|bags|groups|rows|teams|baskets|containers|packs|trays|people|children|students'
        per_match = re.search(
            rf'\b(?:each|per)\s+\w+\s+(?:holds?|has|fits?|contains?)?\s*({NUMBER_TOKEN})',
            text,
        )
        per_value = per_match.group(1) if per_match else ''
        if not per_value:
            per_match = re.search(rf'({NUMBER_TOKEN})\s+\w*\s*per\s+\w+', text)
            per_value = per_match.group(1) if per_match else ''
        if not per_value:
            per_match = re.search(rf'\b\w+\s+(?:holds?|fits?|contains?)\s*({NUMBER_TOKEN})', text)
            per_value = per_match.group(1) if per_match else ''
        if per_value in values:
            total_value = next((value for value in values if value != per_value), values[0])
            return f'{total_value} / {per_value}'

        for index, value in enumerate(values):
            if re.search(rf'{re.escape(value)}\s+(?:{group_nouns})\b', text):
                total_value = values[1 - index]
                return f'{total_value} / {value}'
        return f'{values[0]} / {values[1]}'

    def _larger_first_expression(self, values: list[str], operator: str) -> str:
        try:
            left, right = (Fraction(value) for value in values[:2])
            if right > left:
                return f'{values[1]} {operator} {values[0]}'
        except Exception:
            pass
        return f'{values[0]} {operator} {values[1]}'

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', str(text or ''), re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return {}


def apply_word_problem_state(
    previous_state: TutoringState,
    current_state: TutoringState,
    problem: StructuredWordProblem,
) -> TutoringState:
    if not problem.accepted:
        return current_state
    if current_state.ordered_steps and current_state.current_step_id:
        structured = current_state.model_copy(update={
            'problem_kind': 'word_problem',
            'word_problem_schema': problem.model_dump(),
            'full_problem': problem.original_text,
        })
        return transition_to_task(
            previous_state,
            structured,
            problem.original_text,
            subject='Math',
            source='structured_word_problem',
            previous='pause',
        )
    display = _display_expression(problem)
    next_state = current_state.model_copy(update={
        'problem_kind': 'word_problem',
        'word_problem_schema': problem.model_dump(),
        'main_problem': problem.original_text,
        'full_problem': problem.original_text,
        'active_problem': problem.original_text,
        'current_expression': problem.expression,
        'current_step': problem.expression,
        'current_question': f'What is {display}?',
        'expected_answer': problem.expected_answer,
        'skill': problem.operation,
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'problem_status': 'awaiting_step',
        'mode': 'practice',
        'status': 'waiting_for_student',
    })
    return transition_to_task(
        previous_state,
        next_state,
        problem.original_text,
        subject='Math',
        source='structured_word_problem',
        previous='pause',
    )


def build_word_problem_start_reply(problem: StructuredWordProblem) -> str:
    display = _display_expression(problem)
    operation = problem.operation.replace('_', ' ')
    return (
        'Let’s turn the words into math first.\n\n'
        f'**Plan:** This is a {operation} problem.\n'
        f'**Math sentence:** {display}\n\n'
        f'What is {display}?'
    )


def build_word_problem_clarification_reply() -> str:
    return (
        'I can see this is a Math word problem, but I am not certain which quantities should be combined.\n\n'
        'Can you tell me what the question asks us to find—for example, the **total**, the amount **left**, '
        'the number in **each group**, or the number of **groups**?'
    )


def _display_expression(problem: StructuredWordProblem) -> str:
    display = problem.expression.replace('*', '×')
    if problem.operation == 'division' and re.fullmatch(r'\s*-?\d+(?:\.\d+)?\s*/\s*-?\d+(?:\.\d+)?\s*', display):
        display = display.replace('/', '÷')
    return display
