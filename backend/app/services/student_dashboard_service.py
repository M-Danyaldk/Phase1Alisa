from datetime import UTC, datetime, timedelta
import re
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
        weekly_focus = self._weekly_focus(report)
        weekly_rhythm = await self.weekly_rhythm_for_child(parent_id, child_id, report.child_name)
        achievement_counts = await self._achievement_counts(parent_id, child_id, report, weekly_rhythm)

        return StudentDashboardResponse(
            student=StudentDashboardProfile(
                child_id=report.child_id,
                name=report.child_name,
                grade_level=report.grade_level,
                status='active',
                weekly_focus=weekly_focus,
            ),
            assessment_status=self._child_check_in_status(report.assessment_status),
            homework_status='No homework upload reviewed yet',
            weekly_focus=weekly_focus,
            weekly_rhythm=weekly_rhythm,
            subject_progress=[self._progress_item(item) for item in report.subject_progress],
            recent_activity=self._recent_activity(report),
            achievements=self._achievements(report, achievement_counts['assessment_count'], achievement_counts['session_count']),
            recommended_next_actions=self._student_next_actions(report),
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
            level=item.display_level or item.level,
            enrolled_grade=item.enrolled_grade,
            working_level=item.working_level,
            working_level_source=item.working_level_source,
            progress_percentage=item.progress_percentage,
            current_focus=item.current_topic or item.needs_review or 'Start with a short placement check',
            next_step=self._next_step_for_subject(item),
            status='Learning path started' if item.assessment_count or item.chat_count else 'Check-In ready',
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
                detail=self._session_activity_detail(session.subject, session.topic),
                when=self._display_date(session.last_activity_at),
                subject=session.subject if session.subject in ('Math', 'ELA', 'Writing') else None,
            ))
        if activity:
            return activity[:4]
        return [StudentActivityItem(
            id='empty-learning-activity',
            title='No learning activity yet',
            detail='Start a quick check-in or tutoring chat so Ms. Alisia can help you pick the next step.',
            when='Not started',
        )]

    async def _achievement_counts(
        self,
        parent_id: str,
        child_id: str,
        report: ChildReportResponse,
        weekly_rhythm: WeeklyRhythmResponse,
    ) -> dict[str, int]:
        assessment_count = max(
            len(report.recent_assessments),
            sum(item.assessment_count for item in report.subject_progress),
        )
        session_count = max(report.lessons_completed, weekly_rhythm.session_count)

        assessment_count = max(assessment_count, await self._has_records('assessment_results', f'child_id=eq.{quote(child_id)}&limit=1'))
        session_count = max(
            session_count,
            await self._has_records('learning_sessions', f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1'),
            await self._has_records('chat_threads', f'user_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1'),
            await self._has_records('session_activity_events', f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1'),
        )

        return {'assessment_count': assessment_count, 'session_count': session_count}

    async def _has_records(self, table: str, query: str) -> int:
        try:
            records = await self.supabase.select(table, query)
        except SupabaseClientError:
            return 0
        return 1 if records else 0

    def _achievements(self, report: ChildReportResponse, assessment_count: int, session_count: int) -> list[StudentAchievement]:
        return [
            StudentAchievement(
                id='profile-created',
                title='Profile Started',
                detail=f"{report.child_name}'s learning profile is ready.",
                status='earned',
            ),
            StudentAchievement(
                id='first-assessment',
                title='First Check-In',
                detail='Complete one subject check to unlock a learning path.',
                status='earned' if assessment_count else 'in_progress',
            ),
            StudentAchievement(
                id='first-session',
                title='First Learning Session',
                detail='Finish one guided MsAlisia tutoring session.',
                status='earned' if session_count else 'locked',
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
            return f'Try the {self._subject_label(item.subject)} Quick Check-In'
        if item.needs_review:
            return f'Review {item.needs_review}'
        return f'Practice one guided {self._subject_label(item.subject)} lesson with MsAlisia'

    def _student_next_actions(self, report: ChildReportResponse) -> list[str]:
        missing = [item.subject for item in report.subject_progress if item.assessment_count == 0]
        if missing:
            return [f'Try your {self._subject_label(missing[0])} Quick Check-In', 'Start Learning', 'Homework Help']

        focus_subject = self._most_recent_subject(report)
        return [f'Start {self._subject_label(focus_subject)} Practice', 'Start Learning', 'Homework Help']

    def _child_check_in_status(self, value: str) -> str:
        text = str(value or '').strip()
        if not text:
            return 'No check-ins finished yet'
        replacements = {
            'No assessment completed yet.': 'No check-ins finished yet.',
            'No assessments completed yet': 'No check-ins finished yet',
            'assessments': 'check-ins',
            'Assessments': 'Check-Ins',
            'assessment': 'check-in',
            'Assessment': 'Check-In',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _session_activity_detail(self, subject: str | None, topic: str | None) -> str:
        topic_label = self._student_topic_label(subject, topic)
        return f'Continue practicing {topic_label} with a short session.'

    def _student_topic_label(self, subject: str | None, topic: str | None) -> str:
        value = self._clean_student_fragment(topic)
        if value:
            return value
        subject_label = self._subject_label(subject)
        if subject_label == 'Math':
            return 'multiplication facts'
        if subject_label == 'Reading':
            return 'reading vocabulary'
        if subject_label == 'Writing':
            return 'writing skills'
        return 'one learning skill'

    def _clean_student_fragment(self, value: str | None) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        text = re.sub(r'[*_`#>\[\]()]', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\s+', ' ', text).strip(' .,:;-')
        if len(text) < 3 or not re.search(r'[A-Za-z]', text):
            return ''
        if any(marker in text.lower() for marker in ('good try', 'you are close', "you're close", 'we just found', 'student:', 'msalisia:')):
            return ''
        return text[:80]

    def _most_recent_subject(self, report: ChildReportResponse) -> str | None:
        if report.recent_tutor_sessions:
            return report.recent_tutor_sessions[0].subject
        if report.recent_assessments:
            return report.recent_assessments[0].subject
        assessed = next((item.subject for item in report.subject_progress if item.assessment_count > 0), None)
        return assessed or (report.subject_progress[0].subject if report.subject_progress else None)

    def _display_date(self, value: str | None) -> str:
        if not value:
            return 'Recently'
        return value[:10]

    def _subject_label(self, subject: str | None) -> str:
        return 'Reading' if subject == 'ELA' else (subject or 'Learning')
