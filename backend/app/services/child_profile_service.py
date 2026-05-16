from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.child_profile import ChildProfileCreateRequest, ChildProfileUpdateRequest
from .supabase_client import SupabaseClient, SupabaseClientError


class ChildProfileService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def list_children(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'child_profiles',
                f'parent_id=eq.{quote(parent_id)}&status=neq.inactive&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                return []
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def create_child(self, parent_id: str, payload: ChildProfileCreateRequest) -> dict:
        status = 'active'
        if payload.date_of_birth and not payload.parental_consent_accepted:
            status = 'pending_consent'
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
                'parental_consent_accepted': payload.parental_consent_accepted,
                'created_at': now,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not create child profile.')
        return records[0]

    async def update_child(self, parent_id: str, child_id: str, payload: ChildProfileUpdateRequest) -> dict:
        await self._get_child(parent_id, child_id)
        try:
            records = await self.supabase.update('child_profiles', {
                'id': f'eq.{child_id}',
                'parent_id': f'eq.{parent_id}',
            }, {
                'name': payload.name.strip(),
                'grade_level': payload.grade_level,
                'date_of_birth': payload.date_of_birth.isoformat() if payload.date_of_birth else None,
                'subjects': payload.subjects,
                'learning_goals': payload.learning_goals.strip(),
                'difficulty_level': payload.difficulty_level.strip(),
                'parent_notes': payload.parent_notes.strip(),
                'status': payload.status,
                'parental_consent_accepted': payload.parental_consent_accepted,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_child_profiles_table(exc):
                raise HTTPException(status_code=503, detail='Child profiles are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return records[0]

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
        return records[0]

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

    def _missing_child_profiles_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'child_profiles' in message and ('schema cache' in message or 'could not find the table' in message)
