from backend.app.main import _child_safe_assessment_result
from backend.app.models import AssessmentQuestionResult, AssessmentResult


def main() -> None:
    failures: list[str] = []

    all_correct = _result(
        correct_count=3,
        statuses=['correct', 'correct', 'correct'],
        learning_gaps=[],
        next_topics=['multi-step word problems'],
    )
    all_correct_child = _child_safe_assessment_result(all_correct)
    if all_correct_child.badge_label != 'All Correct':
        failures.append(f'All-correct badge was {all_correct_child.badge_label}.')
    if 'all 3' not in all_correct_child.celebration_message.lower():
        failures.append(f'All-correct message was {all_correct_child.celebration_message!r}.')
    if 'Glad you completed' in all_correct_child.encouragement:
        failures.append('All-correct encouragement still uses old generic consolation copy.')
    if all_correct_child.score_summary != 'Score: 3/3 correct':
        failures.append(f'All-correct score summary was {all_correct_child.score_summary!r}.')

    mostly_correct = _child_safe_assessment_result(_result(
        correct_count=2,
        statuses=['correct', 'correct', 'incorrect'],
        learning_gaps=['division word problems'],
        next_topics=['division word problems'],
    ))
    if mostly_correct.badge_label != 'Strong Work':
        failures.append(f'Mostly-correct badge was {mostly_correct.badge_label}.')
    if '2 out of 3' not in mostly_correct.celebration_message:
        failures.append(f'Mostly-correct message was {mostly_correct.celebration_message!r}.')

    some_correct = _child_safe_assessment_result(_result(
        correct_count=1,
        statuses=['correct', 'incorrect', 'incorrect'],
        learning_gaps=['fraction comparison'],
        next_topics=['fraction comparison'],
    ))
    if some_correct.badge_label != 'Practice Ready':
        failures.append(f'Some-correct badge was {some_correct.badge_label}.')
    if some_correct.performance_label != 'Ready for Practice':
        failures.append(f'Some-correct performance label was {some_correct.performance_label}.')

    review_ready = _child_safe_assessment_result(_result(
        correct_count=0,
        statuses=['needs_review', 'needs_review', 'needs_review'],
        learning_gaps=[],
        next_topics=['writing clarity'],
        subject='Writing',
    ))
    if review_ready.badge_label != 'Review Ready':
        failures.append(f'Review-ready badge was {review_ready.badge_label}.')
    if 'ready for review' not in review_ready.score_summary:
        failures.append(f'Review-ready score summary was {review_ready.score_summary!r}.')
    if 'wrong' in review_ready.child_message.lower():
        failures.append(f'Review-ready child message used wrong-language: {review_ready.child_message!r}.')

    zero_correct = _child_safe_assessment_result(_result(
        correct_count=0,
        statuses=['incorrect', 'incorrect', 'incorrect'],
        learning_gaps=['multiplication facts'],
        next_topics=['multiplication facts'],
    ))
    if zero_correct.score_summary != 'Score: 0/3 correct':
        failures.append(f'Zero-correct score summary was {zero_correct.score_summary!r}.')
    if 'clear place to start' not in zero_correct.encouragement:
        failures.append(f'Zero-correct encouragement was {zero_correct.encouragement!r}.')

    if failures:
        print('Assessment score feedback check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Assessment score feedback check passed.')
    print('- 3/3 correct gets all-correct success language.')
    print('- 2/3 correct gets strong-work language.')
    print('- 1/3 and 0/3 get supportive practice language.')
    print('- Review-needed writing gets review language, not wrong-language.')
    print('- Old generic consolation copy is not used for all-correct results.')


def _result(
    correct_count: int,
    statuses: list[str],
    learning_gaps: list[str],
    next_topics: list[str],
    subject: str = 'Math',
) -> AssessmentResult:
    return AssessmentResult(
        subject=subject,  # type: ignore[arg-type]
        enrolled_grade=4,
        assessment_version=1,
        assessment_question_ids=[f'q{index + 1}' for index in range(len(statuses))],
        question_results=[
            AssessmentQuestionResult(
                question_id=f'q{index + 1}',
                position=index + 1,
                skill=next_topics[0] if next_topics else 'practice',
                question=f'Question {index + 1}',
                student_answer='answer',
                expected_answer='expected',
                status=status,
                validation_type='numeric',
                confidence='high',
                feedback_note='',
                child_feedback='',
                next_topic_if_incorrect=next_topics[0] if next_topics else '',
            )
            for index, status in enumerate(statuses)
        ],
        correct_count=correct_count,
        total_questions=len(statuses),
        estimated_level='Practice focus',
        score_label='LLM label should not control child tone',
        strengths=['Student completed the check-in.'],
        learning_gaps=learning_gaps,
        recommended_progression=['Practice one focused skill.'],
        recommended_next_topics=next_topics,
        parent_summary='Summary',
        provider='local',
        model='rules',
    )


if __name__ == '__main__':
    main()
