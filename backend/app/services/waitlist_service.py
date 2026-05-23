import logging
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException
from email_validator import EmailNotValidError, validate_email

from ..config import get_settings
from ..database import execute, fetch_all
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)
WAITLIST_SUCCESS_MESSAGE = 'Thank you — we will be in touch soon!'


class WaitlistService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def signup(self, email: str) -> dict:
        normalized_email = self._normalize_email(email)
        try:
            record = await self._save_email(normalized_email)
        except Exception as exc:
            logger.warning('Waitlist signup save failed: %s', exc)
            raise HTTPException(status_code=503, detail='Something went wrong. Please try again.') from exc

        created_at = record.get('created_at') or datetime.now(UTC).isoformat()
        await self._send_emails(normalized_email, created_at)
        return {'success': True, 'message': WAITLIST_SUCCESS_MESSAGE}

    def _normalize_email(self, email: str) -> str:
        try:
            validated = validate_email(email.strip(), check_deliverability=False)
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail='Please enter a valid email address.') from exc
        return validated.normalized.lower()

    async def _save_email(self, email: str) -> dict:
        payload = {
            'email': email,
            'source': 'prelaunch_landing',
            'status': 'pending',
            'updated_at': datetime.now(UTC).isoformat(),
        }
        if self.supabase.configured():
            try:
                records = await self.supabase.upsert('waitlist', payload, 'email')
                if records:
                    return records[0]
                return payload
            except SupabaseClientError as exc:
                message = str(exc).lower()
                if 'duplicate' in message or 'unique' in message:
                    return {'email': email, 'source': 'prelaunch_landing', 'status': 'pending'}
                raise

        existing = fetch_all('SELECT * FROM waitlist WHERE email = ? LIMIT 1', (email,))
        if existing:
            return existing[0]
        row_id = execute(
            'INSERT INTO waitlist(email, source, status) VALUES (?, ?, ?)',
            (email, 'prelaunch_landing', 'pending'),
        )
        saved = fetch_all('SELECT * FROM waitlist WHERE id = ? LIMIT 1', (row_id,))
        return saved[0] if saved else payload

    async def _send_emails(self, email: str, created_at: str) -> None:
        if not self.settings.resend_api_key.strip():
            logger.info('RESEND_API_KEY is missing; waitlist emails skipped.')
            return
        await self._send_resend_email(
            to=email,
            subject="You're on the MsAlisia waitlist",
            text=(
                'Thank you for joining the MsAlisia waitlist.\n\n'
                "You'll be among the first to know when we launch and will receive access to a free 7-day trial.\n\n"
                'We will be in touch soon.\n\n'
                'The MsAlisia Team'
            ),
        )
        await self._send_resend_email(
            to=self.settings.waitlist_notify_email,
            subject='New MsAlisia Waitlist Signup',
            text=(
                'A new user joined the MsAlisia pre-launch waitlist.\n\n'
                f'Email: {email}\n'
                'Source: prelaunch_landing\n'
                f'Time: {created_at}'
            ),
        )

    async def _send_resend_email(self, to: str, subject: str, text: str) -> None:
        payload = {
            'from': self.settings.resend_from_email,
            'to': [to],
            'subject': subject,
            'text': text,
        }
        headers = {
            'Authorization': f'Bearer {self.settings.resend_api_key}',
            'Content-Type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post('https://api.resend.com/emails', json=payload, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            logger.warning('Resend waitlist email failed for %s: %s', to, exc)
