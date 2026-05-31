from typing import Literal

from pydantic import BaseModel, model_validator

from ..curriculum import LAUNCH_GRADE_ERROR, is_launch_grade_label

SubjectName = Literal['Math', 'ELA', 'Writing']


class WorkingLevelOverrideRequest(BaseModel):
    subject: SubjectName
    unlocked_grade_level: str

    @model_validator(mode='after')
    def validate_launch_grade(self):
        if not is_launch_grade_label(self.unlocked_grade_level):
            raise ValueError(LAUNCH_GRADE_ERROR)
        return self


class WorkingLevelOverrideItem(BaseModel):
    subject: SubjectName
    enrolled_grade: str
    assessed_level: str | None = None
    effective_working_level: str
    override_level: str | None = None
    override_active: bool = False
    status: str | None = None
    display_text: str
    updated_at: str | None = None


class WorkingLevelOverridesResponse(BaseModel):
    child_id: str
    child_name: str
    enrolled_grade: str
    subjects: list[WorkingLevelOverrideItem]
