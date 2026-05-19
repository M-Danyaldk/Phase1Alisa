from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.billing import ChildAccessUpdateRequest
from .supabase_client import SupabaseClient, SupabaseClientError


class BillingService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def list_child_access(self, parent_id: str) -> list[dict]:
        children = await self._children(parent_id)
        access_rows = await self._access_rows(parent_id)
        access_by_child = {row['child_id']: row for row in access_rows}

        records: list[dict] = []
        for child in children:
            access = access_by_child.get(child['id'])
            if not access:
                access = await self._create_default_access(parent_id, child)
            records.append(self._merge(child, access))
        return records

    async def update_child_access(self, parent_id: str, child_id: str, payload: ChildAccessUpdateRequest) -> dict:
        if payload.access_status in {'active', 'past_due'}:
            raise HTTPException(status_code=403, detail='This billing action is handled by admin billing tools.')
        child = await self._child(parent_id, child_id)
        now = datetime.now(UTC)
        update = {
            'access_status': payload.access_status,
            'plan_name': payload.plan_name.strip() or 'Phase 1 MVP',
            'updated_at': now.isoformat(),
        }
        if payload.access_status == 'trial':
            update['trial_ends_at'] = (now + timedelta(days=7)).isoformat()
            update['current_period_ends_at'] = None
        elif payload.access_status == 'active':
            update['trial_ends_at'] = None
            update['current_period_ends_at'] = (now + timedelta(days=30)).isoformat()
        else:
            update['trial_ends_at'] = None
            update['current_period_ends_at'] = None

        try:
            records = await self.supabase.update('child_access', {
                'parent_id': f'eq.{parent_id}',
                'child_id': f'eq.{child_id}',
            }, update)
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            records = [await self._create_default_access(parent_id, child, update)]
        return self._merge(child, records[0])

    async def _children(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'child_profiles',
                f'parent_id=eq.{quote(parent_id)}&status=neq.inactive&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _child(self, parent_id: str, child_id: str) -> dict:
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

    async def _access_rows(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'child_access',
                f'parent_id=eq.{quote(parent_id)}&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _create_default_access(self, parent_id: str, child: dict, override: dict | None = None) -> dict:
        now = datetime.now(UTC)
        payload = {
            'parent_id': parent_id,
            'child_id': child['id'],
            'access_status': 'trial',
            'plan_name': 'Phase 1 MVP',
            'trial_ends_at': (now + timedelta(days=7)).isoformat(),
            'current_period_ends_at': None,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }
        if override:
            payload.update(override)
        try:
            records = await self.supabase.upsert('child_access', payload, 'child_id')
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not create child access record.')
        return records[0]

    def _merge(self, child: dict, access: dict) -> dict:
        return {
            **access,
            'child_name': child['name'],
            'grade_level': child['grade_level'],
            'access_status': access.get('access_status') or 'inactive',
            'plan_name': access.get('plan_name') or 'Phase 1 MVP',
        }

    def _missing_access_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'child_access' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
