import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException

from ..core.security import generate_session_token, hash_pin, hash_session_token, verify_pin
from ..schemas.student_auth import StudentAccessUpsertRequest, StudentLoginRequest
from .learning_profile_service import LearningProfileService
from .supabase_client import SupabaseClient, SupabaseClientError

USERNAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]{2,31}$')
SESSION_HOURS = 12
CLASSROOM_CONTEXT_MINUTES = 15


class StudentAuthService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def get_student_access(self, parent_id: str, child_id: str) -> dict | None:
        await self._child(parent_id, child_id)
        try:
            records = await self.supabase.select(
                'student_access',
                f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return records[0] if records else None

    async def upsert_student_access(self, parent_id: str, child_id: str, payload: StudentAccessUpsertRequest) -> dict:
        await self._child(parent_id, child_id)
        username = self.normalize_username(payload.username)
        now = datetime.now(UTC).isoformat()
        record = {
            'parent_id': parent_id,
            'child_id': child_id,
            'username': username,
            'normalized_username': username,
            'pin_hash': hash_pin(payload.pin),
            'is_active': payload.is_active,
            'updated_at': now,
        }
        existing = await self.get_student_access(parent_id, child_id)
        if not existing:
            record['created_at'] = now
        try:
            records = await self.supabase.upsert('student_access', record, 'child_id')
        except SupabaseClientError as exc:
            message = str(exc).lower()
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            if 'duplicate' in message or 'unique' in message:
                raise HTTPException(status_code=409, detail='Student username is already taken. Please choose another username.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not save student access.')
        return self._public_access(records[0])

    async def create_classroom_context(self, parent_id: str, child_id: str) -> dict:
        await self._child(parent_id, child_id, require_active=True)
        token = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=CLASSROOM_CONTEXT_MINUTES)
        try:
            await self.supabase.insert('classroom_login_contexts', {
                'parent_id': parent_id,
                'child_id': child_id,
                'context_token_hash': hash_session_token(token),
                'expires_at': expires_at.isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_classroom_contexts(exc):
                raise HTTPException(status_code=503, detail='Classroom login contexts are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {
            'classroom_context_token': token,
            'child_id': child_id,
            'parent_id': parent_id,
            'expires_at': expires_at.isoformat(),
        }

    async def login(self, payload: StudentLoginRequest) -> dict:
        username = self.normalize_username(payload.username)
        context = await self._classroom_context(payload.classroom_context_token)
        access = await self._access_for_context(context, username)
        if not access or not access.get('is_active') or not verify_pin(payload.pin, access.get('pin_hash') or ''):
            raise HTTPException(status_code=401, detail='Invalid student username or PIN.')
        child = await self._child(access['parent_id'], access['child_id'], require_active=True)
        access_state = await self._billing_state(child)
        token = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(hours=SESSION_HOURS)
        token_hash = hash_session_token(token)
        try:
            await self.supabase.insert('student_sessions', {
                'parent_id': access['parent_id'],
                'child_id': access['child_id'],
                'student_access_id': access['id'],
                'token_hash': token_hash,
                'expires_at': expires_at.isoformat(),
            })
            await self.supabase.update('classroom_login_contexts', {'id': f'eq.{context["id"]}'}, {'used_at': datetime.now(UTC).isoformat()})
            await self.supabase.update('student_access', {'id': f'eq.{access["id"]}'}, {'last_login_at': datetime.now(UTC).isoformat()})
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {
            'access_token': token,
            'token_type': 'student',
            'role': 'child',
            'child_id': child['id'],
            'parent_id': child['parent_id'],
            'student_name': child['name'],
            'grade_level': child['grade_level'],
            'learning_levels': await LearningProfileService().subject_levels_for_child(child['id']),
            **access_state,
            'expires_at': expires_at.isoformat(),
            'message': 'Student login successful.',
        }

    async def current_student(self, token: str) -> dict:
        session = await self.session_from_token(token)
        child = await self._child(session['parent_id'], session['child_id'], require_active=True)
        access_state = await self._billing_state(child)
        return {
            'role': 'child',
            'child_id': child['id'],
            'parent_id': child['parent_id'],
            'student_name': child['name'],
            'grade_level': child['grade_level'],
            'subjects': child.get('subjects') or [],
            'learning_levels': await LearningProfileService().subject_levels_for_child(child['id']),
            **access_state,
            'session_expires_at': session['expires_at'],
        }

    async def logout(self, token: str) -> dict:
        token_hash = hash_session_token(token)
        try:
            await self.supabase.update('student_sessions', {'token_hash': f'eq.{token_hash}'}, {'revoked_at': datetime.now(UTC).isoformat()})
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {'message': 'Student logged out.'}

    async def session_from_token(self, token: str) -> dict:
        token_hash = hash_session_token(token)
        try:
            records = await self.supabase.select('student_sessions', f'token_hash=eq.{quote(token_hash)}&limit=1')
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=401, detail='Invalid or expired student session.')
        session = records[0]
        if session.get('revoked_at'):
            raise HTTPException(status_code=401, detail='Invalid or expired student session.')
        expires_at = self._parse_datetime(session['expires_at'])
        if expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=401, detail='Invalid or expired student session.')
        return session

    def normalize_username(self, username: str) -> str:
        value = username.strip().lower()
        if not USERNAME_PATTERN.match(value):
            raise HTTPException(status_code=422, detail='Student username must be 3-32 characters and use only lowercase letters, numbers, dots, dashes, or underscores.')
        return value

    async def _classroom_context(self, token: str) -> dict:
        token_hash = hash_session_token(token)
        try:
            records = await self.supabase.select('classroom_login_contexts', f'context_token_hash=eq.{quote(token_hash)}&limit=1')
        except SupabaseClientError as exc:
            if self._missing_classroom_contexts(exc):
                raise HTTPException(status_code=503, detail='Classroom login contexts are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=401, detail='Please start from your parent dashboard to open your classroom.')
        context = records[0]
        if context.get('used_at'):
            raise HTTPException(status_code=401, detail='Please start from your parent dashboard to open your classroom.')
        expires_at = self._parse_datetime(context['expires_at'])
        if expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=401, detail='Please start from your parent dashboard to open your classroom.')
        return context

    async def _access_for_context(self, context: dict, username: str) -> dict | None:
        parent_id = context['parent_id']
        child_id = context['child_id']
        query = (
            f'parent_id=eq.{quote(parent_id)}'
            f'&child_id=eq.{quote(child_id)}'
            f'&normalized_username=eq.{quote(username)}'
            '&limit=1'
        )
        try:
            records = await self.supabase.select('student_access', query)
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return records[0] if records else None

    async def _child(self, parent_id: str, child_id: str, require_active: bool = False) -> dict:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&limit=1',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        child = records[0]
        if require_active and child.get('status') == 'inactive':
            raise HTTPException(status_code=403, detail='Your learning access is currently paused. Please ask your parent to check the account.')
        return child

    def _public_access(self, record: dict) -> dict:
        return {key: value for key, value in record.items() if key != 'pin_hash'}

    def _missing_student_access(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return ('student_access' in message or 'student_sessions' in message) and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _missing_classroom_contexts(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'classroom_login_contexts' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    async def _billing_state(self, child: dict) -> dict:
        from .access_control import child_billing_access_state

        return await child_billing_access_state(child['id'], child_name=child.get('name'))
