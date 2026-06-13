import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.curriculum import CURRICULUM, INTERNAL_SUPPORTED_GRADES, LAUNCH_GRADES, LAUNCH_SUBJECTS, curriculum_payload
from backend.app.models import AssessmentRequest, StudentProfile
from backend.app.prompts import assessment_prompt, compact_chat_system_prompt


def main() -> None:
    payload = curriculum_payload()
    assert payload['supported_grades'] == LAUNCH_GRADES
    assert payload['grades'] == LAUNCH_GRADES
    assert payload['internal_supported_grades'] == list(range(3, 13))
    assert payload['launch_subjects'] == LAUNCH_SUBJECTS
    assert payload['future_subjects'] == ['Science', 'Social Studies']

    for subject in LAUNCH_SUBJECTS:
        assert subject in CURRICULUM, f'{subject} missing from curriculum'
        for grade in INTERNAL_SUPPORTED_GRADES:
            topics = CURRICULUM[subject].get(grade)
            assert topics and len(topics) >= 5, f'{subject} Grade {grade} needs at least 5 topics'
        for grade in LAUNCH_GRADES:
            topics = CURRICULUM[subject].get(grade)
            student = StudentProfile(name='Coverage Student', grade=grade)
            AssessmentRequest(
                student=student,
                subject=subject,
                grade=grade,
                questions=[f'Grade {grade} {subject} check'],
                answers=['sample answer'],
            )
            compact_chat_system_prompt(student, subject, topics[0])
            assessment_prompt(student, subject, grade, [topics[0]], ['sample answer'])

    print('Grade coverage check passed: launch is locked to Grades 3-6; internal curriculum is ready for Grades 3-12.')


if __name__ == '__main__':
    main()
