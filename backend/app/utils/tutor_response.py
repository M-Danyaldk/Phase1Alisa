import re

MATH_TOKEN_MULTIPLY = re.compile(r'(?<=[\d\)\]a-zA-Z])\s*(?<!\*)\*(?!\*)\s*(?=[\d\(a-zA-Z])')
INTEGER_DIVISION = re.compile(r'\b(\d+)\s+/\s+(\d+)\b')
NUMBER_MINUS_NUMBER = re.compile(r'(\d)\s*-\s*(\d)')
NUMBER_TIMES_NUMBER = re.compile(r'(\d)\s*[xX]\s*(\d)')
INCOMPLETE_ENDINGS = ('now', 'so', 'because', 'then', 'next')


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
