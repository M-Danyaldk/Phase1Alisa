import logging
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
FAMILY_CODE_ATTEMPTS = 5
logger = logging.getLogger(__name__)


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

    async def get_or_create_family_classroom_link(self, parent_id: str) -> dict:
        existing = await self._active_family_link_for_parent(parent_id)
        if existing:
            return self._public_family_link(existing)
        for _ in range(FAMILY_CODE_ATTEMPTS):
            code = generate_session_token()
            try:
                records = await self.supabase.insert('family_classroom_links', {
                    'parent_id': parent_id,
                    'family_code': code,
                    'is_active': True,
                })
            except SupabaseClientError as exc:
                message = str(exc).lower()
                if self._missing_family_links(exc):
                    raise HTTPException(status_code=503, detail='Family classroom links are not set up yet. Please run the Supabase migration first.') from exc
                if 'duplicate' in message or 'unique' in message:
                    existing = await self._active_family_link_for_parent(parent_id)
                    if existing:
                        return self._public_family_link(existing)
                    continue
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
            if records:
                return self._public_family_link(records[0])
        raise HTTPException(status_code=500, detail='Could not create family classroom link.')

    async def login(self, payload: StudentLoginRequest) -> dict:
        username = self.normalize_username(payload.username)
        family_link = await self._family_link(payload.family_code)
        access = await self._access_for_family(family_link, username)
        if not access or not access.get('is_active') or not verify_pin(payload.pin, access.get('pin_hash') or ''):
            raise HTTPException(status_code=401, detail='That username or PIN didn’t work. Please check it and try again.')
        child = await self._child(access['parent_id'], access['child_id'], require_active=True)
        await self._prepare_classroom_access(child)
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
            await self.supabase.update('family_classroom_links', {'id': f'eq.{family_link["id"]}'}, {'last_used_at': datetime.now(UTC).isoformat()})
            await self.supabase.update('student_access', {'id': f'eq.{access["id"]}'}, {'last_login_at': datetime.now(UTC).isoformat()})
        except SupabaseClientError as exc:
            if self._missing_student_access(exc):
                raise HTTPException(status_code=503, detail='Student access tables are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        message = 'Your classroom is ready. Let\'s start learning.' if access_state.get('access_allowed') else 'Please ask your parent to choose a plan so your classroom can continue.'
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
            'message': message,
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

    def normalize_family_code(self, family_code: str) -> str:
        value = family_code.strip()
        if len(value) < 12:
            raise HTTPException(status_code=401, detail='Please check your family classroom link and try again.')
        return value

    async def _active_family_link_for_parent(self, parent_id: str) -> dict | None:
        try:
            records = await self.supabase.select(
                'family_classroom_links',
                f'parent_id=eq.{quote(parent_id)}&is_active=is.true&order=created_at.desc&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_family_links(exc):
                return None
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return records[0] if records else None

    async def _family_link(self, family_code: str) -> dict:
        code = self.normalize_family_code(family_code)
        try:
            records = await self.supabase.select(
                'family_classroom_links',
                f'family_code=eq.{quote(code)}&is_active=is.true&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_family_links(exc):
                raise HTTPException(status_code=503, detail='Family classroom links are not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=401, detail='Please check your family classroom link and try again.')
        return records[0]

    async def _access_for_family(self, family_link: dict, username: str) -> dict | None:
        parent_id = family_link['parent_id']
        query = (
            f'parent_id=eq.{quote(parent_id)}'
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

    def _public_family_link(self, record: dict) -> dict:
        return {
            'family_code': record['family_code'],
            'classroom_path': f'/student?family={record["family_code"]}',
            'created_at': record.get('created_at'),
            'updated_at': record.get('updated_at'),
        }

    def _missing_student_access(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return ('student_access' in message or 'student_sessions' in message) and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _missing_family_links(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'family_classroom_links' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    async def _billing_state(self, child: dict) -> dict:
        from .access_control import child_billing_access_state

        return await child_billing_access_state(child['id'], child_name=child.get('name'))

    async def _prepare_classroom_access(self, child: dict) -> None:
        try:
            from .billing_service import BillingService

            await BillingService().prepare_classroom_access(child['parent_id'], child['id'])
        except Exception as exc:
            logger.warning('Could not prepare classroom billing access for child %s: %s', child.get('id'), exc)
