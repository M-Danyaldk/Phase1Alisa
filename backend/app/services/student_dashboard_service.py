from ..schemas.child_report import ChildReportResponse, SubjectProgress
from ..schemas.student_dashboard import (
    StudentAchievement,
    StudentActivityItem,
    StudentDashboardProfile,
    StudentDashboardResponse,
    StudentProgressItem,
)
from .child_report_service import ChildReportService


class StudentDashboardService:
    async def dashboard_for_child(self, parent_id: str, child_id: str) -> StudentDashboardResponse:
        report = await ChildReportService().report_for_child(parent_id, child_id, period='week', subject='All')
        assessed_count = len([item for item in report.subject_progress if item.assessment_count > 0])
        weekly_focus = self._weekly_focus(report)

        return StudentDashboardResponse(
            student=StudentDashboardProfile(
                child_id=report.child_id,
                name=report.child_name,
                grade_level=report.grade_level,
                status='active',
                weekly_focus=weekly_focus,
            ),
            assessment_status=report.assessment_status,
            homework_status='No homework upload reviewed yet',
            weekly_focus=weekly_focus,
            subject_progress=[self._progress_item(item) for item in report.subject_progress],
            recent_activity=self._recent_activity(report),
            achievements=self._achievements(report, assessed_count),
            recommended_next_actions=report.recommended_next_steps or self._default_next_actions(report),
        )

    def _progress_item(self, item: SubjectProgress) -> StudentProgressItem:
        return StudentProgressItem(
            subject=item.subject,  # type: ignore[arg-type]
            level=item.level,
            progress_percentage=item.progress_percentage,
            current_focus=item.current_topic or item.needs_review or 'Start with a short placement check',
            next_step=self._next_step_for_subject(item),
            status='Learning path started' if item.assessment_count or item.chat_count else 'Assessment needed',
        )

    def _recent_activity(self, report: ChildReportResponse) -> list[StudentActivityItem]:
        activity: list[StudentActivityItem] = []
        for assessment in report.recent_assessments[:2]:
            activity.append(StudentActivityItem(
                id=f'assessment-{assessment.id or assessment.subject}',
                title=f'{assessment.subject} assessment saved',
                detail=assessment.parent_summary or f'Estimated level: {assessment.estimated_level}',
                when=self._display_date(assessment.created_at),
                subject=assessment.subject if assessment.subject in ('Math', 'ELA', 'Writing') else None,
            ))
        for session in report.recent_tutor_sessions[:2]:
            activity.append(StudentActivityItem(
                id=f'session-{session.thread_id}',
                title=session.title or f'{session.subject} learning session',
                detail=session.next_step,
                when=self._display_date(session.last_activity_at),
                subject=session.subject if session.subject in ('Math', 'ELA', 'Writing') else None,
            ))
        if activity:
            return activity[:4]
        return [StudentActivityItem(
            id='empty-learning-activity',
            title='No learning activity yet',
            detail='Start an assessment or tutoring session to unlock progress, reports, and recommendations.',
            when='Not started',
        )]

    def _achievements(self, report: ChildReportResponse, assessed_count: int) -> list[StudentAchievement]:
        lesson_count = report.lessons_completed
        return [
            StudentAchievement(
                id='profile-created',
                title='Profile Started',
                detail=f"{report.child_name}'s learning profile is ready.",
                status='earned',
            ),
            StudentAchievement(
                id='first-assessment',
                title='First Assessment',
                detail='Complete one subject check to unlock a learning path.',
                status='earned' if assessed_count else 'in_progress',
            ),
            StudentAchievement(
                id='first-session',
                title='First Learning Session',
                detail='Finish one guided MsAlisia tutoring session.',
                status='earned' if lesson_count else 'locked',
            ),
        ]

    def _weekly_focus(self, report: ChildReportResponse) -> str:
        if report.weak_areas and not report.weak_areas[0].startswith('No weak areas'):
            return report.weak_areas[0]
        if report.recommended_next_steps:
            return report.recommended_next_steps[0]
        return 'Start with short lessons and quick check-ins'

    def _next_step_for_subject(self, item: SubjectProgress) -> str:
        if item.assessment_count == 0:
            return f'Complete the {item.subject} quick assessment'
        if item.needs_review:
            return f'Review {item.needs_review}'
        return f'Practice one guided {item.subject} lesson with MsAlisia'

    def _default_next_actions(self, report: ChildReportResponse) -> list[str]:
        missing = [item.subject for item in report.subject_progress if item.assessment_count == 0]
        if missing:
            return [f'Start the {missing[0]} assessment.', 'Try one short learning chat.', 'Upload homework when written work is ready.']
        return ['Continue the next guided lesson.', 'Review the latest report.', 'Upload homework when written work is ready.']

    def _display_date(self, value: str | None) -> str:
        if not value:
            return 'Recently'
        return value[:10]
