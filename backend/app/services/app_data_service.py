from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..database import execute, fetch_all
from ..models import StudentProfile
from .supabase_client import SupabaseClient, SupabaseClientError


class AppDataService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def save_student(self, student: StudentProfile) -> str | int:
        payload = {
            'name': student.name,
            'grade': student.grade,
            'math_level': student.math_level,
            'ela_level': student.ela_level,
            'writing_level': student.writing_level,
            'confidence': student.confidence,
            'focus_notes': student.focus_notes,
            'parent_notes': student.parent_notes,
        }
        if self.supabase.configured():
            try:
                records = await self.supabase.insert('students', payload)
                if records:
                    return records[0].get('id', '')
            except SupabaseClientError:
                pass
        return execute(
            'INSERT INTO students(name, grade, math_level, ela_level, writing_level, confidence, focus_notes, parent_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (student.name, student.grade, student.math_level, student.ela_level, student.writing_level, student.confidence, student.focus_notes, student.parent_notes),
        )

    async def list_students(self, limit: int = 50) -> list[dict]:
        if self.supabase.configured():
            try:
                return await self.supabase.select('students', f'order=created_at.desc&limit={limit}')
            except SupabaseClientError:
                return []
        return fetch_all('SELECT * FROM students ORDER BY created_at DESC LIMIT ?', (limit,))

    async def save_assessment(self, payload: dict) -> dict:
        if self.supabase.configured():
            last_error: SupabaseClientError | None = None
            for candidate in self._assessment_payload_candidates(payload):
                try:
                    records = await self.supabase.insert('assessment_results', candidate)
                    return records[0] if records else candidate
                except SupabaseClientError as exc:
                    last_error = exc
                    if not self._compatible_assessment_schema_error(exc):
                        raise
            if last_error:
                raise last_error
        assessment_id = execute(
            'INSERT INTO assessment_results(child_id, student_name, subject, estimated_level, learning_gaps, recommended_progression, recommended_next_topics, parent_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                payload.get('child_id'),
                payload.get('student_name'),
                payload.get('subject'),
                payload.get('estimated_level'),
                self._json_text(payload.get('learning_gaps')),
                self._json_text(payload.get('recommended_progression')),
                self._json_text(payload.get('recommended_next_topics')),
                payload.get('parent_summary'),
            ),
        )
        return {**payload, 'id': assessment_id}

    def _assessment_payload_candidates(self, payload: dict) -> list[dict]:
        optional_columns = {
            'parent_id',
            'assessment_type',
            'result_summary',
            'growth_areas',
        }
        candidates = [dict(payload)]
        without_optional = {key: value for key, value in payload.items() if key not in optional_columns}
        if without_optional != candidates[0]:
            candidates.append(without_optional)
        without_next_topics = {key: value for key, value in without_optional.items() if key != 'recommended_next_topics'}
        if without_next_topics != candidates[-1]:
            candidates.append(without_next_topics)
        return candidates

    def _compatible_assessment_schema_error(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        optional_columns = ['parent_id', 'assessment_type', 'result_summary', 'growth_areas', 'recommended_next_topics']
        return any(column in message for column in optional_columns) and (
            'schema cache' in message or 'column' in message or 'could not find' in message
        )

    def _json_text(self, value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value or [])

    async def list_assessments(self, limit: int = 10) -> list[dict]:
        if self.supabase.configured():
            try:
                return await self.supabase.select('assessment_results', f'order=created_at.desc&limit={limit}')
            except SupabaseClientError:
                return []
        return fetch_all('SELECT * FROM assessment_results ORDER BY created_at DESC LIMIT ?', (limit,))

    async def list_assessments_for_child(self, child_id: str, limit: int = 20) -> list[dict]:
        if self.supabase.configured():
            try:
                return await self.supabase.select(
                    'assessment_results',
                    f'child_id=eq.{child_id}&order=created_at.desc&limit={limit}',
                )
            except SupabaseClientError:
                return []
        return fetch_all(
            'SELECT * FROM assessment_results WHERE child_id = ? ORDER BY created_at DESC LIMIT ?',
            (child_id, limit),
        )

    async def record_llm_event(self, provider: str, model: str, purpose: str, fallback_used: bool) -> None:
        payload = {
            'provider': provider,
            'model': model,
            'purpose': purpose,
            'fallback_used': fallback_used,
        }
        if self.supabase.configured():
            try:
                await self.supabase.insert('llm_events', payload)
                return
            except SupabaseClientError:
                pass
        execute(
            'INSERT INTO llm_events(provider, model, purpose, fallback_used) VALUES (?, ?, ?, ?)',
            (provider, model, purpose, int(fallback_used)),
        )

    async def list_llm_events(self, limit: int = 20) -> list[dict]:
        if self.supabase.configured():
            try:
                return await self.supabase.select('llm_events', f'order=created_at.desc&limit={limit}')
            except SupabaseClientError:
                return []
        return fetch_all('SELECT * FROM llm_events ORDER BY created_at DESC LIMIT ?', (limit,))

    async def upload_homework_file(self, file: UploadFile, child_id: str | None = None) -> dict:
        safe_name = Path(file.filename or 'upload').name
        extension = Path(safe_name).suffix
        stored_name = f'{uuid4().hex}{extension}'
        content = await file.read()
        content_type = file.content_type or 'application/octet-stream'

        if self.supabase.configured():
            try:
                await self.supabase.ensure_storage_bucket('homework-uploads', public=False)
                storage_path = f'{child_id or "legacy"}/{stored_name}'
                await self.supabase.upload_storage_file('homework-uploads', storage_path, content, content_type)
                return {
                    'file_name': safe_name,
                    'stored_name': stored_name,
                    'storage_bucket': 'homework-uploads',
                    'storage_path': storage_path,
                    'size_bytes': len(content),
                    'uploaded_at': datetime.now(UTC).isoformat(),
                }
            except SupabaseClientError:
                pass

        return {
            'file_name': safe_name,
            'stored_name': stored_name,
            'content': content,
            'size_bytes': len(content),
            'uploaded_at': datetime.now(UTC).isoformat(),
        }
