from typing import Any, Literal

from pydantic import BaseModel, Field

from ..models import TutoringState

Subject = Literal['Math', 'ELA', 'Writing']
TopicSource = Literal['manual', 'default', 'assessment']


class VoiceMessageResponse(BaseModel):
    transcript: str = ''
    assistant_text: str
    assistant_audio_base64: str | None = None
    audio_mime_type: str | None = None
    thread_id: str | None = None
    chat_message_id: str | None = None
    voice_session_id: str | None = None
    fallback_to_chat: bool = False
    error_message: str | None = None
    provider: str = 'unknown'
    model: str = 'unknown'
    tts_model: str | None = None
    tutoring_state: TutoringState = Field(default_factory=TutoringState)
    history_saved: bool = False
    history_error: str | None = None
    resolved_topic: str | None = None
    topic_source: str | None = None
    assessed_level: str | None = None
    timings: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceNudgeRequest(BaseModel):
    child_id: str
    message: str = Field(min_length=1, max_length=240)


class VoiceNudgeResponse(BaseModel):
    assistant_audio_base64: str | None = None
    audio_mime_type: str | None = None
    fallback_to_chat: bool = False
    error_message: str | None = None
    tts_model: str | None = None
    timings: dict[str, int] = Field(default_factory=dict)
