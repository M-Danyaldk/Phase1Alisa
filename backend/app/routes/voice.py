from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from ..models import ChatHistoryItem, StudentProfile, TutoringState
from ..schemas.voice import VoiceMessageResponse, VoiceNudgeRequest, VoiceNudgeResponse
from ..services.access_control import require_student_child_access
from ..services.voice_service import VoiceService, parse_voice_json

router = APIRouter(prefix='/api/voice', tags=['voice'])


@router.post('/message', response_model=VoiceMessageResponse)
async def voice_message(
    audio: UploadFile = File(...),
    student_json: str = Form(...),
    child_id: str = Form(...),
    subject: str = Form('Math'),
    topic: str = Form('general practice'),
    topic_source: str = Form('manual'),
    history_json: str = Form('[]'),
    tutoring_state_json: str = Form('{}'),
    thread_id: str | None = Form(default=None),
    authorization: str = Header(default=''),
) -> VoiceMessageResponse:
    access = await require_student_child_access(authorization, child_id)
    try:
        student = StudentProfile.model_validate_json(student_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail='Invalid student payload.') from exc

    if subject not in {'Math', 'ELA', 'Writing'}:
        raise HTTPException(status_code=422, detail='Subject must be Math, ELA, or Writing.')
    if topic_source not in {'manual', 'default', 'assessment'}:
        topic_source = 'manual'

    history_payload = parse_voice_json(history_json, [])
    state_payload = parse_voice_json(tutoring_state_json, {})
    try:
        history = [ChatHistoryItem.model_validate(item) for item in history_payload[-12:]]
    except Exception:
        history = []
    try:
        tutoring_state = TutoringState.model_validate(state_payload)
    except Exception:
        tutoring_state = TutoringState()

    return await VoiceService().handle_message(
        parent_id=access['id'],
        child=access['child'],
        audio=audio,
        student=student,
        subject=subject,
        topic=topic,
        topic_source=topic_source,
        history=history,
        tutoring_state=tutoring_state,
        thread_id=thread_id,
    )


@router.post('/nudge', response_model=VoiceNudgeResponse)
async def voice_nudge(
    payload: VoiceNudgeRequest,
    authorization: str = Header(default=''),
) -> VoiceNudgeResponse:
    access = await require_student_child_access(authorization, payload.child_id)
    result = await VoiceService().synthesize_nudge(
        parent_id=access['id'],
        child=access['child'],
        message=payload.message,
    )
    return VoiceNudgeResponse(
        assistant_audio_base64=result.assistant_audio_base64,
        audio_mime_type=result.audio_mime_type,
        fallback_to_chat=result.fallback_to_chat,
        error_message=result.error_message,
        tts_model=result.tts_model,
        timings=result.timings,
    )
