from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from ..config import get_settings
from ..models import TutoringState
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

VECTOR_SIMILARITY_THRESHOLD = 0.70


class LearningMemoryService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()
        self.settings = get_settings()

    async def latest_for_child_subject(self, child_id: str | None, subject: str) -> dict | None:
        if not child_id or not self.supabase.configured():
            return None
        try:
            rows = await self.supabase.select(
                'learning_session_summaries',
                f'child_id=eq.{quote(child_id)}&subject=eq.{quote(subject)}&order=updated_at.desc&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                return None
            logger.warning('Could not load learning memory for child %s: %s', child_id, exc)
            return None
        return rows[0] if rows else None

    async def relevant_for_child_subject(
        self,
        child_id: str | None,
        subject: str,
        *,
        topic: str | None = None,
        student_message: str | None = None,
        working_level: str | None = None,
        match_count: int = 3,
    ) -> dict | None:
        fallback = await self.latest_for_child_subject(child_id, subject)
        if not child_id or not self.supabase.configured():
            return fallback
        query_text = self._query_embedding_text(
            subject=subject,
            topic=topic,
            student_message=student_message,
            working_level=working_level,
        )
        embedding = await self._generate_embedding(query_text)
        if not embedding:
            return fallback
        try:
            matches = await self.supabase.rpc('match_learning_session_summaries', {
                'query_embedding': self._vector_literal(embedding),
                'match_child_id': child_id,
                'match_subject': subject,
                'match_count': max(1, min(match_count, 10)),
            })
        except SupabaseClientError as exc:
            if not self._missing_vector_support(exc):
                logger.warning('PGVector learning memory search failed for child %s: %s', child_id, exc)
            return fallback
        except Exception as exc:
            logger.warning('PGVector learning memory retrieval failed for child %s: %s', child_id, exc)
            return fallback

        best = matches[0] if matches else None
        if not best:
            return fallback
        try:
            similarity = float(best.get('similarity') or 0)
        except (TypeError, ValueError):
            similarity = 0.0
        if similarity < VECTOR_SIMILARITY_THRESHOLD:
            return fallback
        best['memory_retrieval_method'] = 'pgvector'
        best['memory_similarity'] = similarity
        return best

    async def recent_for_child(self, parent_id: str, child_id: str, limit: int = 6) -> list[dict]:
        if not self.supabase.configured():
            return []
        safe_limit = max(1, min(limit, 20))
        try:
            return await self.supabase.select(
                'learning_session_summaries',
                f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&order=updated_at.desc&limit={safe_limit}',
            )
        except SupabaseClientError as exc:
            if self._missing_table(exc):
                return []
            logger.warning('Could not load parent learning memory for child %s: %s', child_id, exc)
            return []

    def memory_directives(self, memory: dict | None) -> list[str]:
        if not memory:
            return []
        worked_on = self._clean(memory.get('worked_on'))
        struggled_with = self._clean(memory.get('struggled_with'))
        mastered = self._clean(memory.get('mastered'))
        next_step = self._clean(memory.get('next_step'))
        child_summary = self._clean(memory.get('child_facing_summary'))
        parts = []
        if worked_on:
            parts.append(f'last focus: {worked_on}')
        if struggled_with:
            parts.append(f'needed support with: {struggled_with}')
        if mastered:
            parts.append(f'got stronger with: {mastered}')
        if next_step:
            parts.append(f'recommended next step: {next_step}')
        if child_summary:
            parts.append(f'child-friendly reminder: {child_summary}')
        if not parts:
            return []
        return [
            'Use this previous-session memory only if it naturally helps the current same-subject lesson.',
            'If the student is beginning a new session, you may briefly mention the prior focus in a warm way, then ask whether to continue or help with the current question.',
            'Do not mention clinical labels, diagnostics, internal memory fields, or database details to the child.',
            f'Previous learning memory: {"; ".join(parts)}',
        ]

    async def record_exchange_summary(
        self,
        *,
        parent_id: str,
        child_id: str | None,
        subject: str,
        topic: str,
        grade_level: str | None,
        working_level: str | None,
        student_message: str,
        assistant_text: str,
        tutoring_state: TutoringState,
        thread_id: str | None = None,
        session_id: str | None = None,
        source: str = 'session',
        metadata: dict | None = None,
    ) -> None:
        if not child_id or not self.supabase.configured():
            return
        try:
            existing = await self._existing_summary(child_id=child_id, subject=subject, thread_id=thread_id, session_id=session_id)
            payload = self._summary_payload(
                parent_id=parent_id,
                child_id=child_id,
                subject=subject,
                topic=topic,
                grade_level=grade_level,
                working_level=working_level,
                student_message=student_message,
                assistant_text=assistant_text,
                tutoring_state=tutoring_state,
                thread_id=thread_id,
                session_id=session_id,
                source=source,
                existing=existing,
                metadata=metadata or {},
            )
            embedding_payload = await self._embedding_payload(payload)
            write_payload = {**payload, **embedding_payload} if embedding_payload else payload
            try:
                if existing:
                    await self.supabase.update('learning_session_summaries', {'id': f'eq.{existing["id"]}'}, write_payload)
                else:
                    await self.supabase.insert('learning_session_summaries', write_payload)
            except SupabaseClientError as exc:
                if not embedding_payload:
                    raise
                logger.warning('Learning memory embedding write failed; saving structured summary only for child %s: %s', child_id, exc)
                if existing:
                    await self.supabase.update('learning_session_summaries', {'id': f'eq.{existing["id"]}'}, payload)
                else:
                    await self.supabase.insert('learning_session_summaries', payload)
        except SupabaseClientError as exc:
            if not self._missing_table(exc):
                logger.warning('Learning memory summary save failed for child %s: %s', child_id, exc)
        except Exception as exc:
            logger.warning('Learning memory summary generation failed for child %s: %s', child_id, exc)

    async def _existing_summary(self, *, child_id: str, subject: str, thread_id: str | None, session_id: str | None) -> dict | None:
        if thread_id:
            rows = await self.supabase.select(
                'learning_session_summaries',
                f'child_id=eq.{quote(child_id)}&thread_id=eq.{quote(thread_id)}&order=updated_at.desc&limit=1',
            )
            if rows:
                return rows[0]
        if session_id:
            rows = await self.supabase.select(
                'learning_session_summaries',
                f'child_id=eq.{quote(child_id)}&session_id=eq.{quote(session_id)}&order=updated_at.desc&limit=1',
            )
            if rows:
                return rows[0]
        today = datetime.now(UTC).date().isoformat()
        rows = await self.supabase.select(
            'learning_session_summaries',
            f'child_id=eq.{quote(child_id)}&subject=eq.{quote(subject)}&source=eq.session&created_at=gte.{quote(today)}&order=updated_at.desc&limit=1',
        )
        return rows[0] if rows else None

    def _summary_payload(
        self,
        *,
        parent_id: str,
        child_id: str,
        subject: str,
        topic: str,
        grade_level: str | None,
        working_level: str | None,
        student_message: str,
        assistant_text: str,
        tutoring_state: TutoringState,
        thread_id: str | None,
        session_id: str | None,
        source: str,
        existing: dict | None,
        metadata: dict,
    ) -> dict:
        worked_on = self._first_meaningful([
            tutoring_state.skill,
            topic,
            tutoring_state.active_problem,
            student_message,
            self._clean((existing or {}).get('worked_on')),
        ], fallback=f'{subject} practice')
        struggled_with = self._struggle_text(tutoring_state, student_message, existing)
        mastered = self._mastered_text(tutoring_state, assistant_text, existing)
        next_step = self._next_step_text(tutoring_state, topic, existing)
        child_summary = self._child_summary(worked_on, next_step)
        parent_summary = self._parent_summary(worked_on, struggled_with, mastered, next_step)
        now = datetime.now(UTC).isoformat()
        event_count = int(self._metadata(existing).get('exchange_count') or 0) + 1
        return {
            'parent_id': parent_id,
            'child_id': child_id,
            'session_id': session_id,
            'thread_id': thread_id,
            'subject': subject,
            'topic': self._clean(topic) or None,
            'grade_level': grade_level,
            'working_level': working_level,
            'worked_on': worked_on,
            'struggled_with': struggled_with,
            'mastered': mastered,
            'next_step': next_step,
            'child_facing_summary': child_summary,
            'parent_facing_summary': parent_summary,
            'source': source,
            'metadata': {
                **self._metadata(existing),
                **metadata,
                'exchange_count': event_count,
                'last_student_message_preview': self._preview(student_message),
                'last_assistant_message_preview': self._preview(assistant_text),
                'last_tutoring_status': tutoring_state.status,
                'last_correctness_status': tutoring_state.correctness_status,
                'updated_by': 'structured_summary',
            },
            'updated_at': now,
        }

    async def _embedding_payload(self, payload: dict) -> dict:
        embedding_text = self._embedding_text(payload)
        embedding = await self._generate_embedding(embedding_text)
        if not embedding:
            return {}
        return {
            'embedding': self._vector_literal(embedding),
            'embedding_model': self.settings.openai_embedding_model or 'text-embedding-3-small',
            'embedding_text': embedding_text,
            'embedding_updated_at': datetime.now(UTC).isoformat(),
        }

    async def _generate_embedding(self, text: str) -> list[float] | None:
        if not self.settings.openai_api_key:
            return None
        cleaned = self._clean(text)
        if not cleaned:
            return None
        payload = {
            'model': self.settings.openai_embedding_model or 'text-embedding-3-small',
            'input': cleaned[:8000],
        }
        headers = {
            'Authorization': f'Bearer {self.settings.openai_api_key}',
            'Content-Type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.settings.openai_embeddings_api_url, json=payload, headers=headers)
                response.raise_for_status()
            data = response.json()
            embedding = (((data.get('data') or [{}])[0]).get('embedding') or [])
            if isinstance(embedding, list) and embedding:
                return [float(value) for value in embedding]
        except Exception as exc:
            logger.warning('OpenAI embedding generation failed for learning memory: %s', exc)
        return None

    def _embedding_text(self, payload: dict) -> str:
        return '\n'.join([
            f"Subject: {self._clean(payload.get('subject'))}",
            f"Topic: {self._clean(payload.get('topic'))}",
            f"Worked on: {self._clean(payload.get('worked_on'))}",
            f"Struggled with: {self._clean(payload.get('struggled_with'))}",
            f"Mastered: {self._clean(payload.get('mastered'))}",
            f"Next step: {self._clean(payload.get('next_step'))}",
            f"Child summary: {self._clean(payload.get('child_facing_summary'))}",
            f"Parent summary: {self._clean(payload.get('parent_facing_summary'))}",
        ])

    def _query_embedding_text(self, *, subject: str, topic: str | None, student_message: str | None, working_level: str | None) -> str:
        return '\n'.join([
            f'Subject: {self._clean(subject)}',
            f'Topic: {self._clean(topic)}',
            f'Working level: {self._clean(working_level)}',
            f'Current student message: {self._clean(student_message)}',
        ])

    def _vector_literal(self, embedding: list[float]) -> str:
        return '[' + ','.join(f'{value:.8f}' for value in embedding) + ']'

    def _struggle_text(self, state: TutoringState, message: str, existing: dict | None) -> str | None:
        previous = self._clean((existing or {}).get('struggled_with'))
        lower_message = message.lower()
        if state.correctness_status in {'wrong', 'incorrect', 'unclear'} or state.hint_given:
            return self._first_meaningful([state.current_question, state.current_step, state.active_problem, state.skill, previous], fallback='the current practice step')
        if any(phrase in lower_message for phrase in ["i don't know", 'i dont know', 'stuck', 'help me', 'confused']):
            return self._first_meaningful([state.active_problem, state.skill, previous], fallback='getting started with the topic')
        return previous or None

    def _mastered_text(self, state: TutoringState, assistant_text: str, existing: dict | None) -> str | None:
        previous = self._clean((existing or {}).get('mastered'))
        lower_reply = assistant_text.lower()
        if state.correctness_status in {'correct', 'right'} or 'great job' in lower_reply or 'nice work' in lower_reply:
            return self._first_meaningful([state.skill, state.active_problem, previous], fallback='a practice step')
        if state.status == 'finished':
            return self._first_meaningful([state.skill, previous], fallback='the guided example')
        return previous or None

    def _next_step_text(self, state: TutoringState, topic: str, existing: dict | None) -> str:
        return self._first_meaningful([
            state.next_similar_question,
            state.current_question,
            state.current_step,
            self._clean((existing or {}).get('next_step')),
        ], fallback=f'Continue with one short {topic or state.skill or "practice"} step.')

    def _child_summary(self, worked_on: str, next_step: str) -> str:
        return f'Last time we worked on {worked_on}. A good next step is: {next_step}'

    def _parent_summary(self, worked_on: str, struggled_with: str | None, mastered: str | None, next_step: str) -> str:
        parts = [f'Recent focus: {worked_on}.']
        if struggled_with:
            parts.append(f'Needs support with: {struggled_with}.')
        if mastered:
            parts.append(f'Getting stronger with: {mastered}.')
        parts.append(f'Next step: {next_step}')
        return ' '.join(parts)

    def _first_meaningful(self, values: list[object], fallback: str) -> str:
        for value in values:
            cleaned = self._clean(value)
            if cleaned and cleaned.lower() not in {'general practice', 'practice'}:
                return cleaned[:500]
        return fallback

    def _metadata(self, row: dict | None) -> dict:
        value = (row or {}).get('metadata') or {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _preview(self, value: str) -> str:
        return self._clean(value)[:240]

    def _clean(self, value: object) -> str:
        return ' '.join(str(value or '').split()).strip()

    def _missing_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'learning_session_summaries' in message and (
            'schema cache' in message or 'could not find' in message or 'does not exist' in message
        )

    def _missing_vector_support(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return any(token in message for token in (
            'match_learning_session_summaries',
            'query_embedding',
            'vector',
            'embedding',
            'schema cache',
            'could not find',
            'does not exist',
        ))
