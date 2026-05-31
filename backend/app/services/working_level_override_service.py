from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from ..curriculum import LAUNCH_GRADE_ERROR, LAUNCH_GRADES
from ..schemas.working_level_override import WorkingLevelOverrideRequest
from .learning_profile_service import SUBJECTS, LearningProfileService
from .supabase_client import SupabaseClient, SupabaseClientError


class WorkingLevelOverrideService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def summary_for_child(self, parent_id: str, child_id: str) -> dict:
        child = await self._child(parent_id, child_id)
        overrides = await self._overrides_by_subject(child_id)
        profiles = await LearningProfileService().subject_levels_for_child(child_id)
        subjects = self._subjects(child)
        items = [
            self._summary_item(child, subject, profiles.get(subject), overrides.get(subject))
            for subject in subjects
        ]
        return {
            'child_id': child['id'],
            'child_name': child.get('name') or 'Child',
            'enrolled_grade': child.get('grade_level') or 'Grade 3',
            'subjects': items,
        }

    async def set_override(self, parent_id: str, child_id: str, payload: WorkingLevelOverrideRequest) -> dict:
        child = await self._child(parent_id, child_id)
        subject = payload.subject
        enrolled_grade = child.get('grade_level') or 'Grade 3'
        if self._grade_number(payload.unlocked_grade_level) not in LAUNCH_GRADES:
            raise HTTPException(status_code=422, detail=LAUNCH_GRADE_ERROR)
        if self._grade_number(payload.unlocked_grade_level) < self._grade_number(enrolled_grade):
            raise HTTPException(status_code=422, detail='Working level must be at or above the enrolled grade.')

        profiles = await LearningProfileService().subject_levels_for_child(child_id)
        previous_level = profiles.get(subject) or enrolled_grade
        now = datetime.now(UTC).isoformat()
        record = {
            'parent_id': parent_id,
            'child_id': child_id,
            'subject': subject,
            'enrolled_grade': enrolled_grade,
            'approved_working_level': payload.unlocked_grade_level,
            'previous_working_level': previous_level,
            'status': 'approved',
            'requested_by': parent_id,
            'approved_by_parent_id': parent_id,
            'approved_at': now,
            'revoked_at': None,
            'audit_metadata': {
                'source': 'parent_override',
                'note': 'Parent set a subject-specific working level.',
            },
            'updated_at': now,
        }
        try:
            await self.supabase.upsert('subject_working_level_overrides', record, 'child_id,subject')
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                raise HTTPException(status_code=503, detail='Working level overrides are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return await self.summary_for_child(parent_id, child_id)

    async def reset_override(self, parent_id: str, child_id: str, subject: str) -> dict:
        if subject not in SUBJECTS:
            raise HTTPException(status_code=422, detail='Subject must be Math, ELA, or Writing.')
        await self._child(parent_id, child_id)
        now = datetime.now(UTC).isoformat()
        try:
            await self.supabase.update('subject_working_level_overrides', {
                'child_id': f'eq.{child_id}',
                'subject': f'eq.{subject}',
            }, {
                'status': 'revoked',
                'revoked_at': now,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                raise HTTPException(status_code=503, detail='Working level overrides are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return await self.summary_for_child(parent_id, child_id)

    async def active_override_for_subject(self, child_id: str, subject: str) -> dict | None:
        if subject not in SUBJECTS:
            return None
        try:
            records = await self.supabase.select(
                'subject_working_level_overrides',
                f'child_id=eq.{quote(child_id)}&subject=eq.{quote(subject)}&status=eq.approved&limit=1',
            )
        except SupabaseClientError:
            return None
        return records[0] if records else None

    async def active_overrides_for_child(self, child_id: str) -> dict[str, dict]:
        return await self._overrides_by_subject(child_id)

    async def _child(self, parent_id: str, child_id: str) -> dict:
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

    async def _overrides_by_subject(self, child_id: str) -> dict[str, dict]:
        try:
            records = await self.supabase.select(
                'subject_working_level_overrides',
                f'child_id=eq.{quote(child_id)}&status=eq.approved',
            )
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                return {}
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {record.get('subject'): record for record in records if record.get('subject') in SUBJECTS}

    def _summary_item(self, child: dict, subject: str, assessed_level: str | None, override: dict | None) -> dict:
        enrolled_grade = child.get('grade_level') or 'Grade 3'
        override_level = (override or {}).get('approved_working_level')
        effective = override_level or assessed_level or enrolled_grade
        return {
            'subject': subject,
            'enrolled_grade': enrolled_grade,
            'assessed_level': assessed_level,
            'effective_working_level': effective,
            'override_level': override_level,
            'override_active': bool(override_level),
            'status': (override or {}).get('status'),
            'display_text': f'Working at {effective} level - enrolled in {enrolled_grade}',
            'updated_at': (override or {}).get('updated_at') or (override or {}).get('approved_at'),
        }

    def _subjects(self, child: dict) -> list[str]:
        subjects = child.get('subjects') or list(SUBJECTS)
        if isinstance(subjects, str):
            return [subject for subject in SUBJECTS if subject in subjects] or list(SUBJECTS)
        return [subject for subject in subjects if subject in SUBJECTS] or list(SUBJECTS)

    def _grade_number(self, value: object) -> int:
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        return int(digits) if digits else 3

    def _missing_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'subject_working_level_overrides' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
