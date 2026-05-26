from datetime import date
from pydantic import BaseModel, EmailStr, Field, model_validator
from ..core.security import calculate_age


class SignupStartRequest(BaseModel):
    full_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    confirm_password: str = Field(min_length=6)
    grade_level: str = Field(min_length=1)
    date_of_birth: date
    parent_guardian_email: EmailStr | None = None

    @model_validator(mode='after')
    def validate_signup(self):
        if self.password != self.confirm_password:
            raise ValueError('Confirm password must match password.')
        if calculate_age(self.date_of_birth) < 13 and not self.parent_guardian_email:
            raise ValueError('Parent/Guardian email is required if the student is under 13.')
        if self.parent_guardian_email and self.parent_guardian_email.lower() == self.email.lower():
            raise ValueError('Parent/Guardian email must be different from student email.')
        return self


class SignupStartResponse(BaseModel):
    email: EmailStr
    expires_in_minutes: int
    message: str


class VerifySignupRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class AuthUser(BaseModel):
    id: str
    email: str | None = None


class AuthSessionResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None
    user: AuthUser | None = None
    message: str


class ProfileResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: str = 'parent'
    status: str = 'active'
    admin_permissions: list[str] = []
    admin_2fa_enabled: bool = False
    grade_level: str | None = None
    date_of_birth: date | None = None
    parent_guardian_email: EmailStr | None = None
    avatar_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1)
    grade_level: str = Field(min_length=1)
    date_of_birth: date
    parent_guardian_email: EmailStr | None = None

    @model_validator(mode='after')
    def validate_profile_update(self):
        if calculate_age(self.date_of_birth) < 13 and not self.parent_guardian_email:
            raise ValueError('Parent/Guardian email is required if the student is under 13.')
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ResendCodeRequest(BaseModel):
    email: EmailStr


class ResendCodeResponse(BaseModel):
    email: EmailStr
    expires_in_minutes: int
    message: str
