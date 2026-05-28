from pydantic import BaseModel


class HomeworkValidation(BaseModel):
    status: str = 'skipped'
    summary: str
    is_unclear: bool = False
    detected_subject: str | None = None
    suggested_next_step: str | None = None
    problem_overview: str | None = None
    needs_better_upload: bool = False
    provider: str = 'local'
    model: str = 'rules'


class HomeworkUploadResponse(BaseModel):
    id: str | None = None
    child_id: str
    parent_id: str | None = None
    uploaded_by_type: str
    source: str
    file_name: str
    mime_type: str
    file_type: str
    file_size_bytes: int
    upload_status: str
    ai_validation_status: str
    ai_validation_summary: str | None = None
    is_unclear: bool
    detected_subject: str | None = None
    suggested_next_step: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class HomeworkHistoryItem(BaseModel):
    id: str
    child_id: str
    child_name: str | None = None
    file_name: str
    file_type: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    upload_status: str
    ai_validation_status: str
    ai_validation_summary: str | None = None
    is_unclear: bool
    detected_subject: str | None = None
    suggested_next_step: str | None = None
    source: str
    uploader_type: str
    created_at: str | None = None


class HomeworkHistoryResponse(BaseModel):
    child_id: str
    uploads: list[HomeworkHistoryItem]
