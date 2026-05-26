from pydantic import BaseModel, Field


class SessionStatusResponse(BaseModel):
    child_id: str
    session_id: str | None = None
    session_status: str = 'none'
    active_tutoring_seconds_today: int = 0
    brain_break_required: bool = False
    brain_break_active: bool = False
    break_ends_at: str | None = None
    seconds_until_resume: int = 0
    seconds_until_brain_break: int = 7200
    warnings_due: list[str] = Field(default_factory=list)
    message: str = ''


class SessionActivityRequest(BaseModel):
    child_id: str
    subject: str = 'Math'
    topic: str = 'general practice'
    session_id: str | None = None
    event_type: str = 'activity'


class SessionPauseRequest(BaseModel):
    child_id: str
    session_id: str | None = None
    inactive_seconds: int = 180


class SessionResumeRequest(BaseModel):
    child_id: str
    session_id: str | None = None


class SessionExchangeCompleteRequest(BaseModel):
    child_id: str
    session_id: str | None = None
    subject: str = 'Math'
    topic: str = 'general practice'
