import ast
import operator
import re
from dataclasses import dataclass
from fractions import Fraction

from .assessment_bank import AssessmentQuestion, NUMBER_WORDS


@dataclass(frozen=True)
class AnswerValidationResult:
    question_id: str
    status: str
    validation_type: str
    expected_answer: str
    student_answer: str
    normalized_student_answer: str
    confidence: str
    feedback_note: str = ''

    @property
    def is_correct(self) -> bool:
        return self.status == 'correct'


WORD_NUMBERS = {value: key for key, value in NUMBER_WORDS.items()}
STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'to', 'of', 'and', 'in', 'it', 'this', 'that',
    'with', 'for', 'from', 'what', 'does', 'mean', 'main', 'idea',
}


def validate_assessment_answer(question: AssessmentQuestion, student_answer: str) -> AnswerValidationResult:
    answer = str(student_answer or '').strip()
    if not answer:
        return _result(question, answer, 'incorrect', 'high', 'No answer was provided.')

    normalized = normalize_answer_text(answer)
    accepted = {normalize_answer_text(item) for item in question.accepted_answers if str(item).strip()}
    if normalized in accepted:
        return _result(question, answer, 'correct', 'high', 'Matched an accepted answer.')

    validation_type = question.validation_type
    if validation_type in {'numeric', 'numeric_or_fraction'}:
        return _validate_numeric(question, answer)
    if validation_type == 'exact_text':
        return _validate_exact_text(question, answer)
    if validation_type == 'keyword_text':
        return _validate_keyword_text(question, answer)
    if validation_type == 'writing_rubric':
        return _validate_writing_minimum(question, answer)
    return _result(question, answer, 'needs_review', 'low', f'Unsupported validation type: {validation_type}')


def validate_answers(
    questions: tuple[AssessmentQuestion, ...] | list[AssessmentQuestion],
    answers: list[str] | tuple[str, ...],
) -> tuple[AnswerValidationResult, ...]:
    return tuple(
        validate_assessment_answer(question, answers[index] if index < len(answers) else '')
        for index, question in enumerate(questions)
    )


def extract_numeric_value(text: str) -> Fraction | None:
    normalized = normalize_math_text(text)
    word_value = _number_word_value(normalized)
    if word_value is not None:
        return Fraction(word_value, 1)

    expression = extract_math_expression(normalized)
    if expression:
        value = safe_eval_expression(expression)
        if value is not None:
            return value

    mixed = re.search(r'(-?\d+)\s+(\d+)\s*/\s*(\d+)', normalized)
    if mixed:
        whole = int(mixed.group(1))
        numerator = int(mixed.group(2))
        denominator = int(mixed.group(3))
        if denominator == 0:
            return None
        sign = -1 if whole < 0 else 1
        return Fraction(whole, 1) + sign * Fraction(numerator, denominator)

    fraction = re.search(r'-?\d+\s*/\s*-?\d+', normalized)
    if fraction:
        try:
            return Fraction(fraction.group(0).replace(' ', ''))
        except ZeroDivisionError:
            return None

    decimal = re.search(r'-?\d+(?:\.\d+)?', normalized)
    if decimal:
        return Fraction(decimal.group(0))
    return None


def extract_math_expression(text: str) -> str:
    normalized = normalize_math_text(text)
    candidates = re.findall(r'[\d\s\+\-\*/\(\)\.]+', normalized)
    candidates = [
        candidate.strip()
        for candidate in candidates
        if any(op in candidate for op in ['+', '-', '*', '/'])
    ]
    return max(candidates, key=len) if candidates else ''


def normalize_math_text(text: str) -> str:
    normalized = str(text or '').lower()
    replacements = {
        '\u00d7': '*',
        '\u00f7': '/',
        '\u2212': '-',
        'Ã—': '*',
        'Ãƒâ€”': '*',
        'Ã·': '/',
        'ÃƒÂ·': '/',
        'âˆ’': '-',
        'Ã¢Ë†â€™': '-',
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r'(?<=\d)\s*x\s*(?=\d)', ' * ', normalized)
    return normalized


def safe_eval_expression(expression: str) -> Fraction | None:
    try:
        tree = ast.parse(expression, mode='eval')
        return _eval_node(tree.body)
    except Exception:
        return None


def format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f'{value.numerator}/{value.denominator}'


def normalize_answer_text(text: str) -> str:
    normalized = str(text or '').strip().lower()
    normalized = normalized.replace('\u2019', "'").replace('\u2018', "'")
    normalized = normalized.replace('\u201c', '"').replace('\u201d', '"')
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'[.!?]+$', '', normalized)
    return normalized.strip()


def keyword_set(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r'[a-zA-Z]+', normalize_answer_text(text))
        if word not in STOP_WORDS and len(word) > 2
    }


def _validate_numeric(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    expected_value = extract_numeric_value(question.expected_answer)
    student_value = extract_numeric_value(answer)
    if expected_value is None or student_value is None:
        return _result(question, answer, 'needs_review', 'low', 'Could not parse one of the numeric answers safely.')
    if expected_value == student_value:
        return _result(question, answer, 'correct', 'high', f'Numeric answer matches {format_fraction(expected_value)}.')
    return _result(question, answer, 'incorrect', 'high', f'Expected {format_fraction(expected_value)}.')


def _validate_exact_text(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    normalized = normalize_answer_text(answer)
    expected_options = {normalize_answer_text(question.expected_answer)}
    expected_options.update(normalize_answer_text(item) for item in question.accepted_answers)
    if normalized in expected_options:
        return _result(question, answer, 'correct', 'high', 'Text matches the expected correction.')

    student_words = keyword_set(answer)
    expected_words = keyword_set(question.expected_answer)
    if expected_words and len(student_words & expected_words) / len(expected_words) >= 0.7:
        return _result(question, answer, 'partially_correct', 'medium', 'Text includes most expected words but differs from the target correction.')
    return _result(question, answer, 'incorrect', 'high', 'Text does not match the expected correction.')


def _validate_keyword_text(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    student_words = keyword_set(answer)
    expected_sets = [keyword_set(question.expected_answer)]
    expected_sets.extend(keyword_set(item) for item in question.accepted_answers)
    expected_sets = [items for items in expected_sets if items]
    if not expected_sets:
        return _result(question, answer, 'needs_review', 'low', 'No keyword target is available.')

    best_overlap = max(len(student_words & expected_words) / len(expected_words) for expected_words in expected_sets)
    if best_overlap >= 0.7:
        return _result(question, answer, 'correct', 'medium', 'Answer includes the expected idea.')
    if best_overlap >= 0.35:
        return _result(question, answer, 'partially_correct', 'medium', 'Answer includes part of the expected idea.')
    return _result(question, answer, 'incorrect', 'medium', 'Answer does not include the expected idea.')


def _validate_writing_minimum(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    words = re.findall(r"[A-Za-z0-9']+", answer)
    sentence_count = _sentence_count(answer)
    has_ending_punctuation = bool(re.search(r'[.!?]\s*$', answer.strip()))

    if len(words) < 4:
        return _result(question, answer, 'incorrect', 'high', 'Writing answer is too short to assess.')

    if question.position == 2:
        if sentence_count >= 3 and len(words) >= 15:
            return _result(question, answer, 'needs_review', 'medium', 'Meets the three-sentence minimum and is ready for rubric review.')
        if sentence_count >= 2 and len(words) >= 10:
            return _result(question, answer, 'partially_correct', 'medium', 'Includes some explanation but not the full three-sentence target.')
        return _result(question, answer, 'incorrect', 'high', 'Does not meet the three-sentence writing target.')

    if has_ending_punctuation and len(words) >= 6:
        return _result(question, answer, 'needs_review', 'medium', 'Meets the basic writing minimum and is ready for rubric review.')
    if len(words) >= 5:
        return _result(question, answer, 'partially_correct', 'medium', 'Has enough words but may need sentence punctuation or detail.')
    return _result(question, answer, 'incorrect', 'high', 'Does not meet the basic writing target.')


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r'[.!?]+', text) if part.strip()])


def _result(
    question: AssessmentQuestion,
    answer: str,
    status: str,
    confidence: str,
    note: str,
) -> AnswerValidationResult:
    return AnswerValidationResult(
        question_id=question.id,
        status=status,
        validation_type=question.validation_type,
        expected_answer=question.expected_answer,
        student_answer=answer,
        normalized_student_answer=normalize_answer_text(answer),
        confidence=confidence,
        feedback_note=note,
    )


def _number_word_value(text: str) -> int | None:
    normalized = normalize_answer_text(text).replace('-', ' ')
    if normalized in WORD_NUMBERS:
        return WORD_NUMBERS[normalized]
    if normalized.endswith(' days') and normalized[:-5] in WORD_NUMBERS:
        return WORD_NUMBERS[normalized[:-5]]
    return None


def _eval_node(node: ast.AST) -> Fraction:
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in operators:
        return operators[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    raise ValueError('Unsupported math expression')
