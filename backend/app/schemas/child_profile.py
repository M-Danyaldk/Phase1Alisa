from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..core.security import calculate_age
from ..curriculum import LAUNCH_GRADE_ERROR, is_launch_grade_label

ChildStatus = Literal['active', 'inactive', 'pending_consent']
SubjectName = Literal['Math', 'ELA', 'Writing']


class ChildProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    grade_level: str
    date_of_birth: date | None = None
    subjects: list[SubjectName] = Field(default_factory=lambda: ['Math', 'ELA', 'Writing'])
    learning_goals: str = ''
    difficulty_level: str = ''
    parent_notes: str = ''
    parental_consent_accepted: bool = False

    @model_validator(mode='after')
    def validate_child_profile(self):
        if not is_launch_grade_label(self.grade_level):
            raise ValueError(LAUNCH_GRADE_ERROR)
        if not self.subjects:
            raise ValueError('Select at least one subject.')
        if self.date_of_birth and calculate_age(self.date_of_birth) < 13 and not self.parental_consent_accepted:
            raise ValueError('Parental consent is required for children under 13.')
        return self


class ChildProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    grade_level: str
    date_of_birth: date | None = None
    subjects: list[SubjectName] = Field(default_factory=lambda: ['Math', 'ELA', 'Writing'])
    learning_goals: str = ''
    difficulty_level: str = ''
    parent_notes: str = ''
    parental_consent_accepted: bool = False
    status: ChildStatus = 'active'

    @model_validator(mode='after')
    def validate_child_profile_update(self):
        if not is_launch_grade_label(self.grade_level):
            raise ValueError(LAUNCH_GRADE_ERROR)
        if not self.subjects:
            raise ValueError('Select at least one subject.')
        if self.date_of_birth and calculate_age(self.date_of_birth) < 13 and not self.parental_consent_accepted:
            raise ValueError('Parental consent is required for children under 13.')
        return self


class ChildProfileResponse(BaseModel):
    id: str
    parent_id: str
    name: str
    grade_level: str
    date_of_birth: date | None = None
    subjects: list[SubjectName]
    learning_goals: str | None = None
    difficulty_level: str | None = None
    parent_notes: str | None = None
    status: ChildStatus
    parental_consent_accepted: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    learning_levels: dict[str, str] = Field(default_factory=dict)


class ChildProfilesResponse(BaseModel):
    children: list[ChildProfileResponse]
