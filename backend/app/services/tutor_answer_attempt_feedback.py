from __future__ import annotations

import re

from pydantic import BaseModel

from ..models import TutoringState
from .tutor_question_type_router import infer_active_question_type


class AnswerAttemptFeedback(BaseModel):
    question_type: str = ''
    answer_format: str = 'valid'
    counts_as_attempt: bool = True
    prefix: str = ''


def build_attempt_feedback(state: TutoringState, student_answer: str) -> AnswerAttemptFeedback:
    question_type = infer_active_question_type(state)
    answer = ' '.join(str(student_answer or '').strip().split())
    expected = ' '.join(str(state.expected_answer or '').strip().split())
    display_answer = _display_answer(answer)

    if not answer:
        return AnswerAttemptFeedback(question_type=question_type, counts_as_attempt=False, answer_format='empty')

    if question_type == 'fraction_comparison':
        choices = _extract_comparison_choices(state)
        if choices:
            normalized_choices = {_normalize_choice(choice): choice for choice in choices}
            normalized_answer = _normalize_choice(answer)
            if normalized_answer in normalized_choices:
                chosen = normalized_choices[normalized_answer]
                return AnswerAttemptFeedback(
                    question_type=question_type,
                    answer_format='valid_choice',
                    prefix=f'Good try. {chosen} is one of the choices, but it is not the larger value here.',
                )
            return AnswerAttemptFeedback(
                question_type=question_type,
                answer_format='invalid_shape',
                prefix=f'Good try. This question asks which value is larger, so answer with one of the choices: {choices[0]} or {choices[1]}.',
            )

    if question_type == 'equivalent_fraction':
        choices = _extract_comparison_choices(state)
        if _looks_like_fraction(answer):
            if choices:
                normalized_choices = {_normalize_choice(choice): choice for choice in choices}
                normalized_answer = _normalize_choice(answer)
                if normalized_answer in normalized_choices:
                    chosen = normalized_choices[normalized_answer]
                    return AnswerAttemptFeedback(
                        question_type=question_type,
                        answer_format='valid_choice',
                        prefix=f'Good try. {chosen} is one of the choices, but it is not the equivalent fraction here.',
                    )
            return AnswerAttemptFeedback(
                question_type=question_type,
                answer_format='valid',
                prefix=(f'Good try. {display_answer} is not the equivalent fraction for this question.' if display_answer else 'Good try. That fraction is not equivalent here.'),
            )
        return AnswerAttemptFeedback(
            question_type=question_type,
            answer_format='invalid_shape',
            prefix='Good try. This question needs a fraction as the answer.',
        )

    if expected.lower() in {'yes', 'no'}:
        if answer.lower() not in {'yes', 'no', 'y', 'n', 'yeah', 'yep', 'nope'}:
            return AnswerAttemptFeedback(
                question_type=question_type,
                answer_format='invalid_shape',
                prefix='Good try. This question needs a yes-or-no answer.',
            )
        return AnswerAttemptFeedback(
            question_type=question_type,
            answer_format='valid',
            prefix=(f'Good try. {display_answer} is not the right answer here.' if display_answer else 'Good try. That is not the right answer here.'),
        )

    if _looks_like_fraction(expected) and not _looks_like_fraction(answer):
        return AnswerAttemptFeedback(
            question_type=question_type,
            answer_format='invalid_shape',
            prefix='Good try. Write your answer as a fraction for this question.',
        )

    if _looks_numeric(expected) and not _looks_numeric(answer):
        return AnswerAttemptFeedback(
            question_type=question_type,
            answer_format='invalid_shape',
            prefix='Good try. This step needs a number as the answer.',
        )

    if display_answer:
        return AnswerAttemptFeedback(
            question_type=question_type,
            answer_format='valid',
            prefix=f'Good try. {display_answer} is not the right answer for this step.',
        )

    return AnswerAttemptFeedback(
        question_type=question_type,
        answer_format='valid',
        prefix='Good try. That is not the right answer for this step.',
    )


def prepend_attempt_feedback(reply: str, state: TutoringState, student_answer: str) -> str:
    feedback = build_attempt_feedback(state, student_answer)
    prefix = feedback.prefix.strip()
    if not prefix:
        return reply
    clean_reply = str(reply or '').strip()
    if not clean_reply:
        return prefix
    if clean_reply.lower().startswith(prefix.lower()):
        return clean_reply
    return f'{prefix}\n\n{clean_reply}'


def _extract_comparison_choices(state: TutoringState) -> list[str]:
    text = ' '.join([
        str(state.current_question or ''),
        str(state.current_step or ''),
        str(state.active_problem or ''),
    ])
    choices = re.findall(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+(?:\.\d+)?)?%?', text)
    deduped: list[str] = []
    for choice in choices:
        normalized = _normalize_choice(choice)
        if normalized and normalized not in {_normalize_choice(item) for item in deduped}:
            deduped.append(choice.replace(' ', ''))
        if len(deduped) == 2:
            break
    return deduped


def _normalize_choice(value: str) -> str:
    return re.sub(r'\s+', '', str(value or '').lower())


def _looks_like_fraction(value: str) -> bool:
    return bool(re.fullmatch(r'-?\d+\s*/\s*-?\d+', str(value or '').strip()))


def _looks_numeric(value: str) -> bool:
    return bool(re.fullmatch(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?%?', str(value or '').strip()))


def _display_answer(value: str) -> str:
    clean = str(value or '').strip().replace('\n', ' ')
    if not clean or len(clean) > 24:
        return ''
    return clean
