from fastapi import APIRouter, Header

from ..schemas.child_profile import (
    ChildProfileCreateRequest,
    ChildProfileResponse,
    ChildProfilesResponse,
    ChildProfileUpdateRequest,
)
from ..services.auth_user import authenticated_user, bearer_token
from ..services.child_profile_service import ChildProfileService

router = APIRouter(prefix='/children', tags=['child profiles'])


@router.get('', response_model=ChildProfilesResponse)
async def list_children(authorization: str = Header(default='')) -> ChildProfilesResponse:
    user = await authenticated_user(bearer_token(authorization))
    records = await ChildProfileService().list_children(user['id'])
    return ChildProfilesResponse(children=[ChildProfileResponse(**record) for record in records])


@router.post('', response_model=ChildProfileResponse)
async def create_child(payload: ChildProfileCreateRequest, authorization: str = Header(default='')) -> ChildProfileResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await ChildProfileService().create_child(user['id'], payload)
    return ChildProfileResponse(**record)


@router.patch('/{child_id}', response_model=ChildProfileResponse)
async def update_child(child_id: str, payload: ChildProfileUpdateRequest, authorization: str = Header(default='')) -> ChildProfileResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await ChildProfileService().update_child(user['id'], child_id, payload)
    return ChildProfileResponse(**record)


@router.delete('/{child_id}', response_model=ChildProfileResponse)
async def deactivate_child(child_id: str, authorization: str = Header(default='')) -> ChildProfileResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await ChildProfileService().deactivate_child(user['id'], child_id)
    return ChildProfileResponse(**record)
