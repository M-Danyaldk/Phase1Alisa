from fastapi import APIRouter, Header

from ..schemas.session_activity import (
    SessionActivityRequest,
    SessionExchangeCompleteRequest,
    SessionPauseRequest,
    SessionResumeRequest,
    SessionStatusResponse,
)
from ..services.access_control import require_student_child_access
from ..services.session_activity_service import SessionActivityService

router = APIRouter(prefix='/api/session', tags=['session activity'])


@router.get('/status', response_model=SessionStatusResponse)
async def session_status(child_id: str, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, child_id)
    return await SessionActivityService().status(access['id'], access['child_id'])


@router.post('/activity', response_model=SessionStatusResponse)
async def record_session_activity(payload: SessionActivityRequest, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    return await SessionActivityService().record_activity(
        access['id'],
        access['child_id'],
        subject=payload.subject,
        topic=payload.topic,
        session_id=payload.session_id,
        event_type=payload.event_type,
    )


@router.post('/inactivity-nudge', response_model=SessionStatusResponse)
async def record_inactivity_nudge(payload: SessionResumeRequest, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    return await SessionActivityService().record_inactivity_nudge(access['id'], access['child_id'], payload.session_id)


@router.post('/exchange-complete', response_model=SessionStatusResponse)
async def record_exchange_complete(payload: SessionExchangeCompleteRequest, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    return await SessionActivityService().exchange_complete(
        access['id'],
        access['child_id'],
        subject=payload.subject,
        topic=payload.topic,
        session_id=payload.session_id,
    )


@router.post('/pause-inactive', response_model=SessionStatusResponse)
async def pause_inactive_session(payload: SessionPauseRequest, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    return await SessionActivityService().pause_inactive(
        access['id'],
        access['child_id'],
        session_id=payload.session_id,
        inactive_seconds=payload.inactive_seconds,
    )


@router.post('/resume', response_model=SessionStatusResponse)
async def resume_session(payload: SessionResumeRequest, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    return await SessionActivityService().resume(access['id'], access['child_id'], payload.session_id)


@router.get('/brain-break/status', response_model=SessionStatusResponse)
async def brain_break_status(child_id: str, authorization: str = Header(default='')) -> SessionStatusResponse:
    access = await require_student_child_access(authorization, child_id)
    return await SessionActivityService().status(access['id'], access['child_id'])
