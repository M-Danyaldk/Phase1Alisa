from fastapi import APIRouter, Header

from ..schemas.billing import ChildAccessListResponse, ChildAccessResponse, ChildAccessUpdateRequest
from ..services.access_control import require_parent_access
from ..services.billing_service import BillingService

router = APIRouter(prefix='/billing', tags=['billing'])


@router.get('/children', response_model=ChildAccessListResponse)
async def child_access_list(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildAccessListResponse:
    user = await require_parent_access(authorization, x_access_mode)
    records = await BillingService().list_child_access(user['id'])
    return ChildAccessListResponse(children=[ChildAccessResponse(**record) for record in records])


@router.patch('/children/{child_id}', response_model=ChildAccessResponse)
async def update_child_access(child_id: str, payload: ChildAccessUpdateRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildAccessResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await BillingService().update_child_access(user['id'], child_id, payload)
    return ChildAccessResponse(**record)
