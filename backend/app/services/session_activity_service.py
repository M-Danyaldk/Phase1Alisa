import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.session_activity import SessionStatusResponse
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

BRAIN_BREAK_LIMIT_SECONDS = 2 * 60 * 60
BRAIN_BREAK_DURATION_SECONDS = 30 * 60
INACTIVITY_THRESHOLD_SECONDS = 2 * 60
WARNING_THRESHOLDS = {
    'warning_30': 30 * 60,
    'warning_10': 10 * 60,
    'warning_5': 5 * 60,
}


class SessionActivityService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def status(self, parent_id: str, child_id: str) -> SessionStatusResponse:
        counter = await self._counter(parent_id, child_id)
        counter = await self._complete_break_if_ready(counter)
        session = await self._active_or_latest_session(parent_id, child_id)
        return self._status_response(child_id, session, counter)

    async def ensure_can_tutor(self, parent_id: str, child_id: str) -> None:
        counter = await self._counter(parent_id, child_id)
        counter = await self._complete_break_if_ready(counter)
        if self._break_active(counter):
            raise HTTPException(status_code=423, detail='Great work today! Your brain needs a short rest to absorb everything you have learned. Take a 30-minute break and come back ready to learn even more!')

    async def record_activity(
        self,
        parent_id: str,
        child_id: str,
        subject: str = 'Math',
        topic: str = 'general practice',
        session_id: str | None = None,
        event_type: str = 'activity',
    ) -> SessionStatusResponse:
        await self.ensure_can_tutor(parent_id, child_id)
        now = self._now()
        session = await self._session(parent_id, child_id, subject, topic, session_id)
        await self._insert_activity_event(parent_id, child_id, session.get('id'), event_type if event_type in {'activity', 'message_sent'} else 'activity')
        await self.supabase.update('learning_sessions', {'id': f'eq.{session["id"]}'}, {
            'session_status': 'active',
            'last_activity_at': now.isoformat(),
            'resumed_at': now.isoformat() if session.get('session_status') == 'paused' else session.get('resumed_at'),
            'updated_at': now.isoformat(),
        })
        counter = await self._counter(parent_id, child_id)
        return self._status_response(child_id, {**session, 'session_status': 'active', 'last_activity_at': now.isoformat()}, counter)

    async def record_inactivity_nudge(self, parent_id: str, child_id: str, session_id: str | None = None) -> SessionStatusResponse:
        session = await self._require_session(parent_id, child_id, session_id)
        now = self._now()
        await self._insert_activity_event(parent_id, child_id, session.get('id'), 'inactivity_nudge', inactive_seconds_delta=INACTIVITY_THRESHOLD_SECONDS)
        await self.supabase.update('learning_sessions', {'id': f'eq.{session["id"]}'}, {
            'inactivity_nudge_sent_at': now.isoformat(),
            'updated_at': now.isoformat(),
        })
        counter = await self._counter(parent_id, child_id)
        return self._status_response(child_id, {**session, 'inactivity_nudge_sent_at': now.isoformat()}, counter)

    async def pause_inactive(self, parent_id: str, child_id: str, session_id: str | None = None, inactive_seconds: int = 180) -> SessionStatusResponse:
        session = await self._require_session(parent_id, child_id, session_id)
        now = self._now()
        inactive_delta = max(0, min(inactive_seconds, 15 * 60))
        inactive_total = int(session.get('inactive_time_seconds') or 0) + inactive_delta
        await self.supabase.update('learning_sessions', {'id': f'eq.{session["id"]}'}, {
            'session_status': 'paused',
            'inactive_time_seconds': inactive_total,
            'auto_paused_at': now.isoformat(),
            'updated_at': now.isoformat(),
        })
        await self._insert_activity_event(parent_id, child_id, session.get('id'), 'auto_pause', inactive_seconds_delta=inactive_delta)
        await self._insert_pause_event(parent_id, child_id, session, 'inactivity', inactive_total)
        await self._update_counter_inactive(parent_id, child_id, inactive_delta)
        counter = await self._counter(parent_id, child_id)
        return self._status_response(child_id, {**session, 'session_status': 'paused', 'inactive_time_seconds': inactive_total}, counter)

    async def resume(self, parent_id: str, child_id: str, session_id: str | None = None) -> SessionStatusResponse:
        await self.ensure_can_tutor(parent_id, child_id)
        session = await self._active_or_latest_session(parent_id, child_id)
        if session_id:
            session = await self._require_session(parent_id, child_id, session_id)
        if not session:
            session = await self._create_session(parent_id, child_id, 'Math', 'general practice')
        now = self._now()
        await self.supabase.update('learning_sessions', {'id': f'eq.{session["id"]}'}, {
            'session_status': 'active',
            'resumed_at': now.isoformat(),
            'last_activity_at': now.isoformat(),
            'updated_at': now.isoformat(),
        })
        await self.supabase.update('session_pause_events', {
            'learning_session_id': f'eq.{session["id"]}',
            'resumed_at': 'is.null',
        }, {
            'resumed_at': now.isoformat(),
            'resumed_from_pause': True,
            'updated_at': now.isoformat(),
        })
        await self._insert_activity_event(parent_id, child_id, session.get('id'), 'resume')
        counter = await self._counter(parent_id, child_id)
        return self._status_response(child_id, {**session, 'session_status': 'active'}, counter)

    async def exchange_complete(
        self,
        parent_id: str,
        child_id: str,
        subject: str = 'Math',
        topic: str = 'general practice',
        session_id: str | None = None,
    ) -> SessionStatusResponse:
        await self.ensure_can_tutor(parent_id, child_id)
        session = await self._session(parent_id, child_id, subject, topic, session_id)
        now = self._now()
        last_activity = self._parse_datetime(session.get('last_activity_at')) or now
        active_delta = max(0, min(int((now - last_activity).total_seconds()), INACTIVITY_THRESHOLD_SECONDS))
        session_active_total = int(session.get('active_time_seconds') or 0) + active_delta
        await self.supabase.update('learning_sessions', {'id': f'eq.{session["id"]}'}, {
            'active_time_seconds': session_active_total,
            'last_activity_at': now.isoformat(),
            'updated_at': now.isoformat(),
        })
        await self._insert_activity_event(parent_id, child_id, session.get('id'), 'message_received', active_seconds_delta=active_delta)
        counter = await self._add_active_seconds(parent_id, child_id, active_delta)
        await self._add_weekly_active_seconds(parent_id, child_id, active_delta)
        counter = await self._apply_warnings_and_break(parent_id, child_id, session.get('id'), counter)
        return self._status_response(child_id, {**session, 'active_time_seconds': session_active_total}, counter)

    async def _session(self, parent_id: str, child_id: str, subject: str, topic: str, session_id: str | None = None) -> dict:
        if session_id:
            return await self._require_session(parent_id, child_id, session_id)
        session = await self._active_session(parent_id, child_id)
        if session:
            return session
        return await self._create_session(parent_id, child_id, subject, topic)

    async def _create_session(self, parent_id: str, child_id: str, subject: str, topic: str) -> dict:
        now = self._now().isoformat()
        payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'subject': subject if subject in {'Math', 'ELA', 'Writing'} else 'Math',
            'topic': topic,
            'session_started_at': now,
            'session_status': 'active',
            'learning_mode': 'text',
            'last_activity_at': now,
            'created_at': now,
            'updated_at': now,
        }
        records = await self.supabase.insert('learning_sessions', payload)
        if not records:
            raise HTTPException(status_code=503, detail='Ms. Alisia could not save this session right now. Please try again soon.')
        await self._increment_weekly_rhythm(parent_id, child_id)
        return records[0]

    async def _require_session(self, parent_id: str, child_id: str, session_id: str | None) -> dict:
        if not session_id:
            session = await self._active_session(parent_id, child_id)
            if session:
                return session
            raise HTTPException(status_code=404, detail='No active learning session was found.')
        records = await self.supabase.select('learning_sessions', f'id=eq.{quote(session_id)}&parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1')
        if not records:
            raise HTTPException(status_code=404, detail='This learning session was not found.')
        return records[0]

    async def _active_session(self, parent_id: str, child_id: str) -> dict | None:
        records = await self.supabase.select(
            'learning_sessions',
            f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&session_status=eq.active&order=updated_at.desc&limit=1',
        )
        return records[0] if records else None

    async def _active_or_latest_session(self, parent_id: str, child_id: str) -> dict | None:
        records = await self.supabase.select(
            'learning_sessions',
            f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&order=updated_at.desc&limit=1',
        )
        return records[0] if records else None

    async def _counter(self, parent_id: str, child_id: str) -> dict:
        today = self._today()
        records = await self.supabase.select('daily_learning_counters', f'child_id=eq.{quote(child_id)}&counter_date=eq.{quote(today)}&limit=1')
        if records:
            return records[0]
        now = self._now().isoformat()
        payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'counter_date': today,
            'daily_reset_at': now,
            'created_at': now,
            'updated_at': now,
        }
        records = await self.supabase.upsert('daily_learning_counters', payload, 'child_id,counter_date')
        return records[0] if records else payload

    async def _add_active_seconds(self, parent_id: str, child_id: str, active_delta: int) -> dict:
        counter = await self._counter(parent_id, child_id)
        total = int(counter.get('active_tutoring_seconds') or 0) + max(0, active_delta)
        records = await self.supabase.update('daily_learning_counters', {'id': f'eq.{counter["id"]}'}, {
            'active_tutoring_seconds': total,
            'updated_at': self._now().isoformat(),
        })
        return records[0] if records else {**counter, 'active_tutoring_seconds': total}

    async def _update_counter_inactive(self, parent_id: str, child_id: str, inactive_delta: int) -> None:
        counter = await self._counter(parent_id, child_id)
        await self.supabase.update('daily_learning_counters', {'id': f'eq.{counter["id"]}'}, {
            'inactive_seconds': int(counter.get('inactive_seconds') or 0) + max(0, inactive_delta),
            'updated_at': self._now().isoformat(),
        })

    async def _increment_weekly_rhythm(self, parent_id: str, child_id: str) -> None:
        rhythm = await self._weekly_rhythm(parent_id, child_id)
        if not rhythm:
            return
        session_count = int(rhythm.get('session_count') or 0) + 1
        label, child_message, parent_summary = self._weekly_rhythm_copy(session_count)
        payload = {
            **rhythm,
            'session_count': session_count,
            'achievement_label': label,
            'child_visible_message': child_message,
            'parent_visible_summary': parent_summary,
            'updated_at': self._now().isoformat(),
        }
        try:
            if rhythm.get('id'):
                await self.supabase.update('weekly_learning_rhythm', {'id': f'eq.{rhythm["id"]}'}, {
                    'session_count': session_count,
                    'achievement_label': label,
                    'child_visible_message': child_message,
                    'parent_visible_summary': parent_summary,
                    'updated_at': payload['updated_at'],
                })
            else:
                await self.supabase.upsert('weekly_learning_rhythm', payload, 'child_id,week_start_date')
        except SupabaseClientError as exc:
            if not self._missing_weekly_rhythm_table(exc):
                logger.warning('Could not update weekly learning rhythm for child %s: %s', child_id, exc)

    async def _add_weekly_active_seconds(self, parent_id: str, child_id: str, active_delta: int) -> None:
        rhythm = await self._weekly_rhythm(parent_id, child_id)
        if not rhythm:
            return
        active_seconds = int(rhythm.get('active_tutoring_seconds') or 0) + max(0, active_delta)
        try:
            if rhythm.get('id'):
                await self.supabase.update('weekly_learning_rhythm', {'id': f'eq.{rhythm["id"]}'}, {
                    'active_tutoring_seconds': active_seconds,
                    'updated_at': self._now().isoformat(),
                })
            else:
                session_count = max(1, int(rhythm.get('session_count') or 0))
                label, child_message, parent_summary = self._weekly_rhythm_copy(session_count)
                await self.supabase.upsert('weekly_learning_rhythm', {
                    **rhythm,
                    'session_count': session_count,
                    'achievement_label': label,
                    'child_visible_message': child_message,
                    'parent_visible_summary': parent_summary,
                    'active_tutoring_seconds': active_seconds,
                    'updated_at': self._now().isoformat(),
                }, 'child_id,week_start_date')
        except SupabaseClientError as exc:
            if not self._missing_weekly_rhythm_table(exc):
                logger.warning('Could not update weekly active seconds for child %s: %s', child_id, exc)

    async def _weekly_rhythm(self, parent_id: str, child_id: str) -> dict:
        week_start = self._week_start()
        week_end = week_start + timedelta(days=6)
        try:
            records = await self.supabase.select('weekly_learning_rhythm', f'child_id=eq.{quote(child_id)}&week_start_date=eq.{quote(week_start.date().isoformat())}&limit=1')
            if records:
                return records[0]
        except SupabaseClientError as exc:
            if self._missing_weekly_rhythm_table(exc):
                return {}
            logger.warning('Could not load weekly learning rhythm for child %s: %s', child_id, exc)
            return {}
        now = self._now().isoformat()
        return {
            'parent_id': parent_id,
            'child_id': child_id,
            'week_start_date': week_start.date().isoformat(),
            'week_end_date': week_end.date().isoformat(),
            'session_count': 0,
            'active_tutoring_seconds': 0,
            'achievement_label': 'fresh_start',
            'child_visible_message': 'A fresh week is ready when you are. No pressure, just one good step.',
            'parent_visible_summary': 'Fresh Start: no sessions yet this week.',
            'created_at': now,
            'updated_at': now,
        }

    def _weekly_rhythm_copy(self, session_count: int) -> tuple[str, str, str]:
        if session_count >= 5:
            return ('superstar', 'You showed up a lot this week. Amazing effort. A little rest helps your brain keep all that learning strong.', 'Superstar: 5+ sessions this week. Encourage a healthy rest rhythm.')
        if session_count == 4:
            return ('perfect_week', 'Four learning sessions this week. That is a beautiful rhythm.', 'Perfect Week!: 4 sessions this week.')
        if session_count == 3:
            return ('strong_week', 'Three sessions this week. You are building a strong learning rhythm.', 'Strong Week!: 3 sessions this week.')
        if session_count >= 1:
            return ('getting_started', 'You started your learning rhythm this week. One step counts.', f'Getting Started: {session_count} session(s) this week.')
        return ('fresh_start', 'A fresh week is ready when you are. No pressure, just one good step.', 'Fresh Start: no sessions yet this week.')

    async def _apply_warnings_and_break(self, parent_id: str, child_id: str, session_id: str | None, counter: dict) -> dict:
        active_seconds = int(counter.get('active_tutoring_seconds') or 0)
        remaining = max(0, BRAIN_BREAK_LIMIT_SECONDS - active_seconds)
        updates: dict = {'updated_at': self._now().isoformat()}
        for event_type, threshold in WARNING_THRESHOLDS.items():
            column = f'{event_type.replace("warning_", "warning_")}_min_sent_at'
            if event_type == 'warning_30':
                column = 'warning_30_min_sent_at'
            elif event_type == 'warning_10':
                column = 'warning_10_min_sent_at'
            elif event_type == 'warning_5':
                column = 'warning_5_min_sent_at'
            if remaining <= threshold and not counter.get(column) and active_seconds < BRAIN_BREAK_LIMIT_SECONDS:
                timestamp = self._now().isoformat()
                updates[column] = timestamp
                await self._insert_brain_break_event(parent_id, child_id, session_id, counter.get('id'), event_type, active_seconds, False)
        if active_seconds >= BRAIN_BREAK_LIMIT_SECONDS and not self._break_active(counter):
            now = self._now()
            break_ends = now + timedelta(seconds=BRAIN_BREAK_DURATION_SECONDS)
            updates.update({
                'brain_break_required': True,
                'currently_locked_out': True,
                'break_started_at': now.isoformat(),
                'break_ends_at': break_ends.isoformat(),
                'break_completed_at': None,
            })
            await self._insert_brain_break_event(parent_id, child_id, session_id, counter.get('id'), 'started', active_seconds, True, now, break_ends)
            if session_id:
                await self.supabase.update('learning_sessions', {'id': f'eq.{session_id}'}, {
                    'session_status': 'paused',
                    'updated_at': now.isoformat(),
                })
                await self._insert_pause_event(parent_id, child_id, {'id': session_id, 'active_time_seconds': active_seconds, 'inactive_time_seconds': 0}, 'brain_break', 0)
        records = await self.supabase.update('daily_learning_counters', {'id': f'eq.{counter["id"]}'}, updates)
        return records[0] if records else {**counter, **updates}

    async def _complete_break_if_ready(self, counter: dict) -> dict:
        if not self._break_active(counter):
            return counter
        break_ends = self._parse_datetime(counter.get('break_ends_at'))
        if not break_ends or break_ends > self._now():
            return counter
        now = self._now()
        records = await self.supabase.update('daily_learning_counters', {'id': f'eq.{counter["id"]}'}, {
            'active_tutoring_seconds': 0,
            'brain_break_required': False,
            'currently_locked_out': False,
            'break_completed_at': now.isoformat(),
            'updated_at': now.isoformat(),
            'metadata': {**(counter.get('metadata') or {}), 'last_completed_break_date': self._today()},
        })
        updated = records[0] if records else {**counter, 'currently_locked_out': False, 'brain_break_required': False, 'active_tutoring_seconds': 0}
        await self._insert_brain_break_event(
            updated.get('parent_id'),
            updated.get('child_id'),
            None,
            updated.get('id'),
            'ended',
            int(counter.get('active_tutoring_seconds') or 0),
            False,
            self._parse_datetime(counter.get('break_started_at')),
            now,
            completed=True,
        )
        await self._revoke_student_sessions(updated.get('parent_id'), updated.get('child_id'))
        return updated

    async def _insert_activity_event(
        self,
        parent_id: str,
        child_id: str,
        session_id: str | None,
        event_type: str,
        active_seconds_delta: int = 0,
        inactive_seconds_delta: int = 0,
    ) -> None:
        await self.supabase.insert('session_activity_events', {
            'parent_id': parent_id,
            'child_id': child_id,
            'learning_session_id': session_id,
            'event_type': event_type,
            'learning_mode': 'text',
            'active_seconds_delta': active_seconds_delta,
            'inactive_seconds_delta': inactive_seconds_delta,
        })

    async def _revoke_student_sessions(self, parent_id: str | None, child_id: str | None) -> None:
        if not parent_id or not child_id:
            return
        try:
            await self.supabase.update('student_sessions', {
                'parent_id': f'eq.{parent_id}',
                'child_id': f'eq.{child_id}',
                'revoked_at': 'is.null',
            }, {
                'revoked_at': self._now().isoformat(),
            })
        except SupabaseClientError as exc:
            if 'student_sessions' in str(exc).lower() and ('schema cache' in str(exc).lower() or 'does not exist' in str(exc).lower()):
                return
            raise

    async def _insert_pause_event(self, parent_id: str, child_id: str, session: dict, reason: str, inactive_total: int) -> None:
        await self.supabase.insert('session_pause_events', {
            'parent_id': parent_id,
            'child_id': child_id,
            'learning_session_id': session.get('id'),
            'pause_reason': reason,
            'active_time_before_pause_seconds': int(session.get('active_time_seconds') or 0),
            'inactive_time_before_pause_seconds': inactive_total,
        })

    async def _insert_brain_break_event(
        self,
        parent_id: str,
        child_id: str,
        session_id: str | None,
        counter_id: str | None,
        event_type: str,
        active_seconds: int,
        lockout_active: bool,
        break_started_at: datetime | None = None,
        break_ended_at: datetime | None = None,
        completed: bool = False,
    ) -> None:
        await self.supabase.insert('brain_break_events', {
            'parent_id': parent_id,
            'child_id': child_id,
            'learning_session_id': session_id,
            'daily_counter_id': counter_id,
            'event_type': event_type,
            'active_seconds_at_event': active_seconds,
            'break_started_at': break_started_at.isoformat() if break_started_at else None,
            'break_ended_at': break_ended_at.isoformat() if break_ended_at else None,
            'is_lockout_active': lockout_active,
            'completed': completed,
        })

    def _status_response(self, child_id: str, session: dict | None, counter: dict) -> SessionStatusResponse:
        active_seconds = int(counter.get('active_tutoring_seconds') or 0)
        break_ends = self._parse_datetime(counter.get('break_ends_at'))
        seconds_until_resume = max(0, int((break_ends - self._now()).total_seconds())) if break_ends else 0
        remaining = max(0, BRAIN_BREAK_LIMIT_SECONDS - active_seconds)
        warnings_due = []
        for event_type, threshold in WARNING_THRESHOLDS.items():
            column = {
                'warning_30': 'warning_30_min_sent_at',
                'warning_10': 'warning_10_min_sent_at',
                'warning_5': 'warning_5_min_sent_at',
            }[event_type]
            if remaining <= threshold and active_seconds < BRAIN_BREAK_LIMIT_SECONDS and not counter.get(column):
                warnings_due.append(event_type)
        brain_break_active = self._break_active(counter)
        return SessionStatusResponse(
            child_id=child_id,
            session_id=session.get('id') if session else None,
            session_status=session.get('session_status') if session else 'none',
            active_tutoring_seconds_today=active_seconds,
            brain_break_required=bool(counter.get('brain_break_required')),
            brain_break_active=brain_break_active,
            break_ends_at=counter.get('break_ends_at'),
            seconds_until_resume=seconds_until_resume if brain_break_active else 0,
            seconds_until_brain_break=remaining,
            warnings_due=warnings_due,
            message='Great work today! Your brain needs a short rest to absorb everything you have learned. Take a 30-minute break and come back ready to learn even more!' if brain_break_active else '',
        )

    def _break_active(self, counter: dict) -> bool:
        if not counter.get('currently_locked_out'):
            return False
        break_ends = self._parse_datetime(counter.get('break_ends_at'))
        return bool(break_ends and break_ends > self._now())

    def _parse_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _today(self) -> str:
        return self._now().date().isoformat()

    def _week_start(self) -> datetime:
        now = self._now()
        monday = now - timedelta(days=now.weekday())
        return datetime(monday.year, monday.month, monday.day, tzinfo=UTC)

    def _missing_weekly_rhythm_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'weekly_learning_rhythm' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
