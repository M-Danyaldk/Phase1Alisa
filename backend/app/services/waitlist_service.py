import logging
from datetime import UTC, datetime
from html import escape
import json

import httpx
from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException

from ..config import DEFAULT_EMAIL_LOGO_URL, get_settings
from ..database import execute, fetch_all
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)
WAITLIST_SUCCESS_MESSAGE = "You're on the waitlist. Access is scheduled to open on June 15."


class WaitlistService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def signup(self, email: str, parent_name: str | None = None, child_grade: str | None = None, interest_note: str | None = None) -> dict:
        normalized_email = self._normalize_email(email)
        details = {
            'parent_name': self._clean(parent_name),
            'child_grade': self._clean(child_grade),
            'interest_note': self._clean(interest_note),
        }
        try:
            record = await self._save_email(normalized_email, details)
        except Exception as exc:
            logger.warning('Waitlist signup save failed: %s', exc)
            raise HTTPException(status_code=503, detail='Something went wrong. Please try again.') from exc

        created_at = record.get('created_at') or datetime.now(UTC).isoformat()
        await self._send_emails(normalized_email, created_at, details)
        return {'success': True, 'message': self._success_message()}

    def _normalize_email(self, email: str) -> str:
        try:
            validated = validate_email(email.strip(), check_deliverability=False)
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail='Please enter a valid email address.') from exc
        return validated.normalized.lower()

    def _clean(self, value: str | None) -> str:
        return (value or '').strip()

    async def _save_email(self, email: str, details: dict[str, str]) -> dict:
        payload = {
            'email': email,
            'source': 'prelaunch_landing',
            'status': 'pending',
            'metadata': {
                'parent_name': details['parent_name'],
                'child_grade': details['child_grade'],
                'interest_note': details['interest_note'],
                'source': 'prelaunch_landing',
                'submitted_at': datetime.now(UTC).isoformat(),
            },
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
                if 'metadata' not in message:
                    raise
                fallback = {key: value for key, value in payload.items() if key != 'metadata'}
                records = await self.supabase.upsert('waitlist', fallback, 'email')
                return records[0] if records else fallback

        existing = fetch_all('SELECT * FROM waitlist WHERE email = ? LIMIT 1', (email,))
        if existing:
            return existing[0]
        row_id = execute(
            'INSERT INTO waitlist(email, source, status, metadata) VALUES (?, ?, ?, ?)',
            (email, 'prelaunch_landing', 'pending', json.dumps(payload['metadata'])),
        )
        saved = fetch_all('SELECT * FROM waitlist WHERE id = ? LIMIT 1', (row_id,))
        return saved[0] if saved else payload

    async def _send_emails(self, email: str, created_at: str, details: dict[str, str]) -> None:
        if not self.settings.resend_api_key.strip():
            logger.info('RESEND_API_KEY is missing; waitlist emails skipped.')
            return
        await self._send_resend_email(
            to=email,
            subject="You're on the MsAlisia waitlist",
            text=(
                'Thank you for joining the MsAlisia waitlist.\n\n'
                f'Access is scheduled to open on {self._open_date_label()}.\n\n'
                'Francesca and the MsAlisia Team'
            ),
            html=self._waitlist_confirmation_html(),
        )
        detail_lines = [
            f"Parent name: {details['parent_name'] or 'Not provided'}",
            f"Child grade: {details['child_grade'] or 'Not provided'}",
            f"Interest note: {details['interest_note'] or 'Not provided'}",
        ]
        await self._send_resend_email(
            to=self.settings.waitlist_notify_email,
            subject='New MsAlisia Waitlist Signup',
            text=(
                'A new user joined the MsAlisia pre-launch waitlist.\n\n'
                f'Email: {email}\n'
                f"{chr(10).join(detail_lines)}\n"
                'Source: prelaunch_landing\n'
                f'Time: {created_at}'
            ),
        )

    async def _send_resend_email(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        payload = {
            'from': self.settings.resend_from_email,
            'to': [to],
            'subject': subject,
            'text': text,
        }
        if html:
            payload['html'] = html
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

    def _success_message(self) -> str:
        return f"You're on the waitlist. Access is scheduled to open on {self._open_date_label()}."

    def _open_date_label(self) -> str:
        raw_date = self.settings.waitlist_open_date.strip() or '2026-06-15'
        try:
            parsed = datetime.fromisoformat(raw_date)
            return f'{parsed.strftime("%B")} {parsed.day}'
        except Exception:
            try:
                parsed = datetime.strptime(raw_date, '%Y-%m-%d')
                return f'{parsed.strftime("%B")} {parsed.day}'
            except Exception:
                return 'June 15'

    def _waitlist_confirmation_html(self) -> str:
        logo_url = self.settings.email_logo_url.strip() or DEFAULT_EMAIL_LOGO_URL
        safe_logo_url = escape(logo_url, quote=True)
        logo_html = (
            f'<img src="{safe_logo_url}" alt="MsAlisia" width="64" height="64" style="display:block;border-radius:18px;background:#ffffff;object-fit:cover;" />'
        )
        open_date = escape(self._open_date_label())
        return f'''<!doctype html>
<html>
  <body style="margin:0;background:#f7f1ff;font-family:Arial,Helvetica,sans-serif;color:#20173d;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f1ff;margin:0;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#ffffff;border:1px solid #e4d8f7;border-radius:24px;overflow:hidden;box-shadow:0 16px 40px rgba(93,60,150,0.12);">
            <tr>
              <td style="background:#5e3ca0;padding:26px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="vertical-align:middle;">{logo_html}</td>
                    <td style="vertical-align:middle;padding-left:16px;">
                      <div style="font-size:24px;line-height:1.1;font-weight:800;color:#ffffff;">MsAlisia</div>
                      <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#f4d77a;margin-top:6px;">Waitlist confirmation</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 30px 12px;">
                <div style="font-size:13px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#d6a72e;margin-bottom:10px;">You're on the list</div>
                <h1 style="margin:0;color:#5e3ca0;font-size:34px;line-height:1.12;font-weight:900;">Thanks for joining the MsAlisia waitlist.</h1>
                <p style="margin:14px 0 0;color:#5f5576;font-size:17px;line-height:1.6;">Access is scheduled to open on {open_date}. We will reach out when it is your family's turn.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 30px 10px;">
                <div style="background:#fbf8ff;border:1px solid #eadffc;border-radius:16px;padding:18px 20px;margin:22px 0;">
                  <p style="margin:0;color:#5f5576;font-size:16px;line-height:1.6;">MsAlisia supports Grades 3-6 with Math, Reading, and Writing practice, plus parent visibility.</p>
                </div>
              </td>
            </tr>
            <tr>
              <td style="background:#fbf8ff;border-top:1px solid #eadffc;padding:24px 30px;color:#5f5576;font-size:14px;line-height:1.6;">
                <p style="margin:0 0 8px;">Warmly,</p>
                <p style="margin:0;font-weight:800;color:#5e3ca0;">Francesca and the MsAlisia Team</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>'''
