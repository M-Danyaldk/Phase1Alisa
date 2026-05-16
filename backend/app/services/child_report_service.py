from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.child_report import AssessmentSummary, ChildReportResponse, SubjectProgress, TutorSessionSummary, WeeklyReportEmailPreview
from .app_data_service import AppDataService
from .supabase_client import SupabaseClient, SupabaseClientError


class ChildReportService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def report_for_child(self, parent_id: str, child_id: str, period: str = 'all', subject: str = 'All') -> ChildReportResponse:
        child = await self._get_child(parent_id, child_id)
        subject_filter = subject if subject in ('Math', 'ELA', 'Writing') else 'All'
        assessments = self._filter_rows(await self._assessment_rows(child_id), period, subject_filter, 'created_at')
        threads = self._filter_rows(await self._thread_rows(parent_id, child_id), period, subject_filter, 'updated_at')
        messages = self._filter_rows(await self._message_rows(parent_id, child_id), period, subject_filter, 'created_at')

        subject_progress = self._subject_progress(child, assessments, threads, messages)
        if subject_filter != 'All':
            subject_progress = [item for item in subject_progress if item.subject == subject_filter]
        recent_assessments = [self._assessment_summary(row) for row in assessments[:6]]
        recent_sessions = self._session_summaries(threads, messages)
        strengths = self._strengths(subject_progress, recent_assessments)
        weak_areas = self._weak_areas(recent_assessments)
        next_steps = self._next_steps(child, subject_progress, weak_areas)
        last_updated = self._last_updated(assessments, threads, messages)
        questions_practiced = len([message for message in messages if message.get('role') == 'student'])
        lessons_completed = len([thread for thread in threads if (thread.get('updated_at') or thread.get('created_at'))])

        return ChildReportResponse(
            child_id=child['id'],
            child_name=child['name'],
            grade_level=child['grade_level'],
            report_period=period,
            subject_filter=subject_filter,
            current_learning_level=self._current_level(child, subject_progress),
            last_updated_at=last_updated,
            lessons_completed=lessons_completed,
            questions_practiced=questions_practiced,
            assessment_status=self._assessment_status(recent_assessments),
            overall_summary=self._overall_summary(child, assessments, threads, messages),
            weekly_progress=self._weekly_progress(threads, messages),
            time_spent_learning=self._time_spent(messages),
            brain_break_summary='Ms. Alisia supports healthy learning. After 2 hours of continuous tutoring, students receive a 30-minute Brain Break so they can rest, stretch, and return ready to learn.',
            subject_progress=subject_progress,
            recent_assessments=recent_assessments,
            recent_tutor_sessions=recent_sessions,
            strengths=strengths,
            weak_areas=weak_areas,
            recommended_next_steps=next_steps,
        )

    async def weekly_email_preview(self, parent_id: str, child_id: str) -> WeeklyReportEmailPreview:
        child = await self._get_child(parent_id, child_id)
        report = await self.report_for_child(parent_id, child_id, period='week', subject='All')
        return WeeklyReportEmailPreview(
            child_id=child_id,
            child_name=report.child_name,
            parent_id=parent_id,
            subject_line=f"Ms. Alisia weekly progress for {report.child_name}",
            greeting=f"Here is {report.child_name}'s weekly Ms. Alisia learning summary.",
            summary=report.overall_summary,
            subject_progress=report.subject_progress,
            strengths=report.strengths,
            weak_areas=report.weak_areas,
            recommended_next_steps=report.recommended_next_steps,
            brain_break_summary=report.brain_break_summary,
            generated_at=datetime.now(UTC).isoformat(),
        )

    async def save_report_snapshot(self, parent_id: str, child_id: str, period: str = 'week') -> dict:
        report = await self.report_for_child(parent_id, child_id, period=period, subject='All')
        payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'report_period': period,
            'summary': report.overall_summary,
            'strengths': report.strengths,
            'weak_areas': report.weak_areas,
            'recommended_next_steps': report.recommended_next_steps,
            'subject_progress': [item.model_dump() for item in report.subject_progress],
            'assessment_summary': [item.model_dump() for item in report.recent_assessments],
            'session_summary': [item.model_dump() for item in report.recent_tutor_sessions],
            'brain_break_summary': report.brain_break_summary,
            'generated_at': datetime.now(UTC).isoformat(),
        }
        try:
            records = await self.supabase.insert('report_snapshots', payload)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not save report snapshot.')
        return records[0]

    async def _get_child(self, parent_id: str, child_id: str) -> dict:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&status=neq.inactive&limit=1',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return records[0]

    async def _thread_rows(self, parent_id: str, child_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'chat_threads',
                f'user_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&order=updated_at.desc&limit=20',
            )
        except SupabaseClientError:
            return []

    async def _message_rows(self, parent_id: str, child_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'chat_messages',
                f'user_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&order=created_at.desc&limit=250',
            )
        except SupabaseClientError:
            return []

    async def _assessment_rows(self, child_id: str) -> list[dict]:
        return await AppDataService().list_assessments_for_child(child_id, limit=20)

    def _subject_progress(self, child: dict, assessments: list[dict], threads: list[dict], messages: list[dict]) -> list[SubjectProgress]:
        subjects = child.get('subjects') or ['Math', 'ELA', 'Writing']
        if isinstance(subjects, str):
            try:
                subjects = json.loads(subjects)
            except Exception:
                subjects = ['Math', 'ELA', 'Writing']

        assessments_by_subject: dict[str, list[dict]] = defaultdict(list)
        for row in assessments:
            assessments_by_subject[row.get('subject') or ''].append(row)

        threads_by_subject: dict[str, list[dict]] = defaultdict(list)
        for row in threads:
            threads_by_subject[row.get('subject') or ''].append(row)

        messages_by_subject: dict[str, list[dict]] = defaultdict(list)
        for row in messages:
            messages_by_subject[row.get('subject') or ''].append(row)

        progress: list[SubjectProgress] = []
        for subject in subjects:
            assessment_rows = assessments_by_subject.get(subject, [])
            thread_rows = threads_by_subject.get(subject, [])
            message_rows = messages_by_subject.get(subject, [])
            level = assessment_rows[0]['estimated_level'] if assessment_rows else f'{child["grade_level"]} - not assessed yet'
            gaps = self._json_list(assessment_rows[0].get('learning_gaps')) if assessment_rows else []
            last_activity = None
            if thread_rows:
                last_activity = thread_rows[0].get('updated_at')
            elif message_rows:
                last_activity = message_rows[0].get('created_at')
            progress.append(SubjectProgress(
                subject=subject,
                level=level,
                progress_percentage=self._progress_percent(len(assessment_rows), len(thread_rows), len(message_rows)),
                current_topic=thread_rows[0].get('topic') if thread_rows else None,
                strong_area=self._strong_area(subject, len(message_rows), assessment_rows),
                needs_review=gaps[0] if gaps else 'No specific review topic recorded yet.',
                recent_improvement=self._recent_improvement(subject, len(message_rows), len(assessment_rows)),
                completed_lessons=max(0, len(thread_rows)),
                assessment_count=len(assessment_rows),
                chat_count=len(thread_rows),
                message_count=len(message_rows),
                last_activity_at=last_activity,
            ))
        return progress

    def _assessment_summary(self, row: dict) -> AssessmentSummary:
        return AssessmentSummary(
            id=row.get('id'),
            subject=row.get('subject') or 'Unknown',
            estimated_level=row.get('estimated_level') or 'Not assessed yet',
            learning_gaps=self._json_list(row.get('learning_gaps')),
            recommended_progression=self._json_list(row.get('recommended_progression')),
            parent_summary=row.get('parent_summary'),
            created_at=row.get('created_at'),
        )

    def _session_summaries(self, threads: list[dict], messages: list[dict]) -> list[TutorSessionSummary]:
        count_by_thread: dict[str, int] = defaultdict(int)
        for message in messages:
            if message.get('thread_id'):
                count_by_thread[message['thread_id']] += 1
        return [
            TutorSessionSummary(
                thread_id=thread['id'],
                subject=thread.get('subject') or 'Unknown',
                topic=thread.get('topic'),
                title=thread.get('title'),
                message_count=count_by_thread.get(thread['id'], 0),
                time_spent=self._time_spent_for_count(count_by_thread.get(thread['id'], 0)),
                hints_used=self._estimated_hints(thread['id'], messages),
                practice_attempts=len([message for message in messages if message.get('thread_id') == thread['id'] and message.get('role') == 'student']),
                improvement_status='Improvement can be reviewed from the saved chat history.',
                next_step=f'Continue practicing {thread.get("topic") or thread.get("subject") or "this skill"} with a short session.',
                last_activity_at=thread.get('updated_at'),
            )
            for thread in threads[:8]
        ]

    def _strengths(self, progress: list[SubjectProgress], assessments: list[AssessmentSummary]) -> list[str]:
        strengths: list[str] = []
        for item in assessments:
            if item.estimated_level and 'needs review' not in item.estimated_level.lower():
                strengths.append(f'{item.subject}: working at {item.estimated_level}.')
        for item in progress:
            if item.message_count >= 4:
                strengths.append(f'{item.subject}: active practice with Ms. Alisia.')
        return strengths[:5] or ['Complete an assessment to identify strong areas.']

    def _weak_areas(self, assessments: list[AssessmentSummary]) -> list[str]:
        weak: list[str] = []
        for item in assessments:
            weak.extend([f'{item.subject}: {gap}' for gap in item.learning_gaps[:2]])
        return weak[:6] or ['No weak areas recorded yet. Start with a quick assessment.']

    def _next_steps(self, child: dict, progress: list[SubjectProgress], weak_areas: list[str]) -> list[str]:
        steps: list[str] = []
        if weak_areas and not weak_areas[0].startswith('No weak areas'):
            steps.append('Review the first weak area with a short guided tutoring session.')
        missing = [item.subject for item in progress if item.assessment_count == 0]
        if missing:
            steps.append(f'Run a quick {missing[0]} assessment for {child["name"]}.')
        steps.append('Practice one skill at a time and keep sessions short and consistent.')
        return steps[:4]

    def _overall_summary(self, child: dict, assessments: list[dict], threads: list[dict], messages: list[dict]) -> str:
        if not assessments and not threads:
            return f'{child["name"]} has a profile ready. Start an assessment or learning session to build the first report.'
        return f'{child["name"]} has {len(assessments)} assessment record(s), {len(threads)} saved chat thread(s), and {len(messages)} recent tutor message(s).'

    def _weekly_progress(self, threads: list[dict], messages: list[dict]) -> str:
        if not threads and not messages:
            return 'No learning activity recorded yet.'
        return f'{len(threads)} recent chat thread(s) and {len(messages)} recent message(s) are available for review.'

    def _time_spent(self, messages: list[dict]) -> str:
        minutes = max(0, round(len(messages) * 0.75))
        if minutes <= 0:
            return 'No tracked learning time yet.'
        return f'About {minutes} minute(s), estimated from tutor messages.'

    def _time_spent_for_count(self, message_count: int) -> str:
        minutes = max(0, round(message_count * 0.75))
        return f'About {minutes} minute(s)' if minutes else 'Not tracked yet'

    def _filter_rows(self, rows: list[dict], period: str, subject: str, date_key: str) -> list[dict]:
        filtered = rows
        if subject != 'All':
            filtered = [row for row in filtered if row.get('subject') == subject]
        start = self._period_start(period)
        if not start:
            return filtered
        return [row for row in filtered if self._parse_date(row.get(date_key)) >= start]

    def _period_start(self, period: str) -> datetime | None:
        now = datetime.now(UTC)
        if period == 'week':
            return now - timedelta(days=7)
        if period == 'month':
            return now - timedelta(days=30)
        return None

    def _parse_date(self, value: str | None) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=UTC)
        try:
            cleaned = value.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            try:
                return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
            except Exception:
                return datetime.min.replace(tzinfo=UTC)

    def _last_updated(self, assessments: list[dict], threads: list[dict], messages: list[dict]) -> str | None:
        values = [row.get('created_at') for row in assessments] + [row.get('updated_at') for row in threads] + [row.get('created_at') for row in messages]
        dates = [self._parse_date(value) for value in values if value]
        if not dates:
            return None
        return max(dates).isoformat()

    def _current_level(self, child: dict, progress: list[SubjectProgress]) -> str:
        assessed = [item.level for item in progress if 'not assessed' not in item.level.lower()]
        if assessed:
            return assessed[0]
        return f'{child["grade_level"]} - learning path not assessed yet'

    def _assessment_status(self, assessments: list[AssessmentSummary]) -> str:
        if not assessments:
            return 'No assessment completed yet. Start an assessment to create a personalized learning path.'
        latest = assessments[0]
        return f'Latest assessment: {latest.subject} at {latest.estimated_level}.'

    def _progress_percent(self, assessment_count: int, chat_count: int, message_count: int) -> int:
        score = assessment_count * 20 + chat_count * 12 + message_count * 2
        return max(0, min(score, 95))

    def _strong_area(self, subject: str, message_count: int, assessments: list[dict]) -> str:
        if assessments:
            return f'{subject} assessment work is recorded.'
        if message_count >= 4:
            return f'{subject} practice consistency is building.'
        return 'More activity is needed to identify a strong area.'

    def _recent_improvement(self, subject: str, message_count: int, assessment_count: int) -> str:
        if assessment_count and message_count:
            return f'{subject} has both assessment and tutoring activity.'
        if message_count:
            return f'{subject} tutoring practice has started.'
        return 'No recent improvement data yet.'

    def _estimated_hints(self, thread_id: str, messages: list[dict]) -> int:
        thread_messages = [message for message in messages if message.get('thread_id') == thread_id and message.get('role') == 'msalisia']
        return len([message for message in thread_messages if 'hint' in (message.get('content') or '').lower()])

    def _json_list(self, value: object) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        try:
            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            return [str(value)]
        return []
