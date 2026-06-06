from fastapi import APIRouter, File, Form, Header, Query, UploadFile

from ..schemas.homework import HomeworkHistoryResponse, HomeworkUploadResponse
from ..services.access_control import ensure_child_billing_access, ensure_child_for_parent, require_child_access, require_parent_access
from ..services.homework_service import HomeworkService

router = APIRouter(prefix='/api/homework', tags=['homework'])
parent_router = APIRouter(prefix='/api/parent/homework', tags=['parent homework'])


@router.post('/upload', response_model=HomeworkUploadResponse)
async def upload_homework(
    child_id: str = Form(...),
    file: UploadFile = File(...),
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> HomeworkUploadResponse:
    access = await require_child_access(authorization, child_id, x_access_mode)
    return await HomeworkService().upload_for_child_session(
        parent_id=access['id'],
        child_id=child_id,
        file=file,
    )


@router.get('/child/{child_id}/history', response_model=HomeworkHistoryResponse)
async def homework_history_for_parent(
    child_id: str,
    limit: int = Query(default=25, ge=1, le=50),
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> HomeworkHistoryResponse:
    user = await require_parent_access(authorization, x_access_mode)
    child = await ensure_child_for_parent(user['id'], child_id)
    await ensure_child_billing_access(child_id, child_name=child.get('name'))
    return await HomeworkService().history_for_parent(user['id'], child_id, limit=limit)


@router.get('/history', response_model=HomeworkHistoryResponse)
async def homework_history_for_student(
    child_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=50),
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> HomeworkHistoryResponse:
    access = await require_child_access(authorization, child_id, x_access_mode)
    return await HomeworkService().history_for_child_session(access['id'], child_id, limit=limit)


@parent_router.post('/upload', response_model=HomeworkUploadResponse)
async def parent_upload_homework(
    child_id: str = Form(...),
    file: UploadFile = File(...),
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> HomeworkUploadResponse:
    user = await require_parent_access(authorization, x_access_mode)
    child = await ensure_child_for_parent(user['id'], child_id)
    await ensure_child_billing_access(child_id, child_name=child.get('name'))
    return await HomeworkService().upload_for_parent(user['id'], child_id, file)
