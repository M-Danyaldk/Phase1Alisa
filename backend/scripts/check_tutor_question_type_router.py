from backend.app.models import TutorHelperBranch, TutoringState
from backend.app.services.tutor_question_type_router import infer_active_question_type


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []

    single_step = TutoringState(
        current_subject='Math',
        current_question='What is 72 + 48?',
        current_step='72 + 48',
        active_problem='72 + 48',
        expected_answer='120',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(single_step) == 'arithmetic_single_step', 'Single-step arithmetic question type was not detected.', failures)

    multi_step = TutoringState(
        current_subject='Math',
        current_question='What is 35 + 10 - 5?',
        current_step='35 + 10 - 5',
        active_problem='35 + 10 - 5',
        expected_answer='40',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(multi_step) == 'arithmetic_multi_step', 'Multi-step arithmetic question type was not detected.', failures)

    fraction_compare = TutoringState(
        current_subject='Math',
        current_question='Which is larger: 7/8 or 5/8?',
        active_problem='Which is larger: 7/8 or 5/8?',
        skill='fraction comparison',
        tutor_practice_topic='fractions as parts of a whole',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    _expect(infer_active_question_type(fraction_compare) == 'fraction_comparison', 'Fraction comparison question type was not detected.', failures)

    equivalent_fraction = TutoringState(
        current_subject='Math',
        current_question='Write a fraction equivalent to 3/8 with denominator 16.',
        active_problem='Write a fraction equivalent to 3/8 with denominator 16.',
        skill='equivalent fractions',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    _expect(infer_active_question_type(equivalent_fraction) == 'equivalent_fraction', 'Equivalent-fraction question type was not detected.', failures)

    word_problem = TutoringState(
        current_subject='Math',
        problem_kind='word_problem',
        current_question='How many balls are needed?',
        active_problem='There are 7 boxes and each box holds 2 balls. How many balls are needed?',
        full_problem='There are 7 boxes and each box holds 2 balls. How many balls are needed?',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(word_problem) == 'word_problem', 'Word-problem question type was not detected.', failures)

    continuation = TutoringState(
        current_subject='Math',
        mode='awaiting_more_practice_choice',
        status='waiting_for_student',
        problem_status='finished',
    )
    _expect(infer_active_question_type(continuation) == 'continuation_choice', 'Continuation-choice question type was not detected.', failures)

    helper = TutoringState(
        current_subject='Math',
        helper_branch=TutorHelperBranch(branch_id='helper-1', branch_type='side_question', question='what is denominator?', status='active'),
        current_question='What is 3/4 + 1/4?',
        mode='helper_branch',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(helper) == 'side_question', 'Side-question type was not detected.', failures)

    emotional = TutoringState(
        current_subject='Math',
        emotional_support_mode='choice',
        mode='emotional_checkin',
        status='waiting_for_student',
    )
    _expect(infer_active_question_type(emotional) == 'emotion_support', 'Emotion-support question type was not detected.', failures)

    conceptual = TutoringState(
        current_subject='Math',
        current_question='How many fourths make one whole?',
        active_problem='How many fourths make one whole?',
        skill='unit fractions',
        mode='tutor_practice_question',
        status='waiting_for_student',
        problem_status='tutor_practice',
    )
    _expect(infer_active_question_type(conceptual) == 'conceptual_math', 'Conceptual Math question type was not detected.', failures)

    reading = TutoringState(
        current_subject='ELA',
        current_question='What is the main idea of the story?',
        active_problem='What is the main idea of the story?',
        skill='main idea and key details',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(reading) == 'reading_text', 'Reading question type was not detected.', failures)

    writing = TutoringState(
        current_subject='Writing',
        current_question='Write one clear sentence about your favorite hobby.',
        active_problem='Write one clear sentence about your favorite hobby.',
        skill='complete sentences',
        mode='practice',
        status='waiting_for_student',
        problem_status='awaiting_step',
    )
    _expect(infer_active_question_type(writing) == 'writing_text', 'Writing question type was not detected.', failures)

    if failures:
        print('Tutor question-type router check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor question-type router check passed.')
    print('- Active tutor questions are tagged by arithmetic, fraction, word-problem, continuation, helper, and emotion flow.')


if __name__ == '__main__':
    main()
