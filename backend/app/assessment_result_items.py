from functools import lru_cache

from .assessment_bank import AssessmentQuestion, all_assessment_versions, question_for_id
from .assessment_validation import (
    extract_math_expression,
    extract_numeric_value,
    format_fraction,
    normalize_answer_text,
    safe_eval_expression,
    validate_assessment_answer,
)
from .models import AssessmentQuestionResult, AssessmentRequest


def build_question_results(payload: AssessmentRequest) -> list[AssessmentQuestionResult]:
    results: list[AssessmentQuestionResult] = []
    for index, question_text in enumerate(payload.questions):
        answer = payload.answers[index] if index < len(payload.answers) else ''
        bank_question = _question_from_payload(payload, index, question_text)
        if bank_question:
            validation = validate_assessment_answer(bank_question, answer)
            results.append(AssessmentQuestionResult(
                question_id=bank_question.id,
                position=index + 1,
                skill=bank_question.skill,
                question=bank_question.question,
                student_answer=answer,
                expected_answer=validation.expected_answer,
                status=validation.status,
                validation_type=validation.validation_type,
                confidence=validation.confidence,
                feedback_note=validation.feedback_note,
                child_feedback=_child_feedback(bank_question, validation.status),
                next_topic_if_incorrect=bank_question.next_topic_if_incorrect,
            ))
            continue

        results.append(_fallback_result(payload, index, question_text, answer))
    return results


def summarize_question_results(results: list[AssessmentQuestionResult]) -> dict:
    correct_count = len([item for item in results if item.status == 'correct'])
    total_questions = len(results)
    partially_correct = len([item for item in results if item.status == 'partially_correct'])
    needs_review = len([item for item in results if item.status == 'needs_review'])
    return {
        'correct_count': correct_count,
        'total_questions': total_questions,
        'partially_correct_count': partially_correct,
        'needs_review_count': needs_review,
        'question_ids': [item.question_id for item in results if item.question_id],
    }


def _question_from_payload(payload: AssessmentRequest, index: int, question_text: str) -> AssessmentQuestion | None:
    if index < len(payload.question_ids):
        matched = question_for_id(payload.question_ids[index])
        if matched:
            return matched
    return _match_question_by_text(payload.subject, payload.grade, question_text)


def _match_question_by_text(subject: str, grade: int, question_text: str) -> AssessmentQuestion | None:
    normalized = normalize_answer_text(question_text)
    if not normalized:
        return None
    preferred = _question_text_index().get((subject, grade, normalized))
    if preferred:
        return preferred
    return _subject_question_text_index().get((subject, normalized))


@lru_cache(maxsize=1)
def _question_text_index() -> dict[tuple[str, int, str], AssessmentQuestion]:
    index: dict[tuple[str, int, str], AssessmentQuestion] = {}
    for version in all_assessment_versions():
        for question in version.questions:
            index.setdefault((question.subject, question.grade, normalize_answer_text(question.question)), question)
    return index


@lru_cache(maxsize=1)
def _subject_question_text_index() -> dict[tuple[str, str], AssessmentQuestion]:
    index: dict[tuple[str, str], AssessmentQuestion] = {}
    for version in all_assessment_versions():
        for question in version.questions:
            index.setdefault((question.subject, normalize_answer_text(question.question)), question)
    return index


def _fallback_result(
    payload: AssessmentRequest,
    index: int,
    question_text: str,
    answer: str,
) -> AssessmentQuestionResult:
    expected_answer = ''
    status = 'needs_review'
    confidence = 'low'
    feedback_note = 'Question was not found in the validated assessment bank.'
    validation_type = 'needs_review'

    if payload.subject == 'Math':
        expression = extract_math_expression(question_text)
        expected_value = safe_eval_expression(expression) if expression else None
        student_value = extract_numeric_value(answer)
        if expected_value is not None:
            expected_answer = format_fraction(expected_value)
            validation_type = 'numeric'
            if student_value is None:
                status = 'needs_review'
                feedback_note = 'Could not parse the student numeric answer safely.'
            elif student_value == expected_value:
                status = 'correct'
                confidence = 'high'
                feedback_note = f'Numeric answer matches {expected_answer}.'
            else:
                status = 'incorrect'
                confidence = 'high'
                feedback_note = f'Expected {expected_answer}.'

    return AssessmentQuestionResult(
        question_id=f'submitted-q{index + 1}',
        position=index + 1,
        skill='',
        question=question_text,
        student_answer=answer,
        expected_answer=expected_answer,
        status=status,
        validation_type=validation_type,
        confidence=confidence,
        feedback_note=feedback_note,
        child_feedback=_fallback_child_feedback(status),
        next_topic_if_incorrect='',
    )


def _child_feedback(question: AssessmentQuestion, status: str) -> str:
    if status == 'correct':
        if question.validation_type == 'writing_rubric':
            if question.skill == 'complete sentence':
                return 'Nice job. You wrote a clear complete sentence.'
            if question.skill == 'explanatory writing':
                return 'Nice job. You explained your idea in complete sentences.'
            if question.skill == 'revision for detail':
                return 'Nice job. You made the sentence stronger with better detail.'
        return question.child_correct_feedback
    if status == 'partially_correct':
        if question.validation_type == 'writing_rubric':
            if question.skill == 'complete sentence':
                return 'Good try. Your idea is there. Next, make it a full sentence with a capital letter and ending punctuation.'
            if question.skill == 'explanatory writing':
                return 'Good try. You started explaining your idea. Next, write three complete sentences and add a clearer reason.'
            if question.skill == 'revision for detail':
                return 'Good try. You started to revise the sentence. Next, add more specific detail to make it stronger.'
        if question.validation_type == 'exact_text':
            return 'Good try. You fixed part of it. Check capitalization, grammar, and punctuation one more time.'
        return f'Nice effort. You are close, and we can strengthen {question.next_topic_if_incorrect}.'
    if status == 'needs_review':
        return 'Ms. Alisia will review this carefully before choosing the next step.'
    if question.validation_type == 'writing_rubric':
        if question.skill == 'complete sentence':
            return "Good try. Let's practice writing one clear complete sentence."
        if question.skill == 'explanatory writing':
            return "Good try. Let's practice explaining your idea in three complete sentences."
        if question.skill == 'revision for detail':
            return "Good try. Let's practice making a sentence stronger with clearer detail."
    if question.validation_type == 'exact_text':
        return "Good try. Let's practice fixing the sentence so it has the right grammar and punctuation."
    if question.validation_type == 'keyword_text':
        return "Good try. Let's go back to the main idea and look for the most important words."
    return question.child_incorrect_feedback


def _fallback_child_feedback(status: str) -> str:
    if status == 'correct':
        return 'Great job. This answer checks out.'
    if status == 'incorrect':
        return 'Good try. We found one part to practice together.'
    return 'Ms. Alisia will review this carefully before choosing the next step.'
