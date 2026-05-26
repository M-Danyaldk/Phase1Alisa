export type ChildAccessStatus = 'trial' | 'active' | 'inactive' | 'past_due';
export type BillingPlanKey = 'text_monthly' | 'text_annual' | 'voice_monthly' | 'voice_annual';
export type BillingPlanType = 'text' | 'voice';
export type BillingInterval = 'monthly' | 'annual';

export type ChildAccess = {
  id?: string | null;
  child_id: string;
  parent_id: string;
  child_name: string;
  grade_level: string;
  access_status: ChildAccessStatus;
  plan_name: string;
  plan_type?: BillingPlanType | null;
  billing_interval?: BillingInterval | null;
  voice_enabled?: boolean;
  feature_mode?: 'chat_only' | 'chat_and_voice';
  trial_ends_at?: string | null;
  trial_started_at?: string | null;
  current_period_ends_at?: string | null;
  current_period_started_at?: string | null;
  grace_period_ends_at?: string | null;
  access_paused_reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type BillingPlan = {
  plan_key: BillingPlanKey;
  plan_type: BillingPlanType;
  billing_interval: BillingInterval;
  display_name: string;
  price_label: string;
  annual_discount_label?: string | null;
  stripe_price_env: string;
  stripe_price_configured: boolean;
  voice_enabled: boolean;
};
