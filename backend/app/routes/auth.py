from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from ..schemas.auth import (
    AuthSessionResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ResendCodeRequest,
    ResendCodeResponse,
    SignupStartRequest,
    SignupStartResponse,
    VerifyResetCodeRequest,
    VerifyResetCodeResponse,
    VerifySignupRequest,
)
from ..services.verification_service import VerificationService

router = APIRouter(prefix='/auth', tags=['auth'])


def _bearer_token(authorization: str) -> str:
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Authorization token is required.')
    token = authorization.split(' ', 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Authorization token is required.')
    return token


@router.post('/start-signup', response_model=SignupStartResponse)
async def start_signup(payload: SignupStartRequest) -> SignupStartResponse:
    service = VerificationService()
    result = await service.start_signup(payload)
    return SignupStartResponse(**result)


@router.post('/verify-signup', response_model=AuthSessionResponse)
async def verify_signup(payload: VerifySignupRequest) -> AuthSessionResponse:
    service = VerificationService()
    result = await service.verify_signup(str(payload.email), payload.code)
    return AuthSessionResponse(**result)


@router.post('/login', response_model=AuthSessionResponse)
async def login(payload: LoginRequest) -> AuthSessionResponse:
    service = VerificationService()
    result = await service.login(str(payload.email), payload.password)
    return AuthSessionResponse(**result)


@router.post('/forgot-password', response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
    service = VerificationService()
    result = await service.forgot_password(str(payload.email))
    return ForgotPasswordResponse(**result)


@router.post('/verify-reset-code', response_model=VerifyResetCodeResponse)
async def verify_reset_code(payload: VerifyResetCodeRequest) -> VerifyResetCodeResponse:
    service = VerificationService()
    result = await service.verify_reset_code(str(payload.email), payload.code)
    return VerifyResetCodeResponse(**result)


@router.post('/reset-password', response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    service = VerificationService()
    result = await service.reset_password(str(payload.email), payload.code, payload.new_password)
    return ResetPasswordResponse(**result)


@router.get('/me', response_model=ProfileResponse)
async def current_profile(authorization: str = Header(default='')) -> ProfileResponse:
    service = VerificationService()
    result = await service.current_profile(_bearer_token(authorization))
    return ProfileResponse(**result)


@router.patch('/me', response_model=ProfileResponse)
async def update_profile(payload: ProfileUpdateRequest, authorization: str = Header(default='')) -> ProfileResponse:
    service = VerificationService()
    result = await service.update_profile(_bearer_token(authorization), payload)
    return ProfileResponse(**result)


@router.post('/me/avatar', response_model=ProfileResponse)
async def upload_avatar(file: UploadFile = File(...), authorization: str = Header(default='')) -> ProfileResponse:
    service = VerificationService()
    result = await service.upload_avatar(_bearer_token(authorization), file)
    return ProfileResponse(**result)


@router.post('/resend-code', response_model=ResendCodeResponse)
async def resend_code(payload: ResendCodeRequest) -> ResendCodeResponse:
    service = VerificationService()
    result = await service.resend_code(str(payload.email))
    return ResendCodeResponse(**result)
