from fastapi import APIRouter, Header

from ..schemas.billing import ChildAccessListResponse, ChildAccessResponse, ChildAccessUpdateRequest
from ..services.auth_user import authenticated_user, bearer_token
from ..services.billing_service import BillingService

router = APIRouter(prefix='/billing', tags=['billing'])


@router.get('/children', response_model=ChildAccessListResponse)
async def child_access_list(authorization: str = Header(default='')) -> ChildAccessListResponse:
    user = await authenticated_user(bearer_token(authorization))
    records = await BillingService().list_child_access(user['id'])
    return ChildAccessListResponse(children=[ChildAccessResponse(**record) for record in records])


@router.patch('/children/{child_id}', response_model=ChildAccessResponse)
async def update_child_access(child_id: str, payload: ChildAccessUpdateRequest, authorization: str = Header(default='')) -> ChildAccessResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await BillingService().update_child_access(user['id'], child_id, payload)
    return ChildAccessResponse(**record)
