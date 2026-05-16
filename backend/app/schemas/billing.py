from typing import Literal

from pydantic import BaseModel

AccessStatus = Literal['trial', 'active', 'inactive', 'past_due']


class ChildAccessResponse(BaseModel):
    id: str | None = None
    child_id: str
    parent_id: str
    child_name: str
    grade_level: str
    access_status: AccessStatus
    plan_name: str
    trial_ends_at: str | None = None
    current_period_ends_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ChildAccessListResponse(BaseModel):
    children: list[ChildAccessResponse]


class ChildAccessUpdateRequest(BaseModel):
    access_status: AccessStatus
    plan_name: str = 'Phase 1 MVP'
