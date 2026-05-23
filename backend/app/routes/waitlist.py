from fastapi import APIRouter

from ..schemas.waitlist import WaitlistSignupRequest, WaitlistSignupResponse
from ..services.waitlist_service import WaitlistService

router = APIRouter(prefix='/api/waitlist', tags=['waitlist'])


@router.post('/signup', response_model=WaitlistSignupResponse)
async def waitlist_signup(payload: WaitlistSignupRequest) -> WaitlistSignupResponse:
    result = await WaitlistService().signup(str(payload.email))
    return WaitlistSignupResponse(**result)
