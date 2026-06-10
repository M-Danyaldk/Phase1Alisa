from backend.app.assessment_bank import all_assessment_versions, version_for
from backend.app.assessment_result_items import build_question_results, summarize_question_results
from backend.app.database import get_connection, init_db
from backend.app.models import AssessmentRequest, StudentProfile


def main() -> None:
    failures: list[str] = []
    student = StudentProfile(name='QA Student', grade=4)

    math_version = version_for('Math', 4, 1)
    math_payload = AssessmentRequest(
        student=student,
        child_id='qa-child',
        subject='Math',
        grade=4,
        assessment_version=1,
        question_ids=[question.id for question in math_version.questions],
        questions=[question.question for question in math_version.questions],
        answers=['48', '3/4', '6 days'],
    )
    math_results = build_question_results(math_payload)
    math_summary = summarize_question_results(math_results)
    if len(math_results) != 3:
        failures.append(f'Reported Math payload returned {len(math_results)} question results.')
    if math_summary['correct_count'] != 3 or math_summary['total_questions'] != 3:
        failures.append(f'Reported Math summary was {math_summary}.')
    if [item.question_id for item in math_results] != [question.id for question in math_version.questions]:
        failures.append('Reported Math question IDs were not preserved.')
    if math_results[2].expected_answer != '6' or math_results[2].status != 'correct':
        failures.append(f'Mia pages item was {math_results[2].status} expected={math_results[2].expected_answer}.')

    compatibility_payload = AssessmentRequest(
        student=student,
        child_id='qa-child',
        subject='Math',
        grade=4,
        questions=[
            'What is 6 x 7?',
            'Which is larger: 3/4 or 2/3? Explain briefly.',
            'A book has 48 pages. Mia reads 8 pages each day. How many days will it take?',
        ],
        answers=['42', '3/4', '6'],
    )
    compatibility_results = build_question_results(compatibility_payload)
    if len(compatibility_results) != 3:
        failures.append(f'Compatibility payload returned {len(compatibility_results)} question results.')
    if summarize_question_results(compatibility_results)['correct_count'] != 3:
        failures.append(f'Compatibility payload did not mark all three correct: {[item.status for item in compatibility_results]}')

    unmatched_payload = AssessmentRequest(
        student=student,
        child_id='qa-child',
        subject='ELA',
        grade=4,
        questions=['Read this brand-new sentence. What is the best answer?'],
        answers=['A thoughtful answer'],
    )
    unmatched_results = build_question_results(unmatched_payload)
    if len(unmatched_results) != 1:
        failures.append('Unmatched payload did not return one result.')
    elif unmatched_results[0].status != 'needs_review':
        failures.append(f'Unmatched payload returned {unmatched_results[0].status}, expected needs_review.')

    checked_versions = 0
    for version in all_assessment_versions():
        payload = AssessmentRequest(
            student=student.model_copy(update={'grade': version.grade}),
            child_id='qa-child',
            subject=version.subject,  # type: ignore[arg-type]
            grade=version.grade,
            assessment_version=version.version,
            question_ids=[question.id for question in version.questions],
            questions=[question.question for question in version.questions],
            answers=[question.accepted_answers[0] if question.accepted_answers else 'This is a complete sentence with enough detail.' for question in version.questions],
        )
        results = build_question_results(payload)
        if len(results) != 3:
            failures.append(f'{version.subject} grade {version.grade} version {version.version} returned {len(results)} results.')
        if [item.position for item in results] != [1, 2, 3]:
            failures.append(f'{version.subject} grade {version.grade} version {version.version} positions were {[item.position for item in results]}.')
        if not all(item.question_id for item in results):
            failures.append(f'{version.subject} grade {version.grade} version {version.version} had empty question IDs.')
        checked_versions += 1

    init_db()
    with get_connection() as conn:
        columns = [row['name'] for row in conn.execute('PRAGMA table_info(assessment_results)').fetchall()]
    for required in ['assessment_question_results', 'correct_count', 'total_questions']:
        if required not in columns:
            failures.append(f'Local assessment_results table is missing {required}.')

    if failures:
        print('Assessment question result check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Assessment question result check passed.')
    print('- Reported Math set returns 3 item results and 3 correct.')
    print('- Compatibility payload without question IDs still returns 3 item results.')
    print('- Unmatched questions remain visible as needs_review.')
    print(f'- Checked all bank versions: {checked_versions}.')
    print('- Local DB has item-result persistence columns.')


if __name__ == '__main__':
    main()
