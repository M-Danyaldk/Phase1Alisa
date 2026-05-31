import logging
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.data_deletion import DataDeletionRequest
from .email_service import EmailService
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

SUCCESS_MESSAGE = 'Your deletion request has been received. We will review it and contact you if needed.'
PRIVACY_EMAIL = 'privacy@msalisia.com'


class DataDeletionService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def submit_request(self, payload: DataDeletionRequest, access_token: str | None = None) -> dict:
        normalized_email = str(payload.email).strip().lower()
        parent_id = await self._parent_id_from_token(access_token)
        metadata = {
            'parent_name': payload.parent_name.strip(),
            'email': normalized_email,
            'normalized_email': normalized_email,
            'child_name': (payload.child_name or '').strip(),
            'request_details': (payload.request_details or '').strip(),
            'source': 'parent_portal' if parent_id else 'public_form',
            'submitted_at': datetime.now(UTC).isoformat(),
            'status_label': 'pending',
        }
        record = {
            'parent_id': parent_id,
            'requested_by': parent_id,
            'request_scope': 'child' if metadata['child_name'] else 'account',
            'status': 'requested',
            'metadata': metadata,
        }
        try:
            if self.supabase.configured():
                await self.supabase.insert('data_deletion_requests', record)
            else:
                logger.info('Supabase is not configured; data deletion request for %s was not persisted.', normalized_email)
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                raise HTTPException(status_code=503, detail='Data deletion requests are not set up yet. Please run the Supabase migration first.') from exc
            logger.warning('Data deletion request save failed: %s', exc)
            raise HTTPException(status_code=503, detail='We could not submit your request right now. Please try again or contact privacy@msalisia.com.') from exc

        await self._send_privacy_alert(metadata)
        return {'success': True, 'message': SUCCESS_MESSAGE}

    async def _parent_id_from_token(self, access_token: str | None) -> str | None:
        token = (access_token or '').strip()
        if token.lower().startswith('bearer '):
            token = token.split(' ', 1)[1].strip()
        if not token or not self.supabase.configured():
            return None
        try:
            user = await self.supabase.get_user(token)
        except Exception:
            return None
        user_id = user.get('id')
        if not user_id:
            return None
        try:
            profiles = await self.supabase.select('profiles', f'id=eq.{quote(user_id)}&role=eq.parent&select=id&limit=1')
        except Exception:
            return None
        return str(user_id) if profiles else None

    async def _send_privacy_alert(self, metadata: dict) -> None:
        text = (
            'A data deletion request was submitted.\n\n'
            f"Parent name: {metadata.get('parent_name') or 'Not provided'}\n"
            f"Email: {metadata.get('email') or 'Not provided'}\n"
            f"Child name: {metadata.get('child_name') or 'Not provided'}\n"
            f"Source: {metadata.get('source') or 'unknown'}\n"
            f"Submitted at: {metadata.get('submitted_at') or ''}\n\n"
            f"Request details: {metadata.get('request_details') or 'Not provided'}"
        )
        try:
            await EmailService().send_support_alert(
                recipient_email=PRIVACY_EMAIL,
                subject='New MsAlisia data deletion request',
                text=text,
            )
        except Exception as exc:
            logger.warning('Privacy deletion alert email was not sent: %s', exc)

    def _missing_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'data_deletion_requests' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
