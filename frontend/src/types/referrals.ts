export type ReferralRecord = {
  id?: string;
  status: string;
  status_label?: string | null;
  referred_parent_email?: string | null;
  consecutive_paid_months?: number;
  reward_eligible_at?: string | null;
  reward_applied_at?: string | null;
  latest_reason?: string | null;
  created_at?: string | null;
};

export type ReferralRewardRecord = {
  id?: string;
  reward_type: string;
  reward_status: string;
  status_label?: string | null;
  verification_status?: string | null;
  eligible_at?: string | null;
  applied_at?: string | null;
  created_at?: string | null;
};

export type ReferralSummary = {
  referral_code: string;
  referral_url: string;
  referrals_sent: number;
  successful_referrals: number;
  rewards_earned: number;
  referrals: ReferralRecord[];
  rewards: ReferralRewardRecord[];
};
