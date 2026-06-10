from collections import Counter, defaultdict

from backend.app.assessment_bank import (
    EXPECTED_QUESTIONS_PER_VERSION,
    EXPECTED_TOTAL_QUESTIONS,
    EXPECTED_VERSION_COUNT,
    all_assessment_versions,
)
from backend.app.curriculum import LAUNCH_GRADES, LAUNCH_SUBJECTS


def main() -> None:
    versions = all_assessment_versions()
    questions = [question for version in versions for question in version.questions]
    ids = [question.id for question in questions]
    failures: list[str] = []

    if len(questions) != EXPECTED_TOTAL_QUESTIONS:
        failures.append(f'Expected {EXPECTED_TOTAL_QUESTIONS} questions, found {len(questions)}.')

    duplicate_ids = [question_id for question_id, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        failures.append(f'Duplicate question IDs found: {duplicate_ids[:5]}')

    grouped_versions = defaultdict(list)
    for version in versions:
        grouped_versions[(version.grade, version.subject)].append(version)
        if len(version.questions) != EXPECTED_QUESTIONS_PER_VERSION:
            failures.append(f'{version.subject} grade {version.grade} version {version.version} has {len(version.questions)} questions.')
        positions = [question.position for question in version.questions]
        if positions != [1, 2, 3]:
            failures.append(f'{version.subject} grade {version.grade} version {version.version} positions are {positions}.')

    for grade in LAUNCH_GRADES:
        for subject in LAUNCH_SUBJECTS:
            subject_versions = grouped_versions[(grade, subject)]
            if len(subject_versions) != EXPECTED_VERSION_COUNT:
                failures.append(f'{subject} grade {grade} has {len(subject_versions)} versions.')
            version_numbers = sorted(version.version for version in subject_versions)
            if version_numbers != list(range(1, EXPECTED_VERSION_COUNT + 1)):
                failures.append(f'{subject} grade {grade} version numbers are {version_numbers}.')

    question_text_by_group = defaultdict(list)
    for question in questions:
        question_text_by_group[(question.grade, question.subject)].append(question.question)
        if not question.question.strip():
            failures.append(f'{question.id} has empty question text.')
        if not question.skill.strip():
            failures.append(f'{question.id} has empty skill.')
        if question.validation_type in {'numeric', 'numeric_or_fraction', 'exact_text', 'keyword_text'}:
            if not question.expected_answer.strip():
                failures.append(f'{question.id} has no expected answer.')
            if not question.accepted_answers:
                failures.append(f'{question.id} has no accepted answers.')
        if question.validation_type == 'writing_rubric' and not question.rubric:
            failures.append(f'{question.id} has no writing rubric.')

    for group, texts in question_text_by_group.items():
        duplicate_texts = [text for text, count in Counter(texts).items() if count > 1]
        if duplicate_texts:
            failures.append(f'Duplicate question text in grade {group[0]} {group[1]}: {duplicate_texts[:3]}')

    mia_question = next(
        (
            question for question in questions
            if question.id == 'math-g4-v01-q3'
        ),
        None,
    )
    if not mia_question:
        failures.append('Missing reported Mia pages question math-g4-v01-q3.')
    elif mia_question.expected_answer != '6':
        failures.append(f'Mia pages question expected answer is {mia_question.expected_answer}, not 6.')

    if failures:
        print('Assessment bank check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Assessment bank check passed.')
    print(f'- Versions: {len(versions)}')
    print(f'- Questions: {len(questions)}')
    print(f'- Per grade/subject: {EXPECTED_VERSION_COUNT} versions x {EXPECTED_QUESTIONS_PER_VERSION} questions')
    print('- Reported Mia pages question is present with expected answer 6.')


if __name__ == '__main__':
    main()
