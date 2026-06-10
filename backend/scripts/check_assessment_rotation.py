from collections import Counter

from backend.app.assessment_bank import EXPECTED_VERSION_COUNT
from backend.app.assessment_selector import select_next_assessment_version, previous_versions_from_assessments
from backend.app.curriculum import LAUNCH_GRADES, LAUNCH_SUBJECTS


SIMULATED_ATTEMPTS = 45


def main() -> None:
    failures: list[str] = []

    for grade in LAUNCH_GRADES:
        for subject in LAUNCH_SUBJECTS:
            previous: list[int] = []
            selected_versions: list[int] = []
            child_id = f'rotation-test-child-g{grade}-{subject.lower()}'

            for attempt_number in range(1, SIMULATED_ATTEMPTS + 1):
                selection = select_next_assessment_version(
                    subject=subject,
                    grade=grade,
                    previous_versions=previous,
                    child_id=child_id,
                )
                selected_versions.append(selection.version_number)

                if len(selection.question_ids) != 3:
                    failures.append(f'{subject} grade {grade} attempt {attempt_number} returned {len(selection.question_ids)} questions.')

                if attempt_number > 1 and selected_versions[-1] == selected_versions[-2]:
                    failures.append(f'{subject} grade {grade} repeated version {selection.version_number} immediately on attempt {attempt_number}.')

                previous.insert(0, selection.version_number)

            first_cycle = selected_versions[:EXPECTED_VERSION_COUNT]
            if len(set(first_cycle)) != EXPECTED_VERSION_COUNT:
                failures.append(f'{subject} grade {grade} first {EXPECTED_VERSION_COUNT} attempts were not unique: {first_cycle}')

            if set(first_cycle) != set(range(1, EXPECTED_VERSION_COUNT + 1)):
                failures.append(f'{subject} grade {grade} first cycle did not cover all versions: {first_cycle}')

            counts = Counter(selected_versions)
            if max(counts.values()) - min(counts.values()) > 1:
                failures.append(f'{subject} grade {grade} rotation was unbalanced after {SIMULATED_ATTEMPTS} attempts: {dict(counts)}')

    sample_rows = [
        {'subject': 'Math', 'enrolled_grade': 4, 'assessment_version': 7},
        {'subject': 'Math', 'enrolled_grade': 4, 'assessment_version': '6'},
        {'subject': 'ELA', 'enrolled_grade': 4, 'assessment_version': 9},
        {'subject': 'Math', 'enrolled_grade': 5, 'assessment_version': 8},
        {'subject': 'Math', 'enrolled_grade': 4, 'assessment_version': None},
    ]
    parsed = previous_versions_from_assessments(sample_rows, subject='Math', grade=4)
    if parsed != (7, 6):
        failures.append(f'History parser returned {parsed}, expected (7, 6).')

    if failures:
        print('Assessment rotation check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Assessment rotation check passed.')
    print(f'- Checked grades: {LAUNCH_GRADES}')
    print(f'- Checked subjects: {LAUNCH_SUBJECTS}')
    print(f'- Simulated attempts per grade/subject: {SIMULATED_ATTEMPTS}')
    print(f'- First {EXPECTED_VERSION_COUNT} attempts cover all versions without repeats.')
    print('- No immediate version repeat during safe rotation.')
    print('- Saved assessment history parser works for assessment_version rows.')


if __name__ == '__main__':
    main()
