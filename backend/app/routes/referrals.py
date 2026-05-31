from fastapi import APIRouter, Header, HTTPException

from ..config import get_settings
from ..schemas.referrals import ReferralProcessResponse, ReferralSummaryResponse
from ..services.access_control import require_parent_access
from ..services.referral_service import ReferralService

router = APIRouter(prefix='/api/referrals', tags=['referrals'])
internal_router = APIRouter(prefix='/api/internal/referrals', tags=['internal referrals'])


@router.get('/me', response_model=ReferralSummaryResponse)
async def my_referrals(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ReferralSummaryResponse:
    user = await require_parent_access(authorization, x_access_mode)
    result = await ReferralService().parent_summary(user['id'])
    return ReferralSummaryResponse(**result)


@internal_router.post('/process-rewards', response_model=ReferralProcessResponse)
async def process_referral_rewards(
    authorization: str = Header(default=''),
    x_internal_cron_secret: str = Header(default=''),
) -> ReferralProcessResponse:
    settings = get_settings()
    expected_secret = settings.internal_cron_secret.strip()
    provided_secret = x_internal_cron_secret.strip()
    if authorization.lower().startswith('bearer '):
        provided_secret = authorization[7:].strip()
    if not expected_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail='Internal endpoint access denied.')
    result = await ReferralService().process_rewards()
    return ReferralProcessResponse(**result)
