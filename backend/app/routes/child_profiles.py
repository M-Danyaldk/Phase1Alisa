from fastapi import APIRouter, Header

from ..schemas.child_profile import (
    ChildProfileCreateRequest,
    ChildProfileResponse,
    ChildProfilesResponse,
    ChildProfileUpdateRequest,
)
from ..schemas.working_level_override import WorkingLevelOverrideRequest, WorkingLevelOverridesResponse
from ..services.access_control import require_parent_access
from ..services.child_profile_service import ChildProfileService
from ..services.working_level_override_service import WorkingLevelOverrideService

router = APIRouter(prefix='/children', tags=['child profiles'])


@router.get('', response_model=ChildProfilesResponse)
async def list_children(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildProfilesResponse:
    user = await require_parent_access(authorization, x_access_mode)
    records = await ChildProfileService().list_children(user['id'])
    return ChildProfilesResponse(children=[ChildProfileResponse(**record) for record in records])


@router.post('', response_model=ChildProfileResponse)
async def create_child(payload: ChildProfileCreateRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildProfileResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await ChildProfileService().create_child(user['id'], payload)
    return ChildProfileResponse(**record)


@router.patch('/{child_id}', response_model=ChildProfileResponse)
async def update_child(child_id: str, payload: ChildProfileUpdateRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildProfileResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await ChildProfileService().update_child(user['id'], child_id, payload)
    return ChildProfileResponse(**record)


@router.delete('/{child_id}', response_model=ChildProfileResponse)
async def deactivate_child(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildProfileResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await ChildProfileService().deactivate_child(user['id'], child_id)
    return ChildProfileResponse(**record)


@router.post('/{child_id}/reactivate', response_model=ChildProfileResponse)
async def reactivate_child(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildProfileResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await ChildProfileService().reactivate_child(user['id'], child_id)
    return ChildProfileResponse(**record)


@router.get('/{child_id}/working-level-overrides', response_model=WorkingLevelOverridesResponse)
async def working_level_overrides(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> WorkingLevelOverridesResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await WorkingLevelOverrideService().summary_for_child(user['id'], child_id)
    return WorkingLevelOverridesResponse(**record)


@router.post('/{child_id}/working-level-overrides', response_model=WorkingLevelOverridesResponse)
async def set_working_level_override(child_id: str, payload: WorkingLevelOverrideRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> WorkingLevelOverridesResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await WorkingLevelOverrideService().set_override(user['id'], child_id, payload)
    return WorkingLevelOverridesResponse(**record)


@router.delete('/{child_id}/working-level-overrides/{subject}', response_model=WorkingLevelOverridesResponse)
async def reset_working_level_override(child_id: str, subject: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> WorkingLevelOverridesResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await WorkingLevelOverrideService().reset_override(user['id'], child_id, subject)
    return WorkingLevelOverridesResponse(**record)
