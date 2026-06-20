import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import TutoringState

MATH_TOKEN_MULTIPLY = re.compile(r'(?<=[\d\)\]a-zA-Z])\s*(?<!\*)\*(?!\*)\s*(?=[\d\(a-zA-Z])')
INTEGER_DIVISION = re.compile(r'\b(\d+)\s+/\s+(\d+)\b')
NUMBER_MINUS_NUMBER = re.compile(r'(\d)\s*-\s*(\d)')
NUMBER_TIMES_NUMBER = re.compile(r'(\d)\s*[xX]\s*(\d)')
INCOMPLETE_ENDINGS = ('now', 'so', 'because', 'then', 'next')


def format_contextual_math_answer(state: 'TutoringState', value: str) -> str:
    """Attach verified word-problem context without changing numeric checking."""
    clean_value = str(value or '').strip()
    label = ' '.join(str(state.answer_label or state.answer_unit or '').strip().split())
    if not clean_value or not label or state.problem_kind != 'word_problem':
        return clean_value
    if label.lower() in clean_value.lower():
        return clean_value
    return f'{clean_value} {label}'


def ensure_contextual_final_answer(text: str, state: 'TutoringState') -> str:
    """Repair a final-answer label composed without the verified word context."""
    if state.problem_kind != 'word_problem' or not state.expected_answer:
        return text
    contextual = format_contextual_math_answer(state, state.expected_answer)
    if contextual == state.expected_answer:
        return text
    label = ' '.join(str(state.answer_label or state.answer_unit or '').strip().split())
    label_guard = rf'(?!\s+{re.escape(label)})' if label else ''
    pattern = rf'(\*\*Final answer:\*\*|Final answer:)\s*{re.escape(state.expected_answer)}\b{label_guard}'
    return re.sub(pattern, lambda match: f'{match.group(1)} {contextual}', text, flags=re.I)


def contextual_unit_feedback(state: 'TutoringState', student_answer: str) -> str:
    """Return a gentle correction when the numeric answer is right but the unit is contradictory."""
    if state.problem_kind != 'word_problem':
        return ''
    expected_label = ' '.join(str(state.answer_label or '').strip().split())
    expected_unit = ' '.join(str(state.answer_unit or '').strip().split())
    expected_context = expected_label or expected_unit
    if not expected_context:
        return ''

    student_unit = _student_answer_unit(student_answer)
    if not student_unit:
        return ''
    if _unit_matches_expected(student_unit, expected_label, expected_unit):
        return ''
    return f'The number is right, but the unit should be **{expected_context}**, not **{student_unit}**.'


def _student_answer_unit(student_answer: str) -> str:
    text = str(student_answer or '').lower()
    match = re.search(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?\s+([a-z][a-z\s-]{1,40})', text)
    if not match:
        return ''
    unit_text = match.group(1)
    unit_text = re.split(r'[.!?,;:]|\b(?:because|since|and then|so|is|are|were|was)\b', unit_text, maxsplit=1)[0]
    unit_tokens = [
        _singularize_unit_token(token)
        for token in re.findall(r'[a-z]+', unit_text)
        if token not in {'the', 'a', 'an', 'answer', 'is', 'equals', 'equal', 'total'}
    ]
    return ' '.join(unit_tokens).strip()


def _unit_matches_expected(student_unit: str, expected_label: str, expected_unit: str) -> bool:
    student_tokens = set(_unit_tokens(student_unit))
    expected_tokens = set(_unit_tokens(expected_label)) | set(_unit_tokens(expected_unit))
    if not student_tokens or not expected_tokens:
        return True
    return bool(student_tokens & expected_tokens)


def _unit_tokens(text: str) -> list[str]:
    return [_singularize_unit_token(token) for token in re.findall(r'[a-z]+', str(text or '').lower())]


def _singularize_unit_token(token: str) -> str:
    if token.endswith('ies') and len(token) > 3:
        return f'{token[:-3]}y'
    if token.endswith('es') and len(token) > 3:
        return token[:-2]
    if token.endswith('s') and len(token) > 2:
        return token[:-1]
    return token


def format_student_reply(text: str) -> str:
    formatted = text.replace('\r\n', '\n').replace('\r', '\n')
    formatted = re.sub(r'[ \t]+', ' ', formatted)
    formatted = re.sub(r'\n{3,}', '\n\n', formatted).strip()

    formatted = MATH_TOKEN_MULTIPLY.sub(' × ', formatted)
    formatted = NUMBER_TIMES_NUMBER.sub(r'\1 × \2', formatted)
    formatted = re.sub(r'(\d)\s*×\s*(\d)', r'\1 × \2', formatted)
    formatted = INTEGER_DIVISION.sub(r'\1 ÷ \2', formatted)
    formatted = NUMBER_MINUS_NUMBER.sub(r'\1 − \2', formatted)
    formatted = re.sub(r'\s+=\s+', ' = ', formatted)
    formatted = re.sub(r'[ \t]{2,}', ' ', formatted)

    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', formatted) if part.strip()]
    if len(paragraphs) == 1:
        sentences = [part.strip() for part in re.split(r'(?<=[.!?])\s+', paragraphs[0]) if part.strip()]
        if len(sentences) > 5:
            if '?' in sentences[-1]:
                sentences = sentences[:4] + [sentences[-1]]
            else:
                sentences = sentences[:5]
        return '\n\n'.join(sentences)

    return '\n\n'.join(paragraphs[:5])


def looks_incomplete_response(text: str, student_message: str = '') -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    normalized = cleaned.lower().rstrip()
    if cleaned.count('**') % 2 != 0:
        return True
    if cleaned.endswith(':') or cleaned.endswith('('):
        return True
    if normalized.endswith(INCOMPLETE_ENDINGS):
        return True
    if re.search(r'(?:^|\n)\s*\*?\*?step\s+\d+\s*:?\*?\*?\s*$', cleaned, re.I):
        return True
    if re.search(r'(?:^|\n)\s*(?:now|so|because)\s*$', cleaned, re.I):
        return True
    if is_direct_calculation_question(student_message) and not has_calculation_answer(cleaned):
        return True
    return False


def is_direct_calculation_question(message: str) -> bool:
    text = message.strip().lower()
    if not re.search(r'\d', text):
        return False
    has_operator = any(symbol in text for symbol in ['+', '-', '*', '/', '×', '÷', '='])
    has_math_word = any(word in text for word in ['what is', 'solve', 'calculate', 'answer', 'add', 'subtract', 'multiply', 'divide'])
    return has_operator or has_math_word


def has_calculation_answer(text: str) -> bool:
    normalized = text.lower()
    if 'final answer' in normalized:
        return True
    return False
