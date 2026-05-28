import base64
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException, UploadFile

from ..config import get_settings
from ..schemas.homework import HomeworkHistoryResponse, HomeworkUploadResponse, HomeworkValidation
from .access_control import ensure_child_billing_access, ensure_child_for_parent
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

HOMEWORK_BUCKET = 'homework-uploads'
MAX_HOMEWORK_BYTES = 15 * 1024 * 1024
SUPPORTED_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/heic': 'heic',
    'image/heif': 'heic',
    'application/pdf': 'pdf',
}
SUPPORTED_EXTENSIONS = {
    '.jpg': ('image/jpeg', 'jpg'),
    '.jpeg': ('image/jpeg', 'jpeg'),
    '.png': ('image/png', 'png'),
    '.heic': ('image/heic', 'heic'),
    '.heif': ('image/heif', 'heic'),
    '.pdf': ('application/pdf', 'pdf'),
}


class HomeworkService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def upload_for_child_session(self, parent_id: str, child_id: str, file: UploadFile, session_id: str | None = None) -> HomeworkUploadResponse:
        child = await ensure_child_for_parent(parent_id, child_id)
        await ensure_child_billing_access(child_id, child_name=child.get('name'))
        return await self._upload(
            parent_id=parent_id,
            child_id=child_id,
            file=file,
            uploader_type='child',
            source='student_upload',
            uploaded_by_user_id=parent_id,
            metadata={'student_session_id': session_id} if session_id else {},
        )

    async def upload_for_parent(self, parent_id: str, child_id: str, file: UploadFile) -> HomeworkUploadResponse:
        child = await ensure_child_for_parent(parent_id, child_id)
        await ensure_child_billing_access(child_id, child_name=child.get('name'))
        return await self._upload(
            parent_id=parent_id,
            child_id=child_id,
            file=file,
            uploader_type='parent',
            source='parent_upload',
            uploaded_by_user_id=parent_id,
            metadata={'uploaded_from': 'parent_dashboard'},
        )

    async def history_for_parent(self, parent_id: str, child_id: str, limit: int = 25) -> HomeworkHistoryResponse:
        child = await ensure_child_for_parent(parent_id, child_id)
        rows = await self._history_rows(child_id, limit)
        uploads = [self._history_item(row, child.get('name')) for row in rows]
        return HomeworkHistoryResponse(child_id=child_id, uploads=uploads)

    async def history_for_child_session(self, parent_id: str, child_id: str, limit: int = 25) -> HomeworkHistoryResponse:
        child = await ensure_child_for_parent(parent_id, child_id)
        await ensure_child_billing_access(child_id, child_name=child.get('name'))
        rows = await self._history_rows(child_id, limit)
        uploads = [self._history_item(row, child.get('name')) for row in rows]
        return HomeworkHistoryResponse(child_id=child_id, uploads=uploads)

    async def _upload(
        self,
        parent_id: str,
        child_id: str,
        file: UploadFile,
        uploader_type: str,
        source: str,
        uploaded_by_user_id: str | None,
        metadata: dict,
    ) -> HomeworkUploadResponse:
        safe_name, mime_type, file_type = self._validate_file_identity(file)
        content = await file.read()
        if not content:
            raise HTTPException(status_code=422, detail='Please upload a homework photo or PDF first.')
        if len(content) > MAX_HOMEWORK_BYTES:
            raise HTTPException(status_code=413, detail='That file is too large. Please upload a file under 15 MB.')

        stored_name = f'{uuid4().hex}.{file_type}'
        storage_path = f'{child_id}/{stored_name}'
        await self._store_file(storage_path, content, mime_type)

        validation = await self._validate_with_ai(
            file_name=safe_name,
            content=content,
            mime_type=mime_type,
            file_type=file_type,
        )
        now = datetime.now(UTC).isoformat()
        record = {
            'parent_id': parent_id,
            'child_id': child_id,
            'uploaded_by_user_id': uploaded_by_user_id,
            'uploader_type': uploader_type,
            'source': source,
            'file_name': safe_name,
            'file_type': file_type,
            'storage_bucket': HOMEWORK_BUCKET,
            'storage_path': storage_path,
            'file_size_bytes': len(content),
            'upload_status': 'uploaded',
            'ai_validation_status': validation.status,
            'ai_validation_summary': validation.summary,
            'unclear_image': validation.is_unclear,
            'detected_subject': validation.detected_subject,
            'parent_report_visible': True,
            'metadata': {
                **metadata,
                'mime_type': mime_type,
                'suggested_next_step': validation.suggested_next_step,
                'problem_overview': validation.problem_overview,
                'needs_better_upload': validation.needs_better_upload,
                'validation_provider': validation.provider,
                'validation_model': validation.model,
            },
            'created_at': now,
            'updated_at': now,
        }
        row = await self._insert_upload(record)
        return self._upload_response(row, mime_type=mime_type)

    def _validate_file_identity(self, file: UploadFile) -> tuple[str, str, str]:
        safe_name = Path(file.filename or 'homework-upload').name
        suffix = Path(safe_name).suffix.lower()
        content_type = (file.content_type or '').split(';', 1)[0].strip().lower()
        if content_type in SUPPORTED_TYPES:
            file_type = SUPPORTED_TYPES[content_type]
            if file_type == 'jpg' and suffix == '.jpeg':
                file_type = 'jpeg'
            return safe_name, content_type, file_type
        if suffix in SUPPORTED_EXTENSIONS:
            mime_type, file_type = SUPPORTED_EXTENSIONS[suffix]
            return safe_name, mime_type, file_type
        raise HTTPException(status_code=422, detail='Please upload homework as a JPG, PNG, HEIC, HEIF, or PDF file.')

    async def _store_file(self, storage_path: str, content: bytes, mime_type: str) -> None:
        try:
            await self.supabase.ensure_storage_bucket(HOMEWORK_BUCKET, public=False)
            await self.supabase.upload_storage_file(HOMEWORK_BUCKET, storage_path, content, mime_type)
        except SupabaseClientError as exc:
            logger.warning('Homework storage upload failed: %s', exc)
            raise HTTPException(status_code=500, detail='We could not save that homework file. Please try again.') from exc

    async def _insert_upload(self, record: dict) -> dict:
        try:
            rows = await self.supabase.insert('homework_uploads', record)
        except SupabaseClientError as exc:
            logger.warning('Homework upload record insert failed: %s', exc)
            raise HTTPException(status_code=500, detail='The file uploaded, but we could not save the homework history. Please try again.') from exc
        if not rows:
            raise HTTPException(status_code=500, detail='We could not save the homework history. Please try again.')
        return rows[0]

    async def _history_rows(self, child_id: str, limit: int) -> list[dict]:
        try:
            return await self.supabase.select(
                'homework_uploads',
                f'child_id=eq.{quote(child_id)}&parent_report_visible=eq.true&order=created_at.desc&limit={max(1, min(limit, 50))}',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail='Could not load homework history right now.') from exc

    async def _validate_with_ai(self, file_name: str, content: bytes, mime_type: str, file_type: str) -> HomeworkValidation:
        if file_type == 'heic':
            return HomeworkValidation(
                status='skipped',
                summary='Your homework file was uploaded. HEIC photos are saved, but Ms. Alisia may need a JPG or PNG photo to read it clearly.',
                is_unclear=True,
                needs_better_upload=True,
                suggested_next_step='If the preview is not readable, take another photo as JPG or PNG in good light.',
            )
        if file_type not in {'jpg', 'jpeg', 'png', 'pdf'}:
            return HomeworkValidation(
                status='skipped',
                summary='Your homework file was uploaded, but this format cannot be reviewed automatically yet.',
                is_unclear=True,
                needs_better_upload=True,
                suggested_next_step='Upload a clear JPG, PNG, or PDF so Ms. Alisia can review it before tutoring.',
            )
        if not self.settings.anthropic_api_key.strip():
            return HomeworkValidation(
                status='skipped',
                summary='Your homework file was uploaded. Ms. Alisia needs Claude connected before she can review the file contents.',
                suggested_next_step='Try again after homework AI validation is connected.',
            )

        model = self.settings.homework_anthropic_model.strip() or self.settings.anthropic_model
        system = self._validation_system_prompt()
        user_content = self._anthropic_user_content(file_name, content, mime_type, file_type)
        payload = {
            'model': model,
            'max_tokens': min(self.settings.homework_max_output_tokens, 1200),
            'temperature': 0.2,
            'system': system,
            'messages': [{'role': 'user', 'content': user_content}],
        }
        headers = {
            'x-api-key': self.settings.anthropic_api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.settings.anthropic_api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning('Homework Claude validation failed: %s', exc)
            return HomeworkValidation(
                status='failed',
                summary='Your homework file was uploaded, but Ms. Alisia could not review it just now. Please try again in a moment.',
                suggested_next_step='Retry validation or upload a clearer photo if the file may be hard to read.',
                provider='claude',
                model=model,
            )

        text = self._response_text(data)
        parsed = self._parse_validation_json(text)
        return HomeworkValidation(
            status=self._clean_status(parsed.get('status'), bool(parsed.get('is_unclear') or parsed.get('needs_better_upload'))),
            summary=parsed.get('summary') or 'I can see your homework upload. Let us work through it one step at a time.',
            is_unclear=bool(parsed.get('is_unclear') or parsed.get('needs_better_upload')),
            detected_subject=self._clean_subject(parsed.get('detected_subject')),
            suggested_next_step=parsed.get('suggested_next_step'),
            problem_overview=parsed.get('problem_overview'),
            needs_better_upload=bool(parsed.get('needs_better_upload')),
            provider='claude',
            model=model,
        )

    def _anthropic_user_content(self, file_name: str, content: bytes, mime_type: str, file_type: str) -> list[dict]:
        encoded = base64.b64encode(content).decode('ascii')
        prompt = (
            f'Validate this homework upload before tutoring begins. File name: {file_name}. '
            'Return only the requested JSON. Do not solve the homework.'
        )
        if file_type == 'pdf':
            return [
                {
                    'type': 'document',
                    'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': encoded},
                },
                {'type': 'text', 'text': prompt},
            ]
        return [
            {
                'type': 'image',
                'source': {'type': 'base64', 'media_type': mime_type, 'data': encoded},
            },
            {'type': 'text', 'text': prompt},
        ]

    def _validation_system_prompt(self) -> str:
        return (
            'You are Ms. Alisia validating a student homework upload before tutoring. '
            'Use American English. First determine whether the file is readable enough to tutor from. '
            'Do not hallucinate problem text or answers. If uncertain, mark it unclear and ask for a better photo. '
            'Detect subject only when obvious: Math, ELA, or Writing. For handwriting, give only lightweight notes about legibility, spacing, neatness, or letter formation. '
            'If clear, describe what you can see before tutoring begins and suggest a hint-first next step. '
            'Never give final answers. Return strict JSON with keys: status, summary, is_unclear, detected_subject, problem_overview, suggested_next_step, needs_better_upload. '
            'status must be one of valid, unclear, invalid. detected_subject must be Math, ELA, Writing, or null.'
        )

    def _response_text(self, data: dict) -> str:
        parts = data.get('content', [])
        return '\n'.join(part.get('text', '') for part in parts if part.get('type') == 'text').strip()

    def _parse_validation_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    pass
        return {
            'status': 'valid',
            'summary': text[:1200] or 'I can see your homework upload. Let us work through it one step at a time.',
            'is_unclear': False,
            'detected_subject': None,
            'suggested_next_step': 'Start with the first problem and ask a guiding question before solving.',
            'needs_better_upload': False,
        }

    def _clean_subject(self, value: object) -> str | None:
        subject = str(value or '').strip()
        return subject if subject in {'Math', 'ELA', 'Writing'} else None

    def _clean_status(self, value: object, is_unclear: bool) -> str:
        status = str(value or '').strip().lower()
        if status in {'valid', 'invalid', 'unclear'}:
            return status
        return 'unclear' if is_unclear else 'valid'

    def _upload_response(self, row: dict, mime_type: str | None = None) -> HomeworkUploadResponse:
        metadata = row.get('metadata') or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        payload = {
            **row,
            'uploaded_by_type': row.get('uploader_type'),
            'mime_type': mime_type or metadata.get('mime_type') or '',
            'is_unclear': row.get('unclear_image', False),
            'suggested_next_step': metadata.get('suggested_next_step'),
            'provider': metadata.get('validation_provider'),
            'model': metadata.get('validation_model'),
        }
        return HomeworkUploadResponse.model_validate(payload)

    def _history_item(self, row: dict, child_name: str | None) -> dict:
        metadata = row.get('metadata') or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        return {
            'id': row.get('id'),
            'child_id': row.get('child_id'),
            'child_name': child_name,
            'file_name': row.get('file_name'),
            'file_type': row.get('file_type'),
            'mime_type': metadata.get('mime_type'),
            'file_size_bytes': row.get('file_size_bytes'),
            'upload_status': row.get('upload_status'),
            'ai_validation_status': row.get('ai_validation_status'),
            'ai_validation_summary': row.get('ai_validation_summary'),
            'is_unclear': row.get('unclear_image', False),
            'detected_subject': row.get('detected_subject'),
            'suggested_next_step': metadata.get('suggested_next_step'),
            'source': row.get('source'),
            'uploader_type': row.get('uploader_type'),
            'created_at': row.get('created_at'),
        }
