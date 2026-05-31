from pydantic import BaseModel, EmailStr, Field, model_validator


class SignupStartRequest(BaseModel):
    full_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    confirm_password: str = Field(min_length=6)
    referral_code: str | None = Field(default=None, max_length=64)
    coppa_parent_consent_accepted: bool = False

    @model_validator(mode='after')
    def validate_signup(self):
        if self.password != self.confirm_password:
            raise ValueError('Confirm password must match password.')
        if not self.coppa_parent_consent_accepted:
            raise ValueError('Please confirm parent/guardian consent before continuing.')
        return self


class SignupStartResponse(BaseModel):
    email: EmailStr
    expires_in_minutes: int
    message: str
    trial_available: bool = True
    paid_checkout_required: bool = False
    trial_blocked_reason: str | None = None


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
    trial_available: bool = True
    paid_checkout_required: bool = False
    trial_blocked_reason: str | None = None


class ProfileResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: str = 'parent'
    status: str = 'active'
    admin_permissions: list[str] = []
    admin_2fa_enabled: bool = False
    avatar_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ResendCodeRequest(BaseModel):
    email: EmailStr


class ResendCodeResponse(BaseModel):
    email: EmailStr
    expires_in_minutes: int
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class VerifyResetCodeResponse(BaseModel):
    reset_allowed: bool
    message: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')
    new_password: str = Field(min_length=6)
    confirm_password: str = Field(min_length=6)

    @model_validator(mode='after')
    def validate_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError('Confirm password must match password.')
        return self


class ResetPasswordResponse(BaseModel):
    message: str
