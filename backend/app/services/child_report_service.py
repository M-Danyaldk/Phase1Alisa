from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
import re
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.child_report import AssessmentSummary, ChildReportResponse, LearningMemorySummary, SubjectProgress, TutorSessionSummary, WeeklyReportEmailPreview
from ..schemas.homework import HomeworkHistoryItem
from .app_data_service import AppDataService
from .supabase_client import SupabaseClient, SupabaseClientError
from .working_level_override_service import WorkingLevelOverrideService
from .learning_memory_service import LearningMemoryService


class ChildReportService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def report_for_child(self, parent_id: str, child_id: str, period: str = 'all', subject: str = 'All') -> ChildReportResponse:
        child = await self._get_child(parent_id, child_id)
        subject_filter = subject if subject in ('Math', 'ELA', 'Writing') else 'All'
        assessments = self._filter_rows(await self._assessment_rows(child_id), period, subject_filter, 'created_at')
        threads = self._filter_rows(await self._thread_rows(parent_id, child_id), period, subject_filter, 'updated_at')
        messages = self._filter_rows(await self._message_rows(parent_id, child_id), period, subject_filter, 'created_at')
        homework_rows = self._filter_rows(await self._homework_rows(child_id), period, subject_filter, 'created_at')
        memory_rows = self._filter_rows(await LearningMemoryService().recent_for_child(parent_id, child_id, limit=10), period, subject_filter, 'updated_at')

        overrides = await WorkingLevelOverrideService().active_overrides_for_child(child_id)
        subject_progress = self._subject_progress(child, assessments, threads, messages, overrides)
        if subject_filter != 'All':
            subject_progress = [item for item in subject_progress if item.subject == subject_filter]
        recent_assessments = [self._assessment_summary(row) for row in assessments[:6]]
        recent_sessions = self._session_summaries(threads, messages)
        strengths = self._strengths(subject_progress, recent_assessments)
        weak_areas = self._weak_areas(recent_assessments)
        recent_memory = [self._memory_summary(row) for row in memory_rows[:6]]
        next_steps = self._next_steps(child, subject_progress, weak_areas, recent_memory)
        personalized_observation = self._personalized_observation(child, recent_assessments, recent_memory, threads, homework_rows)
        strength_recognition = self._strength_recognition(child, recent_assessments, strengths, recent_memory)
        next_focus = self._next_focus(child, recent_assessments, weak_areas, recent_memory)
        support_plan = self._support_plan(child, next_focus, recent_memory, threads)
        exceptional_performance = self._exceptional_performance(child, recent_assessments)
        last_updated = self._last_updated(assessments, threads, messages, homework_rows, memory_rows)
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
            overall_summary=self._overall_summary(child, recent_assessments, recent_memory, threads, messages),
            personalized_observation=personalized_observation,
            strength_recognition=strength_recognition,
            next_focus=next_focus,
            support_plan=support_plan,
            exceptional_performance=exceptional_performance,
            weekly_progress=self._weekly_progress(threads, messages),
            time_spent_learning=self._time_spent(messages),
            brain_break_summary='Ms. Alisia supports healthy learning. After 2 hours of continuous tutoring, students receive a 30-minute Brain Break so they can rest, stretch, and return ready to learn.',
            subject_progress=subject_progress,
            recent_assessments=recent_assessments,
            recent_tutor_sessions=recent_sessions,
            recent_learning_memory=recent_memory,
            homework_uploads=[self._homework_summary(row, child.get('name')) for row in homework_rows[:10]],
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
            'homework_uploads': [item.model_dump() for item in report.homework_uploads],
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
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&limit=1',
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

    async def _homework_rows(self, child_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'homework_uploads',
                f'child_id=eq.{quote(child_id)}&parent_report_visible=eq.true&order=created_at.desc&limit=25',
            )
        except SupabaseClientError:
            return []

    def _subject_progress(self, child: dict, assessments: list[dict], threads: list[dict], messages: list[dict], overrides: dict[str, dict] | None = None) -> list[SubjectProgress]:
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
            enrolled_grade = child['grade_level']
            assessed_level = assessment_rows[0]['estimated_level'] if assessment_rows else None
            override = (overrides or {}).get(subject)
            override_level = (override or {}).get('approved_working_level')
            working_level = override_level or assessed_level
            level = self._display_subject_level(enrolled_grade, working_level, bool(override_level), bool(assessed_level))
            working_level_source = 'parent_override' if override_level else ('assessment' if assessed_level else 'enrolled_grade')
            gaps = self._json_list(assessment_rows[0].get('learning_gaps')) if assessment_rows else []
            last_activity = None
            if thread_rows:
                last_activity = thread_rows[0].get('updated_at')
            elif message_rows:
                last_activity = message_rows[0].get('created_at')
            progress.append(SubjectProgress(
                subject=subject,
                level=level,
                display_level=level,
                working_level=working_level,
                enrolled_grade=enrolled_grade,
                working_level_source=working_level_source,
                override_active=bool(override_level),
                override_level=override_level,
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
            score_label=row.get('score_label'),
            strengths=self._json_list(row.get('strengths')),
            learning_gaps=self._json_list(row.get('learning_gaps')),
            recommended_progression=self._json_list(row.get('recommended_progression')),
            recommended_next_topics=self._json_list(row.get('recommended_next_topics')),
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

    def _memory_summary(self, row: dict) -> LearningMemorySummary:
        return LearningMemorySummary(
            id=row.get('id'),
            subject=row.get('subject') or 'Unknown',
            topic=row.get('topic'),
            worked_on=row.get('worked_on'),
            struggled_with=row.get('struggled_with'),
            mastered=row.get('mastered'),
            next_step=row.get('next_step'),
            child_facing_summary=row.get('child_facing_summary'),
            parent_facing_summary=row.get('parent_facing_summary'),
            updated_at=row.get('updated_at') or row.get('created_at'),
        )

    def _homework_summary(self, row: dict, child_name: str | None) -> HomeworkHistoryItem:
        metadata = row.get('metadata') or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        return HomeworkHistoryItem.model_validate({
            'id': row.get('id'),
            'child_id': row.get('child_id'),
            'child_name': child_name,
            'file_name': row.get('file_name'),
            'file_type': row.get('file_type'),
            'mime_type': metadata.get('mime_type'),
            'file_size_bytes': row.get('file_size_bytes'),
            'upload_status': row.get('upload_status'),
            'ai_validation_status': row.get('ai_validation_status'),
            'ai_validation_summary': row.get('ai_validation_summary'),
            'is_unclear': row.get('unclear_image', False),
            'detected_subject': row.get('detected_subject'),
            'suggested_next_step': metadata.get('suggested_next_step'),
            'source': row.get('source'),
            'uploader_type': row.get('uploader_type'),
            'created_at': row.get('created_at'),
        })

    def _strengths(self, progress: list[SubjectProgress], assessments: list[AssessmentSummary]) -> list[str]:
        strengths: list[str] = []
        for item in assessments:
            if item.strengths:
                strengths.extend([f'{self._subject_label(item.subject)}: {self._safe_parent_text(strength)}' for strength in item.strengths[:2]])
            elif item.estimated_level and 'needs review' not in item.estimated_level.lower():
                strengths.append(f'{self._subject_label(item.subject)}: working at {self._safe_parent_text(item.estimated_level)}.')
        for item in progress:
            if item.message_count >= 4:
                strengths.append(f'{self._subject_label(item.subject)}: active practice with Ms. Alisia.')
        return strengths[:5] or ["Complete an assessment to identify this child's strong areas."]

    def _weak_areas(self, assessments: list[AssessmentSummary]) -> list[str]:
        growth: list[str] = []
        for item in assessments:
            growth.extend([f'{self._subject_label(item.subject)}: {self._safe_parent_text(gap)}' for gap in item.learning_gaps[:2]])
        return growth[:6] or ['No growth areas recorded yet. Start with a quick assessment.']

    def _next_steps(self, child: dict, progress: list[SubjectProgress], weak_areas: list[str], memory: list[LearningMemorySummary] | None = None) -> list[str]:
        steps: list[str] = []
        if memory:
            latest_next = memory[0].next_step
            if latest_next:
                safe_next = self._safe_parent_text(latest_next)
                if safe_next:
                    steps.append(safe_next)
        if weak_areas and not weak_areas[0].startswith('No growth areas'):
            steps.append('Use the first growth area as the next short guided tutoring focus.')
        missing = [item.subject for item in progress if item.assessment_count == 0]
        if missing:
            steps.append(f'Run a quick {self._subject_label(missing[0])} assessment for {child["name"]}.')
        steps.append('Practice one skill at a time and keep sessions short and consistent.')
        return steps[:4]

    def _overall_summary(self, child: dict, assessments: list[AssessmentSummary], memory: list[LearningMemorySummary], threads: list[dict], messages: list[dict]) -> str:
        if not assessments and not threads:
            return f'{child["name"]} has a profile ready. Start an assessment or learning session to build the first report.'
        latest = assessments[0] if assessments else None
        if latest:
            strength = self._first_safe(latest.strengths) or 'steady effort'
            next_focus = self._first_safe(latest.recommended_next_topics) or self._first_safe(latest.learning_gaps) or self._first_safe(latest.recommended_progression) or 'one focused practice skill'
            return f'{child["name"]} showed {strength} in {self._subject_label(latest.subject)}. The next helpful step is practicing {next_focus} with steady, guided support.'
        if memory:
            latest_memory = memory[0]
            return f'{child["name"]} recently worked on {latest_memory.worked_on or latest_memory.topic or "a learning session"}. Ms. Alisia will use this history to keep the next session focused and encouraging.'
        return f'{child["name"]} has started tutoring with Ms. Alisia. More assessment and practice activity will make the report more personalized.'

    def _personalized_observation(self, child: dict, assessments: list[AssessmentSummary], memory: list[LearningMemorySummary], threads: list[dict], homework_rows: list[dict]) -> str:
        name = child['name']
        latest = assessments[0] if assessments else None
        if latest:
            subject = self._subject_label(latest.subject)
            strength = self._first_safe(latest.strengths) or 'steady focus'
            next_focus = self._first_safe(latest.recommended_next_topics) or self._first_safe(latest.learning_gaps) or self._first_safe(latest.recommended_progression)
            if next_focus:
                return f'Ms. Alisia noticed that {name} showed {strength} in {subject}. The next helpful step is practicing {next_focus} with clear, guided support.'
            return f'Ms. Alisia noticed that {name} showed {strength} in {subject}. The next session can build on that progress with a short guided practice path.'
        if memory:
            latest_memory = memory[0]
            focus = latest_memory.worked_on or latest_memory.topic or 'a recent learning session'
            next_step = self._safe_parent_text(latest_memory.next_step) or self._safe_parent_text(latest_memory.topic) or 'the next small practice step'
            return f'Ms. Alisia remembers that {name} worked on {focus}. The next session can continue with {next_step}.'
        if homework_rows:
            return f'Ms. Alisia has homework activity saved for {name}. Reports will become more specific as tutoring and check-ins continue.'
        if threads:
            return f'{name} has started learning with Ms. Alisia. A quick check-in will help turn this activity into a more personalized plan.'
        return f'{name} has a profile ready. Start a check-in or learning session so Ms. Alisia can learn how to support them.'

    def _strength_recognition(self, child: dict, assessments: list[AssessmentSummary], strengths: list[str], memory: list[LearningMemorySummary]) -> str:
        name = child['name']
        exceptional = self._exceptional_performance(child, assessments)
        if exceptional:
            return exceptional
        latest_strength = self._first_safe(strengths)
        if latest_strength:
            if latest_strength == "Complete an assessment to identify this child's strong areas.":
                return latest_strength
            return f'A clear strength to celebrate: {name} is building confidence with {latest_strength}.'
        if memory and memory[0].mastered:
            return f'A clear strength to celebrate: {name} is getting stronger with {self._safe_parent_text(memory[0].mastered)}.'
        return f'A clear strength to celebrate: {name} is ready to begin building a personalized learning path.'

    def _next_focus(self, child: dict, assessments: list[AssessmentSummary], weak_areas: list[str], memory: list[LearningMemorySummary]) -> str:
        name = child['name']
        if memory:
            safe_memory_step = self._safe_parent_text(memory[0].next_step) or self._safe_parent_text(memory[0].topic)
            if safe_memory_step:
                return f'Next focus: {name} will benefit from {safe_memory_step}.'
        latest = assessments[0] if assessments else None
        if latest:
            focus = self._first_safe(latest.recommended_next_topics) or self._first_safe(latest.learning_gaps) or self._first_safe(latest.recommended_progression)
            if focus:
                return f'Next focus: {name} will benefit from more guided practice with {focus}.'
        if weak_areas and not weak_areas[0].startswith('No growth areas'):
            return f'Next focus: {name} will benefit from more guided practice with {self._safe_parent_text(weak_areas[0])}.'
        return f'Next focus: {name} can start with one short check-in so Ms. Alisia can choose the right first skill.'

    def _support_plan(self, child: dict, next_focus: str, memory: list[LearningMemorySummary], threads: list[dict]) -> str:
        name = child['name']
        if memory:
            return f'Ms. Alisia will use {name}\'s saved learning memory to keep the next session connected to prior work and paced one step at a time.'
        if threads:
            return f'Ms. Alisia will use {name}\'s saved tutoring history to keep practice focused, encouraging, and easy to continue.'
        return f'Ms. Alisia will use this information to guide {name}\'s next session with the right level of support.'

    def _exceptional_performance(self, child: dict, assessments: list[AssessmentSummary]) -> str | None:
        if not assessments:
            return None
        latest = assessments[0]
        label = f'{latest.score_label or ""} {latest.estimated_level or ""}'.lower()
        if any(marker in label for marker in ('excellent', 'advanced', 'strong', 'master', 'above', 'exceptional')):
            return f'Excellent work - {child["name"]} showed strong understanding in {self._subject_label(latest.subject)} and may be ready for a more challenging next step.'
        return None

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
            filtered = [row for row in filtered if (row.get('subject') or row.get('detected_subject')) == subject]
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

    def _last_updated(self, assessments: list[dict], threads: list[dict], messages: list[dict], homework_rows: list[dict] | None = None, memory_rows: list[dict] | None = None) -> str | None:
        values = [row.get('created_at') for row in assessments] + [row.get('updated_at') for row in threads] + [row.get('created_at') for row in messages]
        values += [row.get('created_at') for row in (homework_rows or [])]
        values += [row.get('updated_at') or row.get('created_at') for row in (memory_rows or [])]
        dates = [self._parse_date(value) for value in values if value]
        if not dates:
            return None
        return max(dates).isoformat()

    def _current_level(self, child: dict, progress: list[SubjectProgress]) -> str:
        override = next((item for item in progress if item.override_active and item.override_level), None)
        if override:
            focus = self._practice_focus_label(override.override_level or '')
            return f'{child["grade_level"]} - parent-set practice focus: {focus}' if focus else f'{child["grade_level"]} - parent-set practice focus'
        assessed = [item for item in progress if item.working_level and 'not assessed' not in item.working_level.lower()]
        if assessed:
            focus = self._practice_focus_label(assessed[0].working_level or '')
            return f'{child["grade_level"]} - practice focus: {focus}' if focus else f'{child["grade_level"]} - learning path started'
        return f'{child["grade_level"]} - learning path not assessed yet'

    def _display_subject_level(self, enrolled_grade: str, working_level: str | None, override_active: bool, assessed: bool) -> str:
        enrolled = enrolled_grade or 'Enrolled grade'
        if not working_level:
            return f'{enrolled} - not assessed yet'
        focus = self._practice_focus_label(working_level)
        if not focus:
            return f'{enrolled} - learning path started'
        if override_active:
            return f'{enrolled} - parent-set practice focus: {focus}'
        if assessed:
            return f'{enrolled} - practice focus: {focus}'
        return f'{enrolled} - learning path started'

    def _practice_focus_label(self, value: str) -> str:
        text = self._safe_parent_text(value or '').strip()
        if not text:
            return ''
        lowered = text.lower()
        if 'not assessed' in lowered:
            return ''
        if text.lower().startswith('grade '):
            parts = text.split(maxsplit=2)
            text = parts[2] if len(parts) >= 3 else ''
            text = text.replace('–', '-').replace('—', '-').lstrip(' -:').strip()
        return text or 'Foundational practice'

    def _assessment_status(self, assessments: list[AssessmentSummary]) -> str:
        if not assessments:
            return 'No assessment completed yet. Start an assessment to create a personalized learning path.'
        latest = assessments[0]
        focus = self._practice_focus_label(latest.estimated_level or '')
        label = latest.score_label or (f'practice focus: {focus}' if focus else 'Learning path saved')
        return f'Latest assessment: {self._subject_label(latest.subject)} - {self._safe_parent_text(label)}.'

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

    def _subject_label(self, subject: str | None) -> str:
        return 'Reading' if subject == 'ELA' else (subject or 'Learning')

    def _first_safe(self, values: list[str] | None) -> str:
        for value in values or []:
            safe = self._safe_parent_text(value)
            if safe:
                return safe
        return ''

    def _safe_parent_text(self, value: object) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        text = re.sub(r'[*_`#>\[\]()]', '', text)
        text = re.sub(r'\s+', ' ', text).strip(' .,:;-')
        if not text:
            return ''
        lowered = text.lower()
        raw_prompt_markers = (
            'would you like',
            'do you want to',
            'is it a specific',
            'tell me what',
            'what would you like',
            'or something else',
            'student:',
            'msalisia:',
            'good try',
            "you're close",
            'we just found',
            'i need help',
            "i don't know",
            'i dont know',
        )
        if any(marker in lowered for marker in raw_prompt_markers):
            return ''
        if text.endswith('?') and any(lowered.startswith(prefix) for prefix in ('what ', 'which ', 'why ', 'how ', 'is ', 'are ', 'do ', 'does ', 'can ', 'would ')):
            return ''
        replacements = {
            'weaknesses': 'growth areas',
            'weakness': 'growth area',
            'weak': 'needs more practice',
            'failed': 'needs another try',
            'failure': 'needs another try',
            'poor': 'still building',
            'deficient': 'still building',
            'diagnostic': 'learning',
            'clinical': 'learning',
            'below grade level': 'ready for guided practice',
            'below level': 'ready for guided practice',
            'learning gaps': 'growth areas',
            'learning gap': 'growth area',
        }
        for old, new in replacements.items():
            text = text.replace(old, new).replace(old.title(), new)
        return text
