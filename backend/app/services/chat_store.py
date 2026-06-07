from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.chat_history import ChatMessageCreateRequest, ChatThreadCreateRequest
from .supabase_client import SupabaseClient, SupabaseClientError


class ChatStore:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def list_threads(self, user_id: str, child_id: str | None = None, subject: str | None = None, limit: int = 30) -> list[dict]:
        if child_id:
            await self._ensure_child_for_user(user_id, child_id)
        safe_limit = max(1, min(limit, 100))
        query = f'user_id=eq.{quote(user_id)}&order=updated_at.desc&limit={safe_limit}'
        if child_id:
            query = f'user_id=eq.{quote(user_id)}&child_id=eq.{quote(child_id)}&order=updated_at.desc&limit={safe_limit}'
        if subject:
            child_filter = f'&child_id=eq.{quote(child_id)}' if child_id else ''
            query = f'user_id=eq.{quote(user_id)}{child_filter}&subject=eq.{quote(subject)}&order=updated_at.desc&limit={safe_limit}'
        try:
            return await self.supabase.select('chat_threads', query)
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                return []
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def create_thread(self, user_id: str, payload: ChatThreadCreateRequest) -> dict:
        if payload.child_id:
            await self._ensure_child_for_user(user_id, payload.child_id)
        now = datetime.now(UTC).isoformat()
        topic = self._safe_topic(payload.subject, payload.topic)
        title = (payload.title or '').strip() or self._title_from_topic(payload.subject, topic)
        try:
            records = await self.supabase.insert('chat_threads', {
                'user_id': user_id,
                'child_id': payload.child_id,
                'subject': payload.subject,
                'topic': topic,
                'title': title,
                'created_at': now,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                raise HTTPException(status_code=503, detail='Chat history is not set up for child profiles yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not create chat thread.')
        return records[0]

    async def get_thread_for_user(self, user_id: str, thread_id: str, child_id: str | None = None) -> dict:
        if child_id:
            await self._ensure_child_for_user(user_id, child_id)
        child_filter = f'&child_id=eq.{quote(child_id)}' if child_id else ''
        try:
            records = await self.supabase.select(
                'chat_threads',
                f'id=eq.{quote(thread_id)}&user_id=eq.{quote(user_id)}{child_filter}&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                raise HTTPException(status_code=503, detail='Chat history is not set up for child profiles yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Chat thread not found.')
        return records[0]

    async def list_messages(self, user_id: str, thread_id: str, child_id: str | None = None, limit: int = 100) -> list[dict]:
        await self.get_thread_for_user(user_id, thread_id, child_id=child_id)
        safe_limit = max(1, min(limit, 200))
        child_filter = f'&child_id=eq.{quote(child_id)}' if child_id else ''
        try:
            return await self.supabase.select(
                'chat_messages',
                f'thread_id=eq.{quote(thread_id)}&user_id=eq.{quote(user_id)}{child_filter}&order=created_at.asc&limit={safe_limit}',
            )
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                return []
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def store_message(self, user_id: str, payload: ChatMessageCreateRequest) -> dict:
        thread = await self.get_thread_for_user(user_id, payload.thread_id, child_id=payload.child_id)
        subject = payload.subject or thread.get('subject')
        topic = payload.topic or thread.get('topic')
        child_id = payload.child_id or thread.get('child_id')
        try:
            records = await self.supabase.insert('chat_messages', {
                'thread_id': payload.thread_id,
                'user_id': user_id,
                'child_id': child_id,
                'role': payload.role,
                'content': payload.content,
                'subject': subject,
                'topic': topic,
                'provider': payload.provider,
                'model': payload.model,
                'tutoring_state': payload.tutoring_state,
            })
            await self.touch_thread(user_id, payload.thread_id)
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                raise HTTPException(status_code=503, detail='Chat history is not set up for child profiles yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not store chat message.')
        return records[0]

    async def touch_thread(self, user_id: str, thread_id: str) -> None:
        await self.get_thread_for_user(user_id, thread_id)
        try:
            await self.supabase.update('chat_threads', {
                'id': f'eq.{thread_id}',
                'user_id': f'eq.{user_id}',
            }, {'updated_at': datetime.now(UTC).isoformat()})
        except SupabaseClientError as exc:
            if self._missing_chat_child_schema(exc):
                raise HTTPException(status_code=503, detail='Chat history is not set up for child profiles yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    def _title_from_topic(self, subject: str, topic: str) -> str:
        cleaned = ' '.join(topic.split()).strip()
        if len(cleaned) < 3:
            return f'{self._subject_label(subject)} Practice'
        return f'{self._subject_label(subject)} Practice - {cleaned[:48]}'

    def _subject_label(self, subject: str) -> str:
        return 'Reading' if subject == 'ELA' else (subject or 'Learning')

    def _safe_topic(self, subject: str, topic: str) -> str:
        cleaned = ' '.join(str(topic or '').split()).strip(' .,:;-()[]')
        lowered = cleaned.lower()
        raw_markers = ('i need help', "i don't know", 'i dont know', 'good try', 'you are close', "you're close", 'student:', 'msalisia:')
        if len(cleaned) >= 3 and any(char.isalpha() for char in cleaned) and not any(marker in lowered for marker in raw_markers):
            return cleaned[:80]
        if subject == 'Math':
            return 'multiplication facts'
        if subject == 'ELA':
            return 'reading vocabulary'
        if subject == 'Writing':
            return 'sentence writing'
        return 'guided practice'

    async def _ensure_child_for_user(self, user_id: str, child_id: str) -> None:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(user_id)}&status=neq.inactive&limit=1',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')

    def _missing_chat_child_schema(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return (
            ('chat_threads.child_id' in message or 'chat_messages.child_id' in message or "'child_id'" in message or 'child_id column' in message)
            and ('does not exist' in message or 'schema cache' in message or 'could not find' in message)
        )
