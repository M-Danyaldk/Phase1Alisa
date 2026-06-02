from fastapi import APIRouter, Header, HTTPException

from ..schemas.student_auth import (
    FamilyClassroomLinkResponse,
    StudentAccessResponse,
    StudentAccessUpsertRequest,
    StudentLoginRequest,
    StudentLogoutResponse,
    StudentMeResponse,
    StudentSessionResponse,
)
from ..services.access_control import require_parent_access
from ..services.student_auth_service import StudentAuthService

router = APIRouter(tags=['student auth'])


def _bearer_token(authorization: str) -> str:
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Student session is required.')
    token = authorization.split(' ', 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Student session is required.')
    return token


@router.get('/children/{child_id}/student-access', response_model=StudentAccessResponse | None)
async def get_student_access(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> StudentAccessResponse | None:
    user = await require_parent_access(authorization, x_access_mode)
    record = await StudentAuthService().get_student_access(user['id'], child_id)
    return StudentAccessResponse(**record) if record else None


@router.put('/children/{child_id}/student-access', response_model=StudentAccessResponse)
async def upsert_student_access(child_id: str, payload: StudentAccessUpsertRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> StudentAccessResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await StudentAuthService().upsert_student_access(user['id'], child_id, payload)
    return StudentAccessResponse(**record)


@router.get('/student/family-classroom-link', response_model=FamilyClassroomLinkResponse)
async def family_classroom_link(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> FamilyClassroomLinkResponse:
    user = await require_parent_access(authorization, x_access_mode)
    result = await StudentAuthService().get_or_create_family_classroom_link(user['id'])
    return FamilyClassroomLinkResponse(**result)


@router.post('/student/login', response_model=StudentSessionResponse)
async def student_login(payload: StudentLoginRequest) -> StudentSessionResponse:
    result = await StudentAuthService().login(payload)
    return StudentSessionResponse(**result)


@router.get('/student/me', response_model=StudentMeResponse)
async def student_me(authorization: str = Header(default='')) -> StudentMeResponse:
    result = await StudentAuthService().current_student(_bearer_token(authorization))
    return StudentMeResponse(**result)


@router.post('/student/logout', response_model=StudentLogoutResponse)
async def student_logout(authorization: str = Header(default='')) -> StudentLogoutResponse:
    result = await StudentAuthService().logout(_bearer_token(authorization))
    return StudentLogoutResponse(**result)
