from typing import Literal

from pydantic import BaseModel, EmailStr, Field


AdminRole = Literal['admin', 'super_admin']
ProfileStatus = Literal['active', 'suspended', 'inactive']
AccessStatus = Literal['trial', 'active', 'inactive', 'past_due']


class AdminUserResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr | str
    role: str = 'parent'
    status: str = 'active'
    admin_permissions: list[str] = []
    admin_2fa_enabled: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class AdminOverviewResponse(BaseModel):
    totals: dict
    students: list[dict]
    assessments: list[dict]
    llm_events: list[dict]
    audit_logs: list[dict]


class AdminUsersResponse(BaseModel):
    users: list[AdminUserResponse]


class AdminUserStatusUpdateRequest(BaseModel):
    status: ProfileStatus
    reason: str = Field(default='', max_length=500)


class AdminSubscriptionsResponse(BaseModel):
    subscriptions: list[dict]


class AdminSubscriptionUpdateRequest(BaseModel):
    access_status: AccessStatus
    plan_name: str = 'Phase 1 MVP'
    reason: str = Field(min_length=1, max_length=500)


class AdminReportsResponse(BaseModel):
    assessments: list[dict]
    llm_events: list[dict]
    audit_logs: list[dict]


class OwnerFinancialSummaryResponse(BaseModel):
    summary: dict


class OwnerFinancialSubscriptionsResponse(BaseModel):
    subscriptions: list[dict]


class OwnerFinancialFailedPaymentsResponse(BaseModel):
    failed_payments: list[dict]


class OwnerFinancialDiscountsResponse(BaseModel):
    discounts: list[dict]
    coupon_redemptions: list[dict]


class OwnerFinancialReferralsResponse(BaseModel):
    referral_codes: list[dict]
    referrals: list[dict]
    referral_rewards: list[dict]


class OwnerFinancialEventsResponse(BaseModel):
    events: list[dict]


class AdminSettingsResponse(BaseModel):
    settings: list[dict]


class AdminSettingUpdateRequest(BaseModel):
    value: dict
    reason: str = Field(default='', max_length=500)


class AdminAuditLogsResponse(BaseModel):
    audit_logs: list[dict]


class AdminInviteRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1)
    role: AdminRole = 'admin'
    permissions: list[str] = []
    temporary_password: str = Field(min_length=8)


class AdminInviteResponse(BaseModel):
    admin: AdminUserResponse
    message: str


class AdminPermissionsUpdateRequest(BaseModel):
    role: AdminRole
    permissions: list[str] = []
    reason: str = Field(default='', max_length=500)
