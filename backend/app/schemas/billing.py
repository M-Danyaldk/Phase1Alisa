from typing import Literal

from pydantic import BaseModel, Field

AccessStatus = Literal['trial', 'active', 'inactive', 'past_due']
PlanKey = Literal['text_monthly', 'text_annual', 'voice_monthly', 'voice_annual']
PlanType = Literal['text', 'voice']
BillingInterval = Literal['monthly', 'annual']


class ChildAccessResponse(BaseModel):
    id: str | None = None
    child_id: str
    parent_id: str
    child_name: str
    grade_level: str
    access_status: AccessStatus
    plan_name: str
    plan_type: PlanType | None = None
    billing_interval: BillingInterval | None = None
    voice_enabled: bool = False
    voice_allowed: bool = False
    feature_mode: Literal['chat_only', 'chat_and_voice'] = 'chat_only'
    trial_ends_at: str | None = None
    trial_started_at: str | None = None
    current_period_ends_at: str | None = None
    current_period_started_at: str | None = None
    cancel_at_period_end: bool = False
    grace_period_ends_at: str | None = None
    access_paused_reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ChildAccessListResponse(BaseModel):
    children: list[ChildAccessResponse]


class ChildAccessUpdateRequest(BaseModel):
    access_status: AccessStatus
    plan_name: str = 'Phase 1 MVP'
    plan_key: PlanKey = 'text_monthly'


class BillingPlanResponse(BaseModel):
    plan_key: PlanKey
    plan_type: PlanType
    billing_interval: BillingInterval
    display_name: str
    price_label: str
    annual_discount_label: str | None = None
    stripe_price_env: str
    stripe_price_configured: bool
    voice_enabled: bool


class BillingPlansResponse(BaseModel):
    plans: list[BillingPlanResponse]


class BillingStatusResponse(BaseModel):
    parent_id: str
    email: str
    trial_available: bool
    paid_checkout_required: bool = False
    trial_blocked_reason: str | None = None
    children: list[ChildAccessResponse]
    plans: list[BillingPlanResponse]
    family_discount: dict | None = None
    coupon_redemptions: list[dict] = Field(default_factory=list)


class StartTrialRequest(BaseModel):
    child_id: str
    plan_key: PlanKey = 'text_monthly'


class StartTrialResponse(BaseModel):
    child: ChildAccessResponse
    trial_started_at: str
    trial_ends_at: str
    trial_available: bool = False
    message: str


class CheckoutSessionRequest(BaseModel):
    child_id: str
    plan_key: PlanKey
    coupon_code: str | None = None


class CheckoutChildPlanRequest(BaseModel):
    child_id: str
    plan_key: PlanKey


class BulkCheckoutSessionRequest(BaseModel):
    children: list[CheckoutChildPlanRequest] = Field(min_length=1, max_length=10)
    coupon_code: str | None = None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class CustomerPortalRequest(BaseModel):
    child_id: str | None = None


class CustomerPortalResponse(BaseModel):
    portal_url: str
    session_id: str


class StripeWebhookResponse(BaseModel):
    received: bool
    event_id: str | None = None
    event_type: str | None = None
    status: str


class StripeSubscriptionSyncResponse(BaseModel):
    synced_count: int
    skipped_count: int
    failed_count: int
    has_more: bool = False
    message: str


class GraceExpirationResponse(BaseModel):
    paused_count: int
    checked_at: str
