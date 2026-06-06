import logging
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.child_profile import ChildProfileCreateRequest, ChildProfileUpdateRequest
from .learning_profile_service import LearningProfileService
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)


class ChildProfileService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def list_children(self, parent_id: str) -> list[dict]:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'parent_id=eq.{quote(parent_id)}&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                return []
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return [await self._with_learning_levels(record) for record in records]

    async def create_child(self, parent_id: str, payload: ChildProfileCreateRequest) -> dict:
        status = 'active'
        now = datetime.now(UTC).isoformat()
        try:
            records = await self.supabase.insert('child_profiles', {
                'parent_id': parent_id,
                'name': payload.name.strip(),
                'grade_level': payload.grade_level,
                'date_of_birth': payload.date_of_birth.isoformat() if payload.date_of_birth else None,
                'subjects': payload.subjects,
                'learning_goals': payload.learning_goals.strip(),
                'difficulty_level': payload.difficulty_level.strip(),
                'parent_notes': payload.parent_notes.strip(),
                'status': status,
                'parental_consent_accepted': True,
                'created_at': now,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not create child profile.')
        child = records[0]
        await self._ensure_default_child_access(parent_id, child['id'])
        return await self._with_learning_levels(child)

    async def update_child(self, parent_id: str, child_id: str, payload: ChildProfileUpdateRequest) -> dict:
        await self._get_child(parent_id, child_id)
        try:
            records = await self.supabase.update('child_profiles', {
                'id': f'eq.{child_id}',
                'parent_id': f'eq.{parent_id}',
            }, {
                'grade_level': payload.grade_level,
                'subjects': payload.subjects,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return await self._with_learning_levels(records[0])

    async def deactivate_child(self, parent_id: str, child_id: str) -> dict:
        await self._get_child(parent_id, child_id)
        try:
            records = await self.supabase.update('child_profiles', {
                'id': f'eq.{child_id}',
                'parent_id': f'eq.{parent_id}',
            }, {
                'status': 'inactive',
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return await self._with_learning_levels(records[0])

    async def reactivate_child(self, parent_id: str, child_id: str) -> dict:
        await self._get_child(parent_id, child_id)
        try:
            records = await self.supabase.update('child_profiles', {
                'id': f'eq.{child_id}',
                'parent_id': f'eq.{parent_id}',
            }, {
                'status': 'active',
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return await self._with_learning_levels(records[0])

    async def _with_learning_levels(self, child: dict) -> dict:
        child = dict(child)
        try:
            child['learning_levels'] = await LearningProfileService().subject_levels_for_child(child['id'])
        except Exception:
            child['learning_levels'] = {}
        return child

    async def _get_child(self, parent_id: str, child_id: str) -> dict:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return records[0]

    async def _ensure_default_child_access(self, parent_id: str, child_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            await self.supabase.upsert('child_access', {
                'parent_id': parent_id,
                'child_id': child_id,
                'access_status': 'inactive',
                'plan_name': 'No paid plan selected',
                'trial_ends_at': None,
                'current_period_ends_at': None,
                'created_at': now,
                'updated_at': now,
            }, 'child_id')
        except SupabaseClientError as exc:
            if self._missing_child_access_table(exc):
                logger.warning('Child access table is missing; new child %s will remain blocked until billing setup is available.', child_id)
                return
            logger.warning('Could not create default inactive child access for child %s: %s', child_id, exc)

    def _missing_child_profiles_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'child_profiles' in message and ('schema cache' in message or 'could not find the table' in message)

    def _missing_child_access_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'child_access' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
