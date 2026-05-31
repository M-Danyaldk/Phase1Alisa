from fastapi import APIRouter

from ..schemas.waitlist import WaitlistSignupRequest, WaitlistSignupResponse
from ..services.waitlist_service import WaitlistService

router = APIRouter(prefix='/api/waitlist', tags=['waitlist'])


@router.post('/signup', response_model=WaitlistSignupResponse)
async def waitlist_signup(payload: WaitlistSignupRequest) -> WaitlistSignupResponse:
    result = await WaitlistService().signup(
        str(payload.email),
        parent_name=payload.parent_name,
        child_grade=payload.child_grade,
        interest_note=payload.interest_note,
    )
    return WaitlistSignupResponse(**result)
