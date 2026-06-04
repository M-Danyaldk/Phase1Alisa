from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from ..schemas.child_report import ChildReportResponse, SubjectProgress
from ..schemas.student_dashboard import (
    StudentAchievement,
    StudentActivityItem,
    StudentDashboardProfile,
    StudentDashboardResponse,
    StudentProgressItem,
    WeeklyRhythmResponse,
)
from .child_report_service import ChildReportService
from .supabase_client import SupabaseClient, SupabaseClientError


class StudentDashboardService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def dashboard_for_child(self, parent_id: str, child_id: str) -> StudentDashboardResponse:
        report = await ChildReportService().report_for_child(parent_id, child_id, period='week', subject='All')
        assessed_count = len([item for item in report.subject_progress if item.assessment_count > 0])
        weekly_focus = self._weekly_focus(report)
        weekly_rhythm = await self.weekly_rhythm_for_child(parent_id, child_id, report.child_name)

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
            weekly_rhythm=weekly_rhythm,
            subject_progress=[self._progress_item(item) for item in report.subject_progress],
            recent_activity=self._recent_activity(report),
            achievements=self._achievements(report, assessed_count),
            recommended_next_actions=report.recommended_next_steps or self._default_next_actions(report),
        )

    async def weekly_rhythm_for_parent(self, parent_id: str) -> list[WeeklyRhythmResponse]:
        try:
            children = await self.supabase.select(
                'child_profiles',
                f'parent_id=eq.{quote(parent_id)}&status=neq.inactive&order=created_at.asc',
            )
        except SupabaseClientError:
            return []
        return [await self.weekly_rhythm_for_child(parent_id, child['id'], child.get('name') or 'This student') for child in children]

    async def weekly_rhythm_for_child(self, parent_id: str, child_id: str, child_name: str = 'This student') -> WeeklyRhythmResponse:
        week_start = self._week_start()
        week_end = week_start + timedelta(days=6)
        row = None
        try:
            records = await self.supabase.select(
                'weekly_learning_rhythm',
                f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&week_start_date=eq.{week_start.date().isoformat()}&limit=1',
            )
            row = records[0] if records else None
        except SupabaseClientError:
            row = None
        session_count = int((row or {}).get('session_count') or 0)
        active_seconds = int((row or {}).get('active_tutoring_seconds') or 0)
        key, label, child_message, parent_summary = self._rhythm_copy(session_count, child_name)
        return WeeklyRhythmResponse(
            child_id=child_id,
            week_start_date=week_start.date().isoformat(),
            week_end_date=week_end.date().isoformat(),
            session_count=session_count,
            active_tutoring_seconds=active_seconds,
            achievement_label=(row or {}).get('achievement_label') or key,
            display_label=label,
            child_message=(row or {}).get('child_visible_message') or child_message,
            parent_summary=(row or {}).get('parent_visible_summary') or parent_summary,
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
            subject_label = self._subject_label(assessment.subject)
            activity.append(StudentActivityItem(
                id=f'assessment-{assessment.id or assessment.subject}',
                title=f'{subject_label} check-in saved',
                detail=assessment.score_label or 'Great effort. Ms. Alisia saved your next learning step.',
                when=self._display_date(assessment.created_at),
                subject=assessment.subject if assessment.subject in ('Math', 'ELA', 'Writing') else None,
            ))
        for session in report.recent_tutor_sessions[:2]:
            subject_label = self._subject_label(session.subject)
            activity.append(StudentActivityItem(
                id=f'session-{session.thread_id}',
                title=session.title or f'{subject_label} learning session',
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
        if report.weak_areas and not report.weak_areas[0].startswith('No growth areas'):
            return report.weak_areas[0]
        if report.recommended_next_steps:
            return report.recommended_next_steps[0]
        return 'Start with short lessons and quick check-ins'

    def _rhythm_copy(self, session_count: int, child_name: str) -> tuple[str, str, str, str]:
        if session_count >= 5:
            return (
                'superstar',
                'Superstar',
                'You showed up a lot this week. Amazing effort. A little rest helps your brain keep all that learning strong.',
                f'{child_name} has 5+ sessions this week. Celebrate the rhythm and keep rest in the plan.',
            )
        if session_count == 4:
            return (
                'perfect_week',
                'Perfect Week!',
                'Four learning sessions this week. That is a beautiful rhythm.',
                f'{child_name} reached a perfect 4-session learning week.',
            )
        if session_count == 3:
            return (
                'strong_week',
                'Strong Week!',
                'Three sessions this week. You are building a strong learning rhythm.',
                f'{child_name} has a strong 3-session learning week.',
            )
        if session_count >= 1:
            return (
                'getting_started',
                'Getting Started',
                'You started your learning rhythm this week. One step counts.',
                f'{child_name} has started the week with {session_count} session(s).',
            )
        return (
            'fresh_start',
            'Fresh Start',
            'A fresh week is ready when you are. No pressure, just one good step.',
            f'{child_name} has a fresh start this week with no sessions yet.',
        )

    def _week_start(self) -> datetime:
        now = datetime.now(UTC)
        monday = now - timedelta(days=now.weekday())
        return datetime(monday.year, monday.month, monday.day, tzinfo=UTC)

    def _next_step_for_subject(self, item: SubjectProgress) -> str:
        if item.assessment_count == 0:
            return f'Complete the {self._subject_label(item.subject)} quick assessment'
        if item.needs_review:
            return f'Review {item.needs_review}'
        return f'Practice one guided {self._subject_label(item.subject)} lesson with MsAlisia'

    def _default_next_actions(self, report: ChildReportResponse) -> list[str]:
        missing = [item.subject for item in report.subject_progress if item.assessment_count == 0]
        if missing:
            return [f'Start the {self._subject_label(missing[0])} assessment.', 'Try one short learning chat.', 'Upload homework when written work is ready.']
        return ['Continue the next guided lesson.', 'Review the latest report.', 'Upload homework when written work is ready.']

    def _display_date(self, value: str | None) -> str:
        if not value:
            return 'Recently'
        return value[:10]

    def _subject_label(self, subject: str | None) -> str:
        return 'Reading' if subject == 'ELA' else (subject or 'Learning')
