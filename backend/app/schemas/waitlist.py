from pydantic import BaseModel, Field


class WaitlistSignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class WaitlistSignupResponse(BaseModel):
    success: bool = True
    message: str = 'Thank you — we will be in touch soon!'
