from pydantic import BaseModel, Field


class WaitlistSignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    parent_name: str | None = Field(default=None, max_length=120)
    child_grade: str | None = Field(default=None, max_length=40)
    interest_note: str | None = Field(default=None, max_length=1000)


class WaitlistSignupResponse(BaseModel):
    success: bool = True
    message: str = "You're on the waitlist. Access is scheduled to open on July 3."
