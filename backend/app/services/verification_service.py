import base64
import logging
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from urllib.parse import quote
from fastapi import HTTPException, UploadFile
from ..config import get_settings
from ..core.security import generate_verification_code, hash_verification_code
from ..schemas.auth import ProfileUpdateRequest, SignupStartRequest
from .email_service import EmailService
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)
RESET_GENERIC_MESSAGE = 'If an account exists for this email, we sent password reset instructions.'
RESET_SUCCESS_MESSAGE = 'Your password has been reset. Please log in.'
SIGNUP_EXISTING_ACCOUNT_MESSAGE = 'An account already exists for this email. Please log in or reset your password.'


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
            optional_profile_columns = {
                'role',
                'coppa_parent_consent_accepted',
                'coppa_parent_consent_at',
                'coppa_consent_version',
                'coppa_consent_source',
            }
            if 'schema cache' not in message and not any(column in message for column in optional_profile_columns):
                raise
            fallback_payload = {key: value for key, value in payload.items() if key not in optional_profile_columns}
            return await self.supabase.upsert('profiles', fallback_payload, on_conflict='id')

    async def start_signup(self, payload: SignupStartRequest) -> dict:
        email = str(payload.email).strip().lower()
        if await self._signup_account_exists(email):
            raise HTTPException(status_code=409, detail=SIGNUP_EXISTING_ACCOUNT_MESSAGE)
        await self._expire_existing_codes(email)
        code = generate_verification_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.signup_code_ttl_minutes)
        trial_eligibility = await self._trial_eligibility_for_email(email)
        pending_signup_data = {
            'full_name': payload.full_name.strip(),
            'email': email,
            'password': payload.password,
            'referral_code': (payload.referral_code or '').strip(),
            'coppa_parent_consent_accepted': payload.coppa_parent_consent_accepted,
            'coppa_parent_consent_at': datetime.now(UTC).isoformat(),
            'coppa_consent_version': '2026-06-14',
            'coppa_consent_source': 'parent_signup',
            'trial_eligibility': trial_eligibility,
        }
        try:
            records = await self.supabase.insert('signup_verification_codes', {
                'email': email,
                'hashed_code': hash_verification_code(code),
                'expires_at': expires_at.isoformat(),
                'attempts': 0,
                'used': False,
                'pending_signup_data': pending_signup_data,
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        record_id = records[0].get('id') if records else None
        await self._send_signup_verification_email(email, code, record_id)
        return {
            'email': email,
            'expires_in_minutes': self.settings.signup_code_ttl_minutes,
            'message': 'We sent a verification code to your email. Please check your inbox.',
            **trial_eligibility,
        }

    async def resend_code(self, email: str) -> dict:
        normalized_email = email.strip().lower()
        if await self._signup_account_exists(normalized_email):
            raise HTTPException(status_code=409, detail=SIGNUP_EXISTING_ACCOUNT_MESSAGE)
        records = await self._latest_unused_code(normalized_email)
        if not records:
            raise HTTPException(status_code=404, detail='No pending signup found for this email.')
        pending_data = records[0].get('pending_signup_data') or {}
        code = generate_verification_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.signup_code_ttl_minutes)
        await self._expire_existing_codes(normalized_email)
        try:
            records = await self.supabase.insert('signup_verification_codes', {
                'email': normalized_email,
                'hashed_code': hash_verification_code(code),
                'expires_at': expires_at.isoformat(),
                'attempts': 0,
                'used': False,
                'pending_signup_data': pending_data,
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        record_id = records[0].get('id') if records else None
        await self._send_signup_verification_email(normalized_email, code, record_id)
        return {
            'email': normalized_email,
            'expires_in_minutes': self.settings.signup_code_ttl_minutes,
            'message': 'We sent a new verification code to your email. Please check your inbox.',
        }

    async def forgot_password(self, email: str) -> dict:
        normalized_email = email.strip().lower()
        parent = await self._parent_profile_by_email(normalized_email)
        if not parent:
            return {'message': RESET_GENERIC_MESSAGE}

        await self._expire_existing_reset_codes(normalized_email)
        code = generate_verification_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.reset_code_ttl_minutes)
        try:
            records = await self.supabase.insert('password_reset_codes', {
                'email': normalized_email,
                'normalized_email': normalized_email,
                'code_hash': hash_verification_code(code),
                'expires_at': expires_at.isoformat(),
                'attempts': 0,
                'max_attempts': self.settings.reset_code_max_attempts,
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail='Password reset is not set up yet. Please try again later.') from exc

        record_id = records[0].get('id') if records else None
        try:
            await EmailService().send_password_reset_code(
                recipient_email=normalized_email,
                code=code,
                expires_in_minutes=self.settings.reset_code_ttl_minutes,
            )
        except Exception as exc:
            if record_id:
                try:
                    await self._mark_reset_code_used(record_id)
                except Exception:
                    pass
            logger.warning('Password reset email failed for parent %s: %s', parent.get('id'), exc)
            raise HTTPException(status_code=503, detail='We could not send the reset email. Please try again.') from exc
        return {'message': RESET_GENERIC_MESSAGE}

    async def verify_reset_code(self, email: str, code: str) -> dict:
        await self._valid_reset_code(email.strip().lower(), code, mutate_attempts=True)
        return {'reset_allowed': True, 'message': 'Code verified. You can reset your password.'}

    async def reset_password(self, email: str, code: str, new_password: str) -> dict:
        normalized_email = email.strip().lower()
        record = await self._valid_reset_code(normalized_email, code, mutate_attempts=True)
        parent = await self._parent_profile_by_email(normalized_email)
        if not parent:
            raise HTTPException(status_code=400, detail='Invalid or expired reset code.')
        try:
            await self.supabase.update_auth_user_password(parent['id'], new_password)
            await self._mark_reset_code_used(record['id'])
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail='Could not reset password. Please try again.') from exc
        return {'message': RESET_SUCCESS_MESSAGE}

    async def verify_signup(self, email: str, code: str) -> dict:
        email = email.strip().lower()
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
        if not pending_data.get('coppa_parent_consent_accepted'):
            await self._mark_code_used(record_id)
            raise HTTPException(status_code=400, detail='Please confirm parent/guardian consent before continuing.')
        trial_eligibility = await self._trial_eligibility_for_email(email)
        try:
            auth_user = await self.supabase.create_auth_user(
                email=email,
                password=pending_data['password'],
                metadata={
                    'full_name': pending_data.get('full_name'),
                    'role': 'parent',
                    'coppa_parent_consent_accepted': True,
                    'coppa_consent_version': pending_data.get('coppa_consent_version') or '2026-06-14',
                },
            )
            user_id = auth_user['id']
            await self._upsert_profile_with_role_fallback({
                'id': user_id,
                'full_name': pending_data.get('full_name'),
                'email': email,
                'role': 'parent',
                'coppa_parent_consent_accepted': True,
                'coppa_parent_consent_at': pending_data.get('coppa_parent_consent_at') or datetime.now(UTC).isoformat(),
                'coppa_consent_version': pending_data.get('coppa_consent_version') or '2026-06-14',
                'coppa_consent_source': pending_data.get('coppa_consent_source') or 'parent_signup',
                'updated_at': datetime.now(UTC).isoformat(),
            })
            await self._mark_code_used(record_id)
            session = await self.supabase.login_with_password(email, pending_data['password'])
            await self._queue_signup_welcome(user_id, email)
            await self._send_parent_account_created_alert(user_id, email, pending_data)
            await self._record_referral_signup(user_id, email, pending_data.get('referral_code'))
        except SupabaseClientError as exc:
            if self._is_existing_account_error(exc):
                await self._mark_code_used(record_id)
                raise HTTPException(status_code=409, detail=SIGNUP_EXISTING_ACCOUNT_MESSAGE) from exc
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
            **trial_eligibility,
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

    async def _parent_profile_by_email(self, email: str) -> dict | None:
        try:
            records = await self.supabase.select(
                'profiles',
                f'email=eq.{quote(email)}&role=eq.parent&status=neq.inactive&limit=1',
            )
        except SupabaseClientError as exc:
            logger.warning('Could not load parent profile for password reset: %s', exc)
            return None
        return records[0] if records else None

    async def _signup_account_exists(self, email: str) -> bool:
        try:
            records = await self.supabase.select(
                'profiles',
                f'email=eq.{quote(email)}&status=neq.inactive&limit=1',
            )
        except SupabaseClientError as exc:
            logger.warning('Could not check existing signup account for %s: %s', email, exc)
            return False
        return bool(records)

    def _is_existing_account_error(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return exc.status_code in {409, 422} and (
            'already' in message
            or 'registered' in message
            or 'exists' in message
            or 'duplicate' in message
        )

    async def _valid_reset_code(self, email: str, code: str, mutate_attempts: bool) -> dict:
        records = await self._latest_unused_reset_code(email)
        if not records:
            raise HTTPException(status_code=400, detail='Invalid or expired reset code.')

        record = records[0]
        record_id = record['id']
        expires_at = self._parse_datetime(record['expires_at'])
        attempts = int(record.get('attempts') or 0)
        max_attempts = int(record.get('max_attempts') or self.settings.reset_code_max_attempts)

        if not expires_at or expires_at <= datetime.now(UTC):
            await self._mark_reset_code_used(record_id)
            raise HTTPException(status_code=400, detail='Invalid or expired reset code.')
        if attempts >= max_attempts:
            await self._mark_reset_code_used(record_id)
            raise HTTPException(status_code=400, detail='Invalid or expired reset code.')
        if not compare_digest(hash_verification_code(code), str(record.get('code_hash') or '')):
            next_attempts = attempts + 1
            if mutate_attempts:
                await self._increment_reset_attempts(record_id, next_attempts)
            if next_attempts >= max_attempts:
                await self._mark_reset_code_used(record_id)
            raise HTTPException(status_code=400, detail='Invalid or expired reset code.')
        return record

    async def _latest_unused_reset_code(self, email: str) -> list[dict]:
        query = f'normalized_email=eq.{quote(email)}&used_at=is.null&order=created_at.desc&limit=1'
        try:
            return await self.supabase.select('password_reset_codes', query)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=503, detail='Password reset is not set up yet. Please try again later.') from exc

    async def _expire_existing_reset_codes(self, email: str) -> None:
        try:
            await self.supabase.update(
                'password_reset_codes',
                {'normalized_email': f'eq.{email}', 'used_at': 'is.null'},
                {'used_at': datetime.now(UTC).isoformat(), 'updated_at': datetime.now(UTC).isoformat()},
            )
        except SupabaseClientError as exc:
            message = str(exc).lower()
            if 'password_reset_codes' not in message:
                raise

    async def _mark_reset_code_used(self, record_id: str) -> None:
        await self.supabase.update('password_reset_codes', {'id': f'eq.{record_id}'}, {
            'used_at': datetime.now(UTC).isoformat(),
            'updated_at': datetime.now(UTC).isoformat(),
        })

    async def _increment_reset_attempts(self, record_id: str, attempts: int) -> None:
        await self.supabase.update('password_reset_codes', {'id': f'eq.{record_id}'}, {
            'attempts': attempts,
            'updated_at': datetime.now(UTC).isoformat(),
        })

    async def update_profile(self, access_token: str, payload: ProfileUpdateRequest) -> dict:
        user = await self._authenticated_user(access_token)
        user_id = user.get('id')

        try:
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'full_name': payload.full_name.strip(),
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            await self._create_profile_from_auth_user(user)
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, {
                'full_name': payload.full_name.strip(),
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

        if not user_id or not email:
            raise HTTPException(status_code=401, detail='Invalid or expired session.')

        try:
            records = await self._upsert_profile_with_role_fallback({
                'id': user_id,
                'full_name': full_name,
                'email': email,
                'role': role,
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

    async def _send_signup_verification_email(self, email: str, code: str, record_id: str | None) -> None:
        try:
            await EmailService().send_signup_verification_code(
                recipient_email=email,
                code=code,
                expires_in_minutes=self.settings.signup_code_ttl_minutes,
            )
        except Exception as exc:
            if record_id:
                try:
                    await self._mark_code_used(record_id)
                except Exception:
                    pass
            logger.warning('Signup verification email failed: %s', exc)
            raise HTTPException(status_code=503, detail='We could not send the verification email. Please try again.') from exc

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

    async def _queue_signup_welcome(self, user_id: str, email: str) -> None:
        try:
            await EmailService().queue_and_send_signup_welcome(parent_id=user_id, recipient_email=email)
        except Exception as exc:
            logger.warning('Signup welcome email send failed for parent %s: %s', user_id, exc)

    async def _send_parent_account_created_alert(self, user_id: str, email: str, pending_data: dict) -> None:
        try:
            await EmailService().send_internal_admin_alert(
                subject='MsAlisia Admin Alert: New parent account created',
                lines=[
                    'Event type: New parent account created',
                    f'Parent name: {pending_data.get("full_name") or "Not provided"}',
                    f'Parent email: {email}',
                    f'Time: {datetime.now(UTC).isoformat()}',
                ],
            )
        except Exception as exc:
            logger.warning('Internal parent signup alert failed for parent %s: %s', user_id, exc)

    async def _trial_eligibility_for_email(self, email: str) -> dict:
        normalized_email = email.strip().lower()
        try:
            rows = await self.supabase.select(
                'parent_trial_history',
                f'normalized_email=eq.{quote(normalized_email)}&order=trial_started_at.desc&limit=1',
            )
        except SupabaseClientError as exc:
            message = str(exc).lower()
            if 'parent_trial_history' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message):
                return {'trial_available': True, 'paid_checkout_required': False, 'trial_blocked_reason': None}
            logger.warning('Could not check trial eligibility during signup: %s', exc)
            return {'trial_available': True, 'paid_checkout_required': False, 'trial_blocked_reason': None}
        used_trial = bool(rows)
        return {
            'trial_available': not used_trial,
            'paid_checkout_required': used_trial,
            'trial_blocked_reason': 'trial_already_used' if used_trial else None,
        }

    async def _record_referral_signup(self, user_id: str, email: str, referral_code: object) -> None:
        code = str(referral_code or '').strip()
        if not code:
            return
        try:
            from .referral_service import ReferralService

            await ReferralService().record_referred_signup(user_id, email, code)
        except Exception as exc:
            logger.warning('Referral attribution skipped for parent %s: %s', user_id, exc)
