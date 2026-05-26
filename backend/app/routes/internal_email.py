from fastapi import APIRouter, Header, HTTPException

from ..config import get_settings
from ..services.email_service import EmailService

router = APIRouter(prefix='/api/internal/email', tags=['internal email'])


@router.post('/process-due')
async def process_due_email_events(
    authorization: str = Header(default=''),
    x_internal_cron_secret: str = Header(default=''),
) -> dict:
    settings = get_settings()
    expected_secret = settings.internal_cron_secret.strip()
    provided_secret = x_internal_cron_secret.strip()
    if authorization.lower().startswith('bearer '):
        provided_secret = authorization[7:].strip()
    if not expected_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail='Internal endpoint access denied.')
    return await EmailService().process_due_events()
