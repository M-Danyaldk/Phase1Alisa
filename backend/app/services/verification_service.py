import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from fastapi import HTTPException, UploadFile
from ..config import get_settings
from ..core.security import generate_verification_code, hash_verification_code
from ..schemas.auth import ProfileUpdateRequest, SignupStartRequest
from .supabase_client import SupabaseClient, SupabaseClientError


class VerificationService:
    _failed_login_attempts: dict[str, dict] = {}
    _max_login_attempts = 5
    _lockout_minutes = 15

    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def _upsert_profile_with_role_fallback(self, payload: dict) -> list[dict]:
        try:
            return await self.supabase.upsert('profiles', payload, on_conflict='id')
        except SupabaseClientError as exc:
            message = str(exc).lower()
            if 'role' not in message and 'schema cache' not in message:
                raise
            fallback_payload = {key: value for key, value in payload.items() if key != 'role'}
            return await self.supabase.upsert('profiles', fallback_payload, on_conflict='id')

    async def start_signup(self, payload: SignupStartRequest) -> dict:
        email = payload.email.lower()
        await self._expire_existing_codes(email)
        code = generate_verification_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.signup_code_ttl_minutes)
        pending_signup_data = {
            'full_name': payload.full_name.strip(),
            'email': email,
            'password': payload.password,
            'grade_level': payload.grade_level,
            'date_of_birth': payload.date_of_birth.isoformat(),
            'parent_guardian_email': str(payload.parent_guardian_email).lower() if payload.parent_guardian_email else None,
        }
        try:
            await self.supabase.insert('signup_verification_codes', {
                'email': email,
                'hashed_code': hash_verification_code(code),
                'expires_at': expires_at.isoformat(),
                'attempts': 0,
                'used': False,
                'pending_signup_data': pending_signup_data,
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {
            'email': email,
            'demo_code': code,
            'expires_in_minutes': self.settings.signup_code_ttl_minutes,
            'message': 'Verification code generated.',
        }

    async def resend_code(self, email: str) -> dict:
        records = await self._latest_unused_code(email.lower())
        if not records:
            raise HTTPException(status_code=404, detail='No pending signup found for this email.')
        pending_data = records[0].get('pending_signup_data') or {}
        code = generate_verification_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.signup_code_ttl_minutes)
        await self._expire_existing_codes(email.lower())
        try:
            await self.supabase.insert('signup_verification_codes', {
                'email': email.lower(),
                'hashed_code': hash_verification_code(code),
                'expires_at': expires_at.isoformat(),
                'attempts': 0,
                'used': False,
                'pending_signup_data': pending_data,
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {
            'email': email.lower(),
            'demo_code': code,
            'expires_in_minutes': self.settings.signup_code_ttl_minutes,
            'message': 'New verification code generated.',
        }

    async def verify_signup(self, email: str, code: str) -> dict:
        email = email.lower()
        records = await self._latest_unused_code(email)
        if not records:
            raise HTTPException(status_code=400, detail='Invalid code entered. Please try again.')

        record = records[0]
        record_id = record['id']
        expires_at = self._parse_datetime(record['expires_at'])
        attempts = int(record.get('attempts') or 0)

        if expires_at <= datetime.now(UTC):
            await self._mark_code_used(record_id)
            raise HTTPException(status_code=400, detail='This code has expired. Please request a new code.')

        if attempts >= self.settings.signup_code_max_attempts:
            await self._mark_code_used(record_id)
            raise HTTPException(status_code=400, detail='This code has expired. Please request a new code.')

        if hash_verification_code(code) != record.get('hashed_code'):
            await self._increment_attempts(record_id, attempts + 1)
            raise HTTPException(status_code=400, detail='Invalid code entered. Please try again.')

        pending_data = record.get('pending_signup_data') or {}
        try:
            auth_user = await self.supabase.create_auth_user(
                email=email,
                password=pending_data['password'],
                metadata={
                    'full_name': pending_data.get('full_name'),
                    'role': 'parent',
                    'grade_level': pending_data.get('grade_level'),
                    'date_of_birth': pending_data.get('date_of_birth'),
                    'parent_guardian_email': pending_data.get('parent_guardian_email'),
                },
            )
            user_id = auth_user['id']
            await self._upsert_profile_with_role_fallback({
                'id': user_id,
                'full_name': pending_data.get('full_name'),
                'email': email,
                'role': 'parent',
                'grade_level': pending_data.get('grade_level'),
                'date_of_birth': pending_data.get('date_of_birth'),
                'parent_guardian_email': pending_data.get('parent_guardian_email'),
                'updated_at': datetime.now(UTC).isoformat(),
            })
            await self._mark_code_used(record_id)
            session = await self.supabase.login_with_password(email, pending_data['password'])
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=500, detail='Pending signup data is incomplete.') from exc

        session_user = session.get('user') or {}
        return {
            'access_token': session.get('access_token'),
            'refresh_token': session.get('refresh_token'),
            'expires_in': session.get('expires_in'),
            'token_type': session.get('token_type'),
            'message': 'Account verified and created successfully.',
            'user': {'id': session_user.get('id', user_id), 'email': session_user.get('email', email)},
        }

    async def login(self, email: str, password: str) -> dict:
        normalized_email = email.lower()
        self._ensure_login_not_locked(normalized_email)
        try:
            data = await self.supabase.login_with_password(normalized_email, password)
        except SupabaseClientError as exc:
            await self._record_failed_login(normalized_email, str(exc))
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        self._clear_failed_login(normalized_email)
        user = data.get('user') or {}
        profile = await self.current_profile(data.get('access_token', '')) if data.get('access_token') else None
        if profile and profile.get('status') in {'suspended', 'inactive'}:
            raise HTTPException(status_code=403, detail='This account is not active.')
        return {
            'access_token': data.get('access_token'),
            'refresh_token': data.get('refresh_token'),
            'expires_in': data.get('expires_in'),
            'token_type': data.get('token_type'),
            'user': {'id': user.get('id', ''), 'email': user.get('email')},
            'message': 'Login successful.',
        }

    async def current_profile(self, access_token: str) -> dict:
        user = await self._authenticated_user(access_token)
        user_id = user.get('id')
        records = await self._profile_records(user_id)
        if not records:
            return await self._create_profile_from_auth_user(user)
        return records[0]

    async def update_profile(self, access_token: str, payload: ProfileUpdateRequest) -> dict:
        user = await self._authenticated_user(access_token)
        user_id = user.get('id')
        email = (user.get('email') or '').lower()
        parent_guardian_email = str(payload.parent_guardian_email).lower() if payload.parent_guardian_email else None

        if parent_guardian_email and parent_guardian_email == email:
            raise HTTPException(status_code=422, detail='Parent/Guardian email must be different from student email.')

        try:
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'full_name': payload.full_name.strip(),
                'grade_level': payload.grade_level,
                'date_of_birth': payload.date_of_birth.isoformat(),
                'parent_guardian_email': parent_guardian_email,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            await self._create_profile_from_auth_user(user)
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'full_name': payload.full_name.strip(),
                'grade_level': payload.grade_level,
                'date_of_birth': payload.date_of_birth.isoformat(),
                'parent_guardian_email': parent_guardian_email,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        return records[0]

    async def upload_avatar(self, access_token: str, file: UploadFile) -> dict:
        user = await self._authenticated_user(access_token)
        user_id = user.get('id')
        content_type = (file.content_type or '').lower()
        extension_by_type = {
            'image/jpeg': 'jpg',
            'image/png': 'png',
            'image/webp': 'webp',
        }
        if content_type not in extension_by_type:
            raise HTTPException(status_code=422, detail='Please upload a JPG, PNG, or WEBP image.')

        content = await file.read()
        max_size = 5 * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(status_code=413, detail='Profile photo must be 5MB or smaller.')

        extension = extension_by_type[content_type]
        storage_path = f'{user_id}/profile.{extension}'
        avatar_url = ''
        try:
            await self.supabase.ensure_public_storage_bucket('avatars')
            await self.supabase.upload_storage_file('avatars', storage_path, content, content_type)
            avatar_url = self.supabase.public_storage_url('avatars', storage_path)
        except SupabaseClientError as exc:
            if 'bucket not found' not in str(exc).lower():
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
            encoded = base64.b64encode(content).decode('ascii')
            avatar_url = f'data:{content_type};base64,{encoded}'

        try:
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'avatar_url': avatar_url,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            await self._create_profile_from_auth_user(user)
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'avatar_url': avatar_url,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        return records[0]

    async def _authenticated_user(self, access_token: str) -> dict:
        try:
            user = await self.supabase.get_user(access_token)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not user.get('id'):
            raise HTTPException(status_code=401, detail='Invalid or expired session.')
        return user

    async def _profile_records(self, user_id: str) -> list[dict]:
        try:
            return await self.supabase.select('profiles', f'id=eq.{user_id}&limit=1')
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _create_profile_from_auth_user(self, user: dict) -> dict:
        user_id = user.get('id')
        email = (user.get('email') or '').lower()
        metadata = user.get('user_metadata') or {}
        full_name = metadata.get('full_name') or metadata.get('name') or email.split('@')[0] or 'Student'
        role = metadata.get('role') or 'parent'
        grade_level = metadata.get('grade_level') or 'Grade 4'
        date_of_birth = metadata.get('date_of_birth') or '2012-01-01'
        parent_guardian_email = metadata.get('parent_guardian_email')

        if not user_id or not email:
            raise HTTPException(status_code=401, detail='Invalid or expired session.')

        try:
            records = await self._upsert_profile_with_role_fallback({
                'id': user_id,
                'full_name': full_name,
                'email': email,
                'role': role,
                'grade_level': grade_level,
                'date_of_birth': date_of_birth,
                'parent_guardian_email': parent_guardian_email,
                'avatar_url': metadata.get('avatar_url') or metadata.get('picture'),
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            raise HTTPException(status_code=404, detail='Profile not found for this user.')
        return records[0]

    async def _latest_unused_code(self, email: str) -> list[dict]:
        query = f'email=eq.{quote(email)}&used=eq.false&order=created_at.desc&limit=1'
        try:
            return await self.supabase.select('signup_verification_codes', query)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _expire_existing_codes(self, email: str) -> None:
        try:
            await self.supabase.update(
                'signup_verification_codes',
                {'email': f'eq.{email}', 'used': 'eq.false'},
                {'used': True},
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _mark_code_used(self, record_id: str) -> None:
        await self.supabase.update('signup_verification_codes', {'id': f'eq.{record_id}'}, {'used': True})

    async def _increment_attempts(self, record_id: str, attempts: int) -> None:
        await self.supabase.update('signup_verification_codes', {'id': f'eq.{record_id}'}, {'attempts': attempts})

    def _parse_datetime(self, value: str) -> datetime:
        normalized = value.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _ensure_login_not_locked(self, email: str) -> None:
        state = self._failed_login_attempts.get(email)
        if not state:
            return
        locked_until = state.get('locked_until')
        if locked_until and locked_until > datetime.now(UTC):
            raise HTTPException(status_code=429, detail='Too many failed login attempts. Please try again later.')
        if locked_until:
            self._failed_login_attempts.pop(email, None)

    async def _record_failed_login(self, email: str, reason: str) -> None:
        now = datetime.now(UTC)
        state = self._failed_login_attempts.setdefault(email, {'count': 0, 'locked_until': None})
        state['count'] += 1
        if state['count'] >= self._max_login_attempts:
            state['locked_until'] = now + timedelta(minutes=self._lockout_minutes)
        try:
            await self.supabase.insert('login_security_events', {
                'email': email,
                'event_type': 'failed_login',
                'detail': {'reason': reason, 'attempt_count': state['count']},
            })
        except SupabaseClientError:
            return

    def _clear_failed_login(self, email: str) -> None:
        self._failed_login_attempts.pop(email, None)
