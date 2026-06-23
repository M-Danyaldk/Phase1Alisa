from backend.app.main import _tutor_math_question_state, _tutor_practice_answer_reply
from backend.app.models import TutoringState
from backend.app.services.tutor_answer_attempt_feedback import build_attempt_feedback, prepend_attempt_feedback
from backend.app.tutor_math_practice_bank import TutorMathPracticeQuestion
from backend.app.utils.attempt_policy import register_answer_attempt


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []

    arithmetic = TutoringState(
        current_subject='Math',
        active_problem='What is -9 + 5?',
        current_step='-9 + 5',
        current_question='What is -9 + 5?',
        expected_answer='-4',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    arithmetic_feedback = build_attempt_feedback(arithmetic, '4')
    _expect(arithmetic_feedback.question_type == 'arithmetic_single_step', 'Arithmetic answer feedback did not preserve the arithmetic question type.', failures)
    _expect('4 is not the right answer' in arithmetic_feedback.prefix, 'Arithmetic wrong answer was not acknowledged directly.', failures)

    fraction_compare = TutoringState(
        current_subject='Math',
        active_problem='Which is larger: 7/8 or 5/8?',
        current_step='Which is larger: 7/8 or 5/8?',
        current_question='Which is larger: 7/8 or 5/8?',
        expected_answer='7/8',
        skill='fraction comparison',
        tutor_practice_topic='equivalent fractions and decimals',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    compare_shape_feedback = build_attempt_feedback(fraction_compare, '13')
    _expect(compare_shape_feedback.answer_format == 'invalid_shape', 'Fraction-comparison numeric mismatch was not flagged as the wrong answer shape.', failures)
    _expect('answer with one of the choices: 7/8 or 5/8' in compare_shape_feedback.prefix, 'Fraction-comparison feedback did not redirect the child to the comparison choices.', failures)

    compare_choice_feedback = build_attempt_feedback(fraction_compare, '5/8')
    _expect(compare_choice_feedback.answer_format == 'valid_choice', 'Fraction-comparison wrong choice was not recognized as a real choice attempt.', failures)
    _expect('5/8 is one of the choices' in compare_choice_feedback.prefix, 'Fraction-comparison wrong choice was not acknowledged clearly.', failures)

    equivalent = TutoringState(
        current_subject='Math',
        active_problem='What fraction is equivalent to 1/2: 2/4 or 1/4?',
        current_step='What fraction is equivalent to 1/2: 2/4 or 1/4?',
        current_question='What fraction is equivalent to 1/2: 2/4 or 1/4?',
        expected_answer='2/4',
        skill='equivalent fractions',
        tutor_practice_topic='equivalent fractions and decimals',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    equivalent_feedback = build_attempt_feedback(equivalent, '4')
    _expect(equivalent_feedback.answer_format == 'invalid_shape', 'Equivalent-fraction whole-number answer was not rejected as the wrong answer shape.', failures)
    _expect('needs a fraction as the answer' in equivalent_feedback.prefix, 'Equivalent-fraction feedback did not ask for a fraction answer.', failures)

    prefixed = prepend_attempt_feedback('Here is the first hint.\n\nCompare the top numbers.', fraction_compare, '13')
    _expect(prefixed.startswith('Good try.'), 'Attempt feedback prefix was not added before the hint.', failures)
    _expect('Here is the first hint.' in prefixed, 'Attempt feedback prefix removed the original hint content.', failures)

    practice_question = TutorMathPracticeQuestion(
        id='feedback-fraction-1',
        grade=4,
        topic='equivalent fractions and decimals',
        skill='fraction comparison',
        question='Which is larger: 7/8 or 5/8?',
        expected_answer='7/8',
        accepted_answers=(),
        hint_1='The denominators are the same, so compare the top numbers.',
        hint_2='7 eighths is more than 5 eighths.',
        worked_explanation='7/8 is larger than 5/8 because 7 is greater than 5.',
    )
    practice_state = _tutor_math_question_state(TutoringState(current_subject='Math'), 'Math', 'ready', practice_question)
    practice_attempt = register_answer_attempt(practice_state)
    practice_reply, _ = _tutor_practice_answer_reply(practice_attempt, '13', None, '')
    _expect(practice_reply.startswith('Good try.'), 'Tutor-practice wrong answer did not start with warm attempt feedback.', failures)
    _expect('answer with one of the choices: 7/8 or 5/8' in practice_reply, 'Tutor-practice fraction comparison did not explain the needed answer form.', failures)
    _expect('Here is the first hint.' in practice_reply, 'Tutor-practice wrong answer did not continue into the hint ladder.', failures)

    if failures:
        print('Tutor answer-attempt feedback check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor answer-attempt feedback check passed.')
    print('- Wrong answers are acknowledged before hints instead of being ignored.')
    print('- Fraction-comparison and equivalent-fraction questions explain the needed answer form.')


if __name__ == '__main__':
    main()
