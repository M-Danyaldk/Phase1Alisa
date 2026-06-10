import asyncio

from backend.app.assessment_bank import all_assessment_versions, version_for
from backend.app.assessment_validation import validate_assessment_answer, validate_answers
from backend.app.services.tutor_answer_checker import TutorAnswerChecker


async def main() -> None:
    failures: list[str] = []

    math_g4_v1 = version_for('Math', 4, 1)
    mia_question = math_g4_v1.questions[2]
    for answer in ['6', '6 days', 'six', 'six days']:
        result = validate_assessment_answer(mia_question, answer)
        if result.status != 'correct':
            failures.append(f'Mia pages answer {answer!r} returned {result.status}.')

    wrong_mia = validate_assessment_answer(mia_question, '8')
    if wrong_mia.status != 'incorrect':
        failures.append(f'Mia pages wrong answer returned {wrong_mia.status}, expected incorrect.')

    math_g4_v16 = version_for('Math', 4, 16)
    multiplication_question = math_g4_v16.questions[0]
    if multiplication_question.expected_answer != '102':
        failures.append(f'Expected math-g4-v16-q1 to target 102, found {multiplication_question.expected_answer}.')
    for answer in ['102', 'one hundred two']:
        result = validate_assessment_answer(multiplication_question, answer)
        if result.status != 'correct':
            failures.append(f'34 x 3 bank answer {answer!r} returned {result.status}.')

    tutor_checker = TutorAnswerChecker()
    tutor_cases = [
        ('What is 34 x 3?', '102'),
        ('What is 34 \\u00d7 3?', '102'),
        ('34 * 3', '102'),
        ('What is 48 \\u00f7 8?', '6'),
        ('What is -3 + 8?', '5'),
    ]
    for question, answer in tutor_cases:
        question = question.encode('utf-8').decode('unicode_escape')
        result = await tutor_checker.check('Math', question, answer)
        if result.status != 'correct':
            failures.append(f'Tutor checker failed {question!r} -> {answer!r}: {result.status}, expected {result.expected_answer}.')

    fraction_question = math_g4_v1.questions[1]
    fraction_result = validate_assessment_answer(fraction_question, '3/4')
    if fraction_result.status != 'correct':
        failures.append(f'Fraction comparison returned {fraction_result.status}.')

    reading_g4_v1 = version_for('ELA', 4, 1)
    vocab_result = validate_assessment_answer(reading_g4_v1.questions[0], 'jumped')
    if vocab_result.status != 'correct':
        failures.append(f'Reading vocabulary returned {vocab_result.status}.')
    grammar_result = validate_assessment_answer(reading_g4_v1.questions[2], "She doesn't want to go.")
    if grammar_result.status != 'correct':
        failures.append(f'Reading grammar returned {grammar_result.status}.')

    writing_g4_v1 = version_for('Writing', 4, 1)
    blank_writing = validate_assessment_answer(writing_g4_v1.questions[0], '')
    if blank_writing.status != 'incorrect':
        failures.append(f'Blank writing returned {blank_writing.status}.')
    adequate_writing = validate_assessment_answer(
        writing_g4_v1.questions[0],
        'The park is my favorite place because I can play soccer there.',
    )
    if adequate_writing.status != 'needs_review':
        failures.append(f'Adequate writing returned {adequate_writing.status}, expected needs_review.')

    all_correct_validation_types = {'numeric', 'numeric_or_fraction', 'exact_text', 'keyword_text'}
    checked_questions = 0
    for version in all_assessment_versions():
        answers = []
        for question in version.questions:
            if question.validation_type in all_correct_validation_types:
                answers.append(question.accepted_answers[0] if question.accepted_answers else question.expected_answer)
                checked_questions += 1
            else:
                answers.append('This is a complete sentence with enough detail.')
        results = validate_answers(version.questions, answers)
        for question, result in zip(version.questions, results):
            if question.validation_type in all_correct_validation_types and result.status != 'correct':
                failures.append(f'{question.id} expected self-check correct, got {result.status} for {answers[question.position - 1]!r}.')

    if checked_questions != 480:
        failures.append(f'Expected to self-check 480 non-writing questions, checked {checked_questions}.')

    if failures:
        print('Assessment validation check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Assessment validation check passed.')
    print('- Reported 34 x / multiplication symbol case is deterministic.')
    print('- Reported Mia pages question accepts 6, 6 days, six, and six days.')
    print('- Wrong known-answer math returns incorrect.')
    print('- Reading vocabulary and grammar deterministic checks pass.')
    print('- Writing uses deterministic minimum checks and needs_review for adequate open writing.')
    print(f'- Bank self-check passed for {checked_questions} non-writing questions.')


if __name__ == '__main__':
    asyncio.run(main())
