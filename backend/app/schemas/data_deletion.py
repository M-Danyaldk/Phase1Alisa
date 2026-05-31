from pydantic import BaseModel, EmailStr, Field, model_validator


class DataDeletionRequest(BaseModel):
    parent_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    child_name: str | None = Field(default=None, max_length=120)
    request_details: str | None = Field(default=None, max_length=1200)
    confirmation_accepted: bool = False

    @model_validator(mode='after')
    def validate_confirmation(self):
        if not self.confirmation_accepted:
            raise ValueError('Please confirm that this request will be reviewed before deletion.')
        return self


class DataDeletionResponse(BaseModel):
    success: bool = True
    message: str = 'Your deletion request has been received. We will review it and contact you if needed.'
