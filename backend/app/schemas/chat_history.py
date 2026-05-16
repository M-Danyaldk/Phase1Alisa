from typing import Any, Literal

from pydantic import BaseModel, Field

Subject = Literal['Math', 'ELA', 'Writing']
MessageRole = Literal['student', 'msalisia']


class ChatThreadCreateRequest(BaseModel):
    child_id: str | None = None
    subject: Subject
    topic: str = Field(default='general practice', min_length=1)
    title: str | None = None


class ChatThreadResponse(BaseModel):
    id: str
    user_id: str
    child_id: str | None = None
    subject: Subject
    topic: str | None = None
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ChatThreadsResponse(BaseModel):
    threads: list[ChatThreadResponse]


class ChatMessageCreateRequest(BaseModel):
    thread_id: str
    child_id: str | None = None
    role: MessageRole
    content: str = Field(min_length=1)
    subject: Subject | None = None
    topic: str | None = None
    provider: str | None = None
    model: str | None = None
    tutoring_state: dict[str, Any] | None = None


class ChatMessageResponse(BaseModel):
    id: str
    thread_id: str
    user_id: str
    child_id: str | None = None
    role: MessageRole
    content: str
    subject: str | None = None
    topic: str | None = None
    provider: str | None = None
    model: str | None = None
    tutoring_state: dict[str, Any] | None = None
    created_at: str | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
