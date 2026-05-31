from pydantic import BaseModel


class ReferralSummaryResponse(BaseModel):
    referral_code: str
    referral_url: str
    referrals_sent: int
    successful_referrals: int
    rewards_earned: int
    referrals: list[dict]
    rewards: list[dict]


class ReferralProcessResponse(BaseModel):
    checked_count: int
    eligible_count: int
    applied_count: int
    pending_count: int
    skipped_count: int
    message: str
