import json
import logging
from datetime import UTC, datetime
from urllib.parse import quote

from ..database import execute, fetch_all
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

SUBJECTS = ('Math', 'ELA', 'Writing')


class LearningProfileService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def upsert_from_assessment(self, payload: dict) -> None:
        child_id = payload.get('child_id')
        subject = payload.get('subject')
        assessed_level = payload.get('estimated_level')
        if not child_id or subject not in SUBJECTS or not assessed_level:
            return

        now = datetime.now(UTC).isoformat()
        record = {
            'child_id': child_id,
            'subject': subject,
            'assessed_level': assessed_level,
            'learning_gaps': self._list(payload.get('learning_gaps')),
            'strengths': self._list(payload.get('strengths')),
            'recommended_next_steps': self._list(payload.get('recommended_progression') or payload.get('recommended_next_steps')),
            'recommended_next_topics': self._list(payload.get('recommended_next_topics')),
            'last_assessed_at': now,
            'updated_at': now,
        }
        if self.supabase.configured():
            try:
                await self.supabase.upsert('child_learning_profiles', record, 'child_id,subject')
                return
            except SupabaseClientError as exc:
                logger.warning('Could not upsert child learning profile: %s', exc)
                raise

        execute(
            '''
            INSERT INTO child_learning_profiles(
              child_id, subject, assessed_level, learning_gaps, strengths,
              recommended_next_steps, recommended_next_topics, last_assessed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(child_id, subject) DO UPDATE SET
              assessed_level = excluded.assessed_level,
              learning_gaps = excluded.learning_gaps,
              strengths = excluded.strengths,
              recommended_next_steps = excluded.recommended_next_steps,
              recommended_next_topics = excluded.recommended_next_topics,
              last_assessed_at = excluded.last_assessed_at,
              updated_at = excluded.updated_at
            ''',
            (
                child_id,
                subject,
                assessed_level,
                self._json_text(record['learning_gaps']),
                self._json_text(record['strengths']),
                self._json_text(record['recommended_next_steps']),
                self._json_text(record['recommended_next_topics']),
                now,
                now,
            ),
        )

    async def context_for_child_subject(self, child_id: str | None, subject: str) -> dict | None:
        if not child_id or subject not in SUBJECTS:
            return None
        assessment = await self.latest_assessment_context(child_id, subject)
        if assessment:
            return assessment
        return await self.learning_profile(child_id, subject)

    async def learning_profile(self, child_id: str, subject: str) -> dict | None:
        if self.supabase.configured():
            try:
                records = await self.supabase.select(
                    'child_learning_profiles',
                    f'child_id=eq.{quote(child_id)}&subject=eq.{quote(subject)}&limit=1',
                )
                return self._normalize_profile(records[0]) if records else None
            except SupabaseClientError as exc:
                logger.warning('Could not load child learning profile: %s', exc)
                return None
        rows = fetch_all(
            'SELECT * FROM child_learning_profiles WHERE child_id = ? AND subject = ? LIMIT 1',
            (child_id, subject),
        )
        return self._normalize_profile(rows[0]) if rows else None

    async def learning_profiles_for_child(self, child_id: str) -> list[dict]:
        if self.supabase.configured():
            try:
                records = await self.supabase.select(
                    'child_learning_profiles',
                    f'child_id=eq.{quote(child_id)}&order=last_assessed_at.desc',
                )
                return [self._normalize_profile(record) for record in records]
            except SupabaseClientError as exc:
                logger.warning('Could not load child learning profiles: %s', exc)
                return []
        rows = fetch_all(
            'SELECT * FROM child_learning_profiles WHERE child_id = ? ORDER BY last_assessed_at DESC',
            (child_id,),
        )
        return [self._normalize_profile(row) for row in rows]

    async def latest_assessment_context(self, child_id: str, subject: str) -> dict | None:
        if self.supabase.configured():
            try:
                records = await self.supabase.select(
                    'assessment_results',
                    f'child_id=eq.{quote(child_id)}&subject=eq.{quote(subject)}&order=created_at.desc&limit=1',
                )
                return self._normalize_assessment(records[0]) if records else None
            except SupabaseClientError as exc:
                logger.warning('Could not load latest assessment context: %s', exc)
                return None
        rows = fetch_all(
            'SELECT * FROM assessment_results WHERE child_id = ? AND subject = ? ORDER BY created_at DESC LIMIT 1',
            (child_id, subject),
        )
        return self._normalize_assessment(rows[0]) if rows else None

    async def subject_levels_for_child(self, child_id: str) -> dict[str, str]:
        profiles = await self.learning_profiles_for_child(child_id)
        return {
            profile['subject']: profile['assessed_level']
            for profile in profiles
            if profile.get('subject') in SUBJECTS and profile.get('assessed_level')
        }

    def _normalize_profile(self, record: dict) -> dict:
        return {
            'child_id': record.get('child_id'),
            'subject': record.get('subject'),
            'assessed_level': record.get('assessed_level') or record.get('estimated_level'),
            'learning_gaps': self._list(record.get('learning_gaps')),
            'strengths': self._list(record.get('strengths')),
            'recommended_next_steps': self._list(record.get('recommended_next_steps')),
            'recommended_next_topics': self._list(record.get('recommended_next_topics')),
            'last_assessed_at': record.get('last_assessed_at') or record.get('created_at'),
        }

    def _normalize_assessment(self, record: dict) -> dict:
        return {
            'child_id': record.get('child_id'),
            'subject': record.get('subject'),
            'assessed_level': record.get('estimated_level'),
            'learning_gaps': self._list(record.get('learning_gaps')),
            'strengths': self._list(record.get('strengths')),
            'recommended_next_steps': self._list(record.get('recommended_progression')),
            'recommended_next_topics': self._list(record.get('recommended_next_topics')),
            'last_assessed_at': record.get('created_at'),
        }

    def _list(self, value: object) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        try:
            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            pass
        text = str(value).strip()
        return [text] if text else []

    def _json_text(self, value: object) -> str:
        return json.dumps(self._list(value))
