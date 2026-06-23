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
SIMPLE_NUMBER_WORDS = {
    'zero': 0,
    'one': 1,
    'two': 2,
    'three': 3,
    'four': 4,
    'five': 5,
    'six': 6,
    'seven': 7,
    'eight': 8,
    'nine': 9,
    'ten': 10,
    'eleven': 11,
    'twelve': 12,
    'thirteen': 13,
    'fourteen': 14,
    'fifteen': 15,
    'sixteen': 16,
    'seventeen': 17,
    'eighteen': 18,
    'nineteen': 19,
    'twenty': 20,
    'thirty': 30,
    'forty': 40,
    'fifty': 50,
    'sixty': 60,
    'seventy': 70,
    'eighty': 80,
    'ninety': 90,
}
NUMBER_CONNECTOR_WORDS = {'and'}
NUMBER_SCALE_WORDS = {'hundred': 100}
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
    normalized = re.sub(r'(?<=\d)\s*x\s*(?=\d|\()', ' * ', normalized)
    normalized = re.sub(r'(?<=\))\s*x\s*(?=\d|\()', ' * ', normalized)
    normalized = re.sub(r'(?<=\d)[ \t]*\?[ \t]*(?=\d|\()', ' * ', normalized)
    normalized = re.sub(r'(?<=\))[ \t]*\?[ \t]*(?=\d|\()', ' * ', normalized)
    normalized = re.sub(r'(?<=[\d)])\s*(?=\()', ' * ', normalized)
    normalized = re.sub(r'(?<=\))\s*(?=\d)', ' * ', normalized)
    return normalized


def normalize_word_numbers_in_text(text: str) -> str:
    tokens = re.findall(r'[a-z]+(?:-[a-z]+)?|\d+|[^\w\s]|\s+', str(text or '').lower())
    if not tokens:
        return ''

    result: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not re.fullmatch(r'[a-z]+(?:-[a-z]+)?', token):
            result.append(token)
            index += 1
            continue

        value, consumed = _parse_number_word_tokens(tokens, index)
        if consumed > 0:
            result.append(str(value))
            index += consumed
            continue

        result.append(token)
        index += 1

    return ''.join(result)


def safe_eval_expression(expression: str) -> Fraction | None:
    try:
        prepared = _prepare_fraction_expression(expression)
        tree = ast.parse(prepared, mode='eval')
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
    if question.skill == 'fraction comparison':
        comparison_note = _fraction_comparison_feedback(question.question, question.expected_answer)
        if comparison_note:
            return _result(question, answer, 'incorrect', 'high', comparison_note)
    return _result(question, answer, 'incorrect', 'high', f'Expected {format_fraction(expected_value)}.')


def _fraction_comparison_feedback(question_text: str, expected_answer: str) -> str:
    fractions = re.findall(r'-?\d+\s*/\s*-?\d+', str(question_text or ''))
    if len(fractions) < 2:
        return ''
    values: list[tuple[str, Fraction]] = []
    for fraction_text in fractions[:2]:
        try:
            values.append((fraction_text.replace(' ', ''), Fraction(fraction_text.replace(' ', ''))))
        except ZeroDivisionError:
            return ''
    if len(values) < 2:
        return ''
    left, right = values
    expected_display = str(expected_answer or '').strip() or format_fraction(max(left[1], right[1]))
    return (
        f'{expected_display} is larger because '
        f'{left[0]} = {_decimal_label(left[1])} and {right[0]} = {_decimal_label(right[1])}.'
    )


def _decimal_label(value: Fraction) -> str:
    decimal = value.numerator / value.denominator
    return f'{decimal:.3f}'.rstrip('0').rstrip('.')


def _validate_exact_text(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    normalized = normalize_answer_text(answer)
    canonical = _canonical_text(normalized)
    expected_options = {normalize_answer_text(question.expected_answer)}
    expected_options.update(normalize_answer_text(item) for item in question.accepted_answers)
    canonical_options = {_canonical_text(item) for item in expected_options}
    if normalized in expected_options or canonical in canonical_options:
        return _result(question, answer, 'correct', 'high', 'Text matches the expected correction.')

    student_words = keyword_set(answer)
    expected_words = keyword_set(question.expected_answer)
    if expected_words and len(student_words & expected_words) / len(expected_words) >= 0.7:
        return _result(question, answer, 'partially_correct', 'medium', 'Text includes most expected words but differs from the target correction.')
    return _result(question, answer, 'incorrect', 'high', 'Text does not match the expected correction.')


def _validate_keyword_text(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    prompt_validation = _validate_reading_prompt_keywords(question, answer)
    if prompt_validation is not None:
        return prompt_validation

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


def _validate_reading_prompt_keywords(question: AssessmentQuestion, answer: str) -> AnswerValidationResult | None:
    prompt = normalize_answer_text(question.question)
    if question.subject != 'ELA':
        return None

    if prompt.startswith('read this short passage:') and 'what is the main idea' in prompt:
        return _validate_main_idea_response(question, answer)

    if prompt.startswith('read this short passage:') and 'what can you infer about' in prompt:
        return _validate_inference_response(question, answer)

    return None


def _validate_main_idea_response(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    student_words = keyword_set(answer)
    if not student_words:
        return _result(question, answer, 'incorrect', 'high', 'Answer does not yet explain the main idea.')

    helpful_words = {'helpful', 'kind', 'good', 'careful', 'responsible', 'smart', 'thoughtful'}
    better_words = {
        'better', 'healthy', 'welcome', 'cleaner', 'clearer', 'improved', 'easier', 'possible',
        'neat', 'ready', 'organized', 'stronger', 'safer', 'helped',
    }
    action_words = {'action', 'thing', 'step', 'choice', 'help', 'helped', 'did', 'made'}

    has_helpful_idea = bool(student_words & helpful_words)
    has_better_outcome = bool(student_words & better_words)
    has_summary_shape = bool(student_words & action_words)

    if (has_helpful_idea and has_better_outcome) or normalize_answer_text(answer) in {
        normalize_answer_text(item) for item in (question.expected_answer, *question.accepted_answers)
    }:
        return _result(question, answer, 'correct', 'high', 'Answer explains that a helpful action improved the situation.')

    if has_better_outcome or has_helpful_idea or has_summary_shape:
        return _result(question, answer, 'partially_correct', 'medium', 'Answer notices part of the passage, but the main idea is not fully stated yet.')

    return _result(question, answer, 'incorrect', 'high', 'Answer does not yet explain the main idea of the passage.')


def _validate_inference_response(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    student_words = keyword_set(answer)
    if not student_words:
        return _result(question, answer, 'incorrect', 'high', 'Answer does not yet explain the inference.')

    responsibility_words = {'responsible', 'careful', 'prepared', 'organized', 'thoughtful', 'reliable'}
    strategy_words = {'strategy', 'plan', 'smart', 'helpful', 'carefully', 'useful', 'good', 'planning'}
    positive_trait_words = {'helpful', 'kind', 'smart', 'careful', 'responsible', 'thoughtful'}

    has_trait = bool(student_words & responsibility_words)
    has_strategy = bool(student_words & strategy_words)
    has_positive_trait = bool(student_words & positive_trait_words)

    if (has_trait and has_strategy) or normalize_answer_text(answer) in {
        normalize_answer_text(item) for item in (question.expected_answer, *question.accepted_answers)
    }:
        return _result(question, answer, 'correct', 'high', 'Answer gives a supported inference about the student.')

    if has_trait or has_strategy or has_positive_trait:
        return _result(question, answer, 'partially_correct', 'medium', 'Answer gives part of the inference, but it needs a clearer supported idea.')

    return _result(question, answer, 'incorrect', 'high', 'Answer does not yet give a supported inference from the passage.')


def _validate_writing_minimum(question: AssessmentQuestion, answer: str) -> AnswerValidationResult:
    words = re.findall(r"[A-Za-z0-9']+", answer)
    sentence_count = _sentence_count(answer)
    has_ending_punctuation = bool(re.search(r'[.!?]\s*$', answer.strip()))
    starts_with_capital = bool(re.match(r'^\s*[A-Z]', answer))
    prompt = normalize_answer_text(question.question)
    unique_ratio = _unique_word_ratio(words)
    repeated = _has_heavy_repetition(words)

    if len(words) < 4:
        return _result(question, answer, 'incorrect', 'high', 'Writing answer is too short to assess.')

    if question.skill == 'complete sentence' or prompt.startswith('write one clear sentence'):
        if repeated:
            return _result(question, answer, 'incorrect', 'high', 'The sentence repeats too much and does not clearly express one idea.')
        topic_words = _prompt_topic_words(question.question)
        on_topic = _shares_topic_language(answer, topic_words)
        if sentence_count >= 1 and len(words) >= 6 and has_ending_punctuation and starts_with_capital and not repeated:
            return _result(question, answer, 'correct', 'high', 'Wrote one complete sentence with a capital letter and ending punctuation.')
        if sentence_count >= 1 and len(words) >= 5 and (on_topic or has_ending_punctuation or starts_with_capital):
            return _result(question, answer, 'partially_correct', 'medium', 'The idea is started, but the sentence needs stronger conventions or clearer wording.')
        return _result(question, answer, 'incorrect', 'high', 'Does not yet form one clear complete sentence.')

    if question.skill == 'explanatory writing' or prompt.startswith('write 3 sentences'):
        explanation_markers = {'because', 'so', 'this', 'helps', 'matters', 'builds', 'shows'}
        answer_words = {word.lower() for word in words}
        has_reason_language = bool(answer_words & explanation_markers)
        topic_words = _prompt_topic_words(question.question)
        on_topic = _shares_topic_language(answer, topic_words)
        strong_variety = unique_ratio >= 0.55
        if repeated:
            return _result(question, answer, 'incorrect', 'high', 'The writing repeats the same idea instead of explaining it clearly.')
        if sentence_count >= 3 and len(words) >= 15 and has_reason_language and strong_variety and not repeated:
            return _result(question, answer, 'correct', 'high', 'Includes three explanatory sentences with a clear reason.')
        if sentence_count >= 2 and len(words) >= 8 and (has_reason_language or on_topic):
            return _result(question, answer, 'partially_correct', 'medium', 'Includes some explanation but not the full three-sentence target.')
        return _result(question, answer, 'incorrect', 'high', 'Does not yet meet the three-sentence explanatory writing target.')

    if question.skill == 'revision for detail' or prompt.startswith('how can you make this sentence stronger'):
        original_sentence = _revision_source_sentence(question.question)
        original_words = keyword_set(original_sentence)
        student_words = keyword_set(answer)
        added_words = student_words - original_words
        vivid_words = _descriptive_word_count(answer)
        if repeated:
            return _result(question, answer, 'incorrect', 'high', 'The revision repeats the same weak wording and needs clearer detail.')
        if (
            sentence_count >= 1
            and len(words) >= 6
            and has_ending_punctuation
            and starts_with_capital
            and original_words
            and student_words & original_words
            and len(added_words) >= 2
            and vivid_words >= 1
        ):
            return _result(question, answer, 'correct', 'medium', 'Revised the sentence with added detail or stronger word choice.')
        if sentence_count >= 1 and len(words) >= 3 and (added_words or student_words & original_words):
            return _result(question, answer, 'partially_correct', 'medium', 'Attempts a stronger sentence, but it needs more specific detail or clearer revision.')
        return _result(question, answer, 'incorrect', 'high', 'Does not yet revise the sentence into a stronger complete sentence.')

    if has_ending_punctuation and len(words) >= 6:
        return _result(question, answer, 'correct', 'medium', 'Meets the basic writing minimum.')
    if len(words) >= 5:
        return _result(question, answer, 'partially_correct', 'medium', 'Has enough words but may need sentence punctuation or detail.')
    return _result(question, answer, 'incorrect', 'high', 'Does not meet the basic writing target.')


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r'[.!?]+', text) if part.strip()])


def _unique_word_ratio(words: list[str]) -> float:
    if not words:
        return 0.0
    normalized = [word.lower() for word in words]
    return len(set(normalized)) / max(len(normalized), 1)


def _has_heavy_repetition(words: list[str]) -> bool:
    if len(words) < 5:
        return False
    normalized = [word.lower() for word in words]
    counts: dict[str, int] = {}
    for word in normalized:
        counts[word] = counts.get(word, 0) + 1
    return max(counts.values(), default=0) >= 3 and _unique_word_ratio(words) < 0.5


def _prompt_topic_words(question_text: str) -> set[str]:
    text = normalize_answer_text(question_text)
    prefixes = (
        'write one clear sentence about ',
        'write 3 sentences that explain why ',
        'write three sentences that explain why ',
    )
    topic = text
    for prefix in prefixes:
        if text.startswith(prefix):
            topic = text[len(prefix):]
            break
    return {
        word
        for word in re.findall(r'[a-zA-Z]+', topic)
        if word not in STOP_WORDS and len(word) > 3
    }


def _shares_topic_language(answer: str, topic_words: set[str]) -> bool:
    if not topic_words:
        return True
    student_words = keyword_set(answer)
    if student_words & topic_words:
        return True
    synonym_groups = {
        'practice': {'practice', 'improve', 'better', 'skill', 'learn', 'training'},
        'skills': {'skill', 'skills', 'improve', 'practice', 'learn'},
        'matters': {'matters', 'important', 'helps', 'useful'},
        'reading': {'reading', 'read', 'books', 'story', 'learn'},
        'teamwork': {'teamwork', 'team', 'together', 'group', 'help'},
    }
    for topic in topic_words:
        group = synonym_groups.get(topic, {topic})
        if student_words & group:
            return True
    return False


def _descriptive_word_count(answer: str) -> int:
    descriptive_words = {
        'clear', 'careful', 'helpful', 'strong', 'stronger', 'specific', 'detailed', 'interesting',
        'bright', 'kind', 'fun', 'exciting', 'colorful', 'quick', 'smart', 'thoughtful',
    }
    return len(keyword_set(answer) & descriptive_words)


def _revision_source_sentence(question_text: str) -> str:
    match = re.search(r'stronger:\s*(.+)$', str(question_text or ''), re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    return ''


def _canonical_text(text: str) -> str:
    canonical = normalize_answer_text(text)
    replacements = {
        "doesn't": 'does not',
        "don't": 'do not',
        "isn't": 'is not',
        "aren't": 'are not',
        "wasn't": 'was not',
        "weren't": 'were not',
        "can't": 'cannot',
        "won't": 'will not',
        "didn't": 'did not',
        "hasn't": 'has not',
        "haven't": 'have not',
        "hadn't": 'had not',
        "it's": 'it is',
        "that's": 'that is',
    }
    for source, target in replacements.items():
        canonical = canonical.replace(source, target)
    canonical = re.sub(r'\s+', ' ', canonical).strip()
    return canonical


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
    normalized = normalize_answer_text(text)
    normalized = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', normalized)
    sign = 1
    sign_match = re.match(r'^(?:negative|minus)\s+', normalized)
    if sign_match:
        sign = -1
        normalized = normalized[sign_match.end():].strip()
    if normalized in WORD_NUMBERS:
        return sign * WORD_NUMBERS[normalized]
    if normalized.endswith(' days') and normalized[:-5] in WORD_NUMBERS:
        return sign * WORD_NUMBERS[normalized[:-5]]
    if normalized.endswith(' days'):
        converted_days = normalize_word_numbers_in_text(normalized[:-5]).strip()
        if re.fullmatch(r'-?\d+', converted_days):
            return sign * int(converted_days)
    converted = normalize_word_numbers_in_text(normalized).strip()
    if re.fullmatch(r'-?\d+', converted):
        return sign * int(converted)
    return None


def _parse_number_word_tokens(tokens: list[str], start: int) -> tuple[int, int]:
    total = 0
    current = 0
    consumed = 0
    saw_number = False
    index = start

    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r'\s+', token):
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ''
            if re.fullmatch(r'[a-z]+(?:-[a-z]+)?', next_token) and _is_number_word_piece(next_token):
                consumed += 1
                index += 1
                continue
            break
        if not re.fullmatch(r'[a-z]+(?:-[a-z]+)?', token):
            break

        parts = token.split('-')
        piece_consumed = False
        for part in parts:
            if part in SIMPLE_NUMBER_WORDS:
                current += SIMPLE_NUMBER_WORDS[part]
                saw_number = True
                piece_consumed = True
            elif part in NUMBER_SCALE_WORDS and saw_number:
                current *= NUMBER_SCALE_WORDS[part]
                piece_consumed = True
            elif part in NUMBER_CONNECTOR_WORDS and saw_number:
                piece_consumed = True
            else:
                if not saw_number:
                    return 0, 0
                total += current
                return total, consumed

        if not piece_consumed:
            break

        consumed += 1
        index += 1

    if not saw_number:
        return 0, 0
    return total + current, consumed


def _is_number_word_piece(token: str) -> bool:
    parts = token.split('-')
    return all(part in SIMPLE_NUMBER_WORDS or part in NUMBER_SCALE_WORDS or part in NUMBER_CONNECTOR_WORDS for part in parts)


def _prepare_fraction_expression(expression: str) -> str:
    text = str(expression or '')
    return re.sub(r'(?<![\d)])(-?\d+\s*/\s*-?\d+)(?![\d(])', r'(\1)', text)


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
