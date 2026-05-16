from fastapi import APIRouter, Header, Query

from ..schemas.chat_history import (
    ChatHistoryResponse,
    ChatMessageCreateRequest,
    ChatMessageResponse,
    ChatThreadCreateRequest,
    ChatThreadResponse,
    ChatThreadsResponse,
)
from ..services.auth_user import authenticated_user, bearer_token
from ..services.chat_store import ChatStore

router = APIRouter(prefix='/chat', tags=['chat history'])


@router.get('/threads', response_model=ChatThreadsResponse)
async def list_threads(
    child_id: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    authorization: str = Header(default=''),
) -> ChatThreadsResponse:
    user = await authenticated_user(bearer_token(authorization))
    records = await ChatStore().list_threads(user['id'], child_id=child_id, subject=subject, limit=limit)
    return ChatThreadsResponse(threads=[ChatThreadResponse(**record) for record in records])


@router.post('/threads', response_model=ChatThreadResponse)
async def create_thread(payload: ChatThreadCreateRequest, authorization: str = Header(default='')) -> ChatThreadResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await ChatStore().create_thread(user['id'], payload)
    return ChatThreadResponse(**record)


@router.get('/history', response_model=ChatHistoryResponse)
async def history(
    thread_id: str,
    child_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    authorization: str = Header(default=''),
) -> ChatHistoryResponse:
    user = await authenticated_user(bearer_token(authorization))
    records = await ChatStore().list_messages(user['id'], thread_id, child_id=child_id, limit=limit)
    return ChatHistoryResponse(messages=[ChatMessageResponse(**record) for record in records])


@router.post('/messages', response_model=ChatMessageResponse)
async def store_message(payload: ChatMessageCreateRequest, authorization: str = Header(default='')) -> ChatMessageResponse:
    user = await authenticated_user(bearer_token(authorization))
    record = await ChatStore().store_message(user['id'], payload)
    return ChatMessageResponse(**record)
