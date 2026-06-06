from fastapi import APIRouter, Header, HTTPException

from ..config import get_settings
from ..services.email_service import EmailService

router = APIRouter(prefix='/api/internal/email', tags=['internal email'])


@router.post('/process-due')
async def process_due_email_events(
    authorization: str = Header(default=''),
    x_internal_cron_secret: str = Header(default=''),
) -> dict:
    _require_internal_secret(authorization, x_internal_cron_secret)
    return await EmailService().process_due_events()


@router.post('/process-due-fast')
async def process_due_email_event_batch(
    authorization: str = Header(default=''),
    x_internal_cron_secret: str = Header(default=''),
) -> dict:
    _require_internal_secret(authorization, x_internal_cron_secret)
    return await EmailService().process_due_event_batch()


def _require_internal_secret(authorization: str, x_internal_cron_secret: str) -> None:
    settings = get_settings()
    expected_secret = settings.internal_cron_secret.strip()
    provided_secret = x_internal_cron_secret.strip()
    if authorization.lower().startswith('bearer '):
        provided_secret = authorization[7:].strip()
    if not expected_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail='Internal endpoint access denied.')
