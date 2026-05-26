from pydantic import BaseModel, Field


class StudentAccessUpsertRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=12)
    is_active: bool = True


class StudentAccessResponse(BaseModel):
    id: str | None = None
    parent_id: str
    child_id: str
    username: str
    is_active: bool
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class StudentLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=12)


class StudentSessionResponse(BaseModel):
    access_token: str
    token_type: str = 'student'
    role: str = 'child'
    child_id: str
    parent_id: str
    student_name: str
    grade_level: str
    learning_levels: dict[str, str] = Field(default_factory=dict)
    access_allowed: bool = True
    billing_status: str | None = None
    blocked_reason: str | None = None
    voice_allowed: bool = False
    child_blocked_message: str | None = None
    expires_at: str
    message: str


class StudentMeResponse(BaseModel):
    role: str = 'child'
    child_id: str
    parent_id: str
    student_name: str
    grade_level: str
    subjects: list[str]
    learning_levels: dict[str, str] = Field(default_factory=dict)
    access_allowed: bool = True
    billing_status: str | None = None
    blocked_reason: str | None = None
    voice_allowed: bool = False
    child_blocked_message: str | None = None
    session_expires_at: str


class StudentLogoutResponse(BaseModel):
    message: str
