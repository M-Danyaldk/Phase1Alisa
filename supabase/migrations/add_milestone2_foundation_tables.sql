create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create or replace function public.current_user_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
    where id = auth.uid()
      and role in ('admin', 'super_admin')
      and coalesce(status, 'active') = 'active'
  );
$$;

create or replace function public.current_user_has_admin_permission(permission_name text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
    where id = auth.uid()
      and coalesce(status, 'active') = 'active'
      and (
        role = 'super_admin'
        or (
          role = 'admin'
          and coalesce(admin_permissions, '[]'::jsonb) ? permission_name
        )
      )
  );
$$;

create or replace function public.current_user_owns_child(target_child_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.child_profiles
    where id = target_child_id
      and parent_id = auth.uid()
  );
$$;

alter table public.profiles
  add column if not exists stripe_customer_id text;

create unique index if not exists profiles_stripe_customer_id_uidx
  on public.profiles(stripe_customer_id)
  where stripe_customer_id is not null;

alter table public.child_access
  add column if not exists plan_type text check (plan_type in ('text', 'voice'));

alter table public.child_access
  add column if not exists billing_interval text check (billing_interval in ('monthly', 'annual'));

alter table public.child_access
  add column if not exists stripe_customer_id text;

alter table public.child_access
  add column if not exists stripe_subscription_id text;

alter table public.child_access
  add column if not exists stripe_price_id text;

alter table public.child_access
  add column if not exists trial_started_at timestamptz;

alter table public.child_access
  add column if not exists grace_period_started_at timestamptz;

alter table public.child_access
  add column if not exists grace_period_ends_at timestamptz;

alter table public.child_access
  add column if not exists access_paused_reason text;

alter table public.child_access
  add column if not exists original_billing_due_at timestamptz;

alter table public.child_access
  add column if not exists current_period_started_at timestamptz;

alter table public.child_access
  add column if not exists latest_invoice_id text;

alter table public.child_access
  add column if not exists latest_payment_intent_id text;

alter table public.child_access
  add column if not exists non_refundable_policy_accepted_at timestamptz;

alter table public.child_access
  add column if not exists non_refundable_policy_version text;

alter table public.child_access
  add column if not exists family_discount_eligible boolean not null default false;

alter table public.child_access
  add column if not exists family_discount_applied boolean not null default false;

alter table public.child_access
  add column if not exists family_discount_remove_at_period_end boolean not null default false;

alter table public.child_access
  add column if not exists stripe_coupon_id text;

create index if not exists child_access_stripe_customer_idx
  on public.child_access(stripe_customer_id)
  where stripe_customer_id is not null;

create unique index if not exists child_access_stripe_subscription_uidx
  on public.child_access(stripe_subscription_id)
  where stripe_subscription_id is not null;

create index if not exists child_access_stripe_price_idx
  on public.child_access(stripe_price_id)
  where stripe_price_id is not null;

create table if not exists public.billing_customers (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  email text not null,
  normalized_email text generated always as (lower(trim(email))) stored,
  stripe_customer_id text not null unique,
  default_payment_method_id text,
  billing_name text,
  billing_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists billing_customers_parent_idx
  on public.billing_customers(parent_id, created_at desc);

create index if not exists billing_customers_normalized_email_idx
  on public.billing_customers(normalized_email);

create table if not exists public.billing_subscriptions (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  billing_customer_id uuid references public.billing_customers(id) on delete set null,
  stripe_customer_id text not null,
  stripe_subscription_id text not null unique,
  stripe_price_id text,
  stripe_latest_invoice_id text,
  stripe_latest_payment_intent_id text,
  plan_type text not null check (plan_type in ('text', 'voice')),
  billing_interval text not null check (billing_interval in ('monthly', 'annual')),
  subscription_status text not null default 'incomplete'
    check (subscription_status in ('incomplete', 'trialing', 'active', 'past_due', 'paused', 'canceled', 'unpaid', 'incomplete_expired')),
  trial_started_at timestamptz,
  trial_ends_at timestamptz,
  grace_period_started_at timestamptz,
  grace_period_ends_at timestamptz,
  access_paused_reason text,
  original_billing_due_at timestamptz,
  current_period_started_at timestamptz,
  current_period_ends_at timestamptz,
  cancel_at_period_end boolean not null default false,
  canceled_at timestamptz,
  non_refundable_policy_accepted_at timestamptz,
  non_refundable_policy_version text,
  family_discount_eligible boolean not null default false,
  family_discount_applied boolean not null default false,
  family_discount_remove_at_period_end boolean not null default false,
  stripe_coupon_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists billing_subscriptions_parent_status_idx
  on public.billing_subscriptions(parent_id, subscription_status, created_at desc);

create index if not exists billing_subscriptions_child_idx
  on public.billing_subscriptions(child_id, created_at desc);

create index if not exists billing_subscriptions_stripe_customer_idx
  on public.billing_subscriptions(stripe_customer_id);

create index if not exists billing_subscriptions_period_end_idx
  on public.billing_subscriptions(current_period_ends_at)
  where current_period_ends_at is not null;

create table if not exists public.stripe_events (
  id uuid primary key default gen_random_uuid(),
  stripe_event_id text not null unique,
  event_type text not null,
  api_version text,
  livemode boolean not null default false,
  processed_at timestamptz,
  processing_status text not null default 'pending' check (processing_status in ('pending', 'processed', 'failed', 'ignored')),
  error_message text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists stripe_events_type_created_idx
  on public.stripe_events(event_type, created_at desc);

create index if not exists stripe_events_status_created_idx
  on public.stripe_events(processing_status, created_at desc);

create table if not exists public.parent_trial_history (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  email text not null,
  normalized_email text generated always as (lower(trim(email))) stored,
  child_id uuid references public.child_profiles(id) on delete set null,
  trial_started_at timestamptz not null,
  trial_ends_at timestamptz not null,
  source text not null default 'signup',
  stripe_customer_id text,
  stripe_subscription_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists parent_trial_history_normalized_email_uidx
  on public.parent_trial_history(normalized_email);

create index if not exists parent_trial_history_parent_idx
  on public.parent_trial_history(parent_id, created_at desc);

create table if not exists public.billing_discounts (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  billing_subscription_id uuid references public.billing_subscriptions(id) on delete set null,
  discount_type text not null check (discount_type in ('family', 'coupon', 'referral', 'manual')),
  discount_percent numeric(5,2),
  stripe_coupon_id text,
  stripe_promotion_code_id text,
  eligibility_status text not null default 'pending' check (eligibility_status in ('pending', 'eligible', 'applied', 'remove_at_period_end', 'removed', 'ineligible')),
  applies_at timestamptz,
  removes_at_period_end boolean not null default false,
  removed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists billing_discounts_parent_status_idx
  on public.billing_discounts(parent_id, eligibility_status, created_at desc);

create index if not exists billing_discounts_subscription_idx
  on public.billing_discounts(billing_subscription_id, created_at desc);

create table if not exists public.referral_codes (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  referral_code text not null unique,
  referral_url text,
  is_active boolean not null default true,
  use_count integer not null default 0,
  max_uses integer,
  fraud_review_status text not null default 'clear' check (fraud_review_status in ('clear', 'review', 'blocked')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists referral_codes_parent_idx
  on public.referral_codes(parent_id, created_at desc);

create index if not exists referral_codes_code_idx
  on public.referral_codes(referral_code);

create table if not exists public.referrals (
  id uuid primary key default gen_random_uuid(),
  referral_code_id uuid references public.referral_codes(id) on delete set null,
  referrer_parent_id uuid references auth.users(id) on delete set null,
  referred_parent_id uuid references auth.users(id) on delete set null,
  referred_parent_email text not null,
  referred_normalized_email text generated always as (lower(trim(referred_parent_email))) stored,
  status text not null default 'pending'
    check (status in ('pending', 'signed_up', 'trialing', 'qualified', 'reward_pending', 'rewarded', 'canceled', 'paused', 'blocked', 'expired')),
  self_referral_blocked boolean not null default false,
  consecutive_paid_months integer not null default 0,
  reward_eligible_at timestamptz,
  reward_applied_at timestamptz,
  reset_at timestamptz,
  fraud_flags jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists referrals_referrer_status_idx
  on public.referrals(referrer_parent_id, status, created_at desc);

create index if not exists referrals_referred_parent_idx
  on public.referrals(referred_parent_id, created_at desc);

create index if not exists referrals_referred_email_idx
  on public.referrals(referred_normalized_email);

create table if not exists public.referral_rewards (
  id uuid primary key default gen_random_uuid(),
  referral_id uuid not null references public.referrals(id) on delete cascade,
  referrer_parent_id uuid references auth.users(id) on delete set null,
  reward_type text not null default 'billing_credit',
  reward_status text not null default 'pending' check (reward_status in ('pending', 'eligible', 'applied', 'voided')),
  reward_amount_cents integer,
  stripe_coupon_id text,
  stripe_credit_note_id text,
  eligibility_months_required integer not null default 3,
  eligible_at timestamptz,
  applied_at timestamptz,
  voided_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists referral_rewards_referrer_status_idx
  on public.referral_rewards(referrer_parent_id, reward_status, created_at desc);

create table if not exists public.coupon_redemptions (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  billing_subscription_id uuid references public.billing_subscriptions(id) on delete set null,
  coupon_code text not null,
  normalized_coupon_code text generated always as (lower(trim(coupon_code))) stored,
  stripe_coupon_id text,
  stripe_promotion_code_id text,
  validation_status text not null default 'pending' check (validation_status in ('pending', 'valid', 'invalid', 'applied', 'expired', 'rejected')),
  applied_at timestamptz,
  payment_reference text,
  rejection_reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists coupon_redemptions_parent_idx
  on public.coupon_redemptions(parent_id, created_at desc);

create index if not exists coupon_redemptions_code_idx
  on public.coupon_redemptions(normalized_coupon_code);

create table if not exists public.email_events (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  trigger_type text not null check (trigger_type in (
    'signup_welcome',
    'trial_day_5',
    'trial_day_7',
    'trial_expired_day_8',
    'payment_success',
    'payment_failed',
    'annual_renewal_reminder',
    'weekly_progress'
  )),
  recipient_email text not null,
  normalized_recipient_email text generated always as (lower(trim(recipient_email))) stored,
  template_key text,
  status text not null default 'pending' check (status in ('pending', 'sent', 'failed', 'skipped')),
  provider text not null default 'resend',
  scheduled_send_at timestamptz,
  sent_at timestamptz,
  retry_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists email_events_parent_status_idx
  on public.email_events(parent_id, status, scheduled_send_at);

create index if not exists email_events_trigger_status_idx
  on public.email_events(trigger_type, status, scheduled_send_at);

create table if not exists public.email_delivery_logs (
  id uuid primary key default gen_random_uuid(),
  email_event_id uuid references public.email_events(id) on delete set null,
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  trigger_type text,
  recipient_email text not null,
  provider text not null default 'resend',
  provider_message_id text,
  status text not null default 'pending' check (status in ('pending', 'sent', 'failed', 'skipped')),
  error_message text,
  scheduled_send_at timestamptz,
  sent_at timestamptz,
  retry_count integer not null default 0,
  payload_preview jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists email_delivery_logs_event_idx
  on public.email_delivery_logs(email_event_id, created_at desc);

create index if not exists email_delivery_logs_parent_status_idx
  on public.email_delivery_logs(parent_id, status, created_at desc);

create table if not exists public.homework_uploads (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  uploaded_by_user_id uuid references auth.users(id) on delete set null,
  uploader_type text not null check (uploader_type in ('parent', 'child', 'admin', 'system')),
  source text not null default 'student_upload' check (source in ('student_upload', 'parent_upload', 'admin_upload', 'system')),
  file_name text not null,
  file_type text not null check (file_type in ('jpg', 'jpeg', 'png', 'heic', 'pdf')),
  storage_bucket text not null default 'homework-uploads',
  storage_path text not null,
  file_size_bytes integer,
  upload_status text not null default 'uploaded' check (upload_status in ('pending', 'uploaded', 'failed', 'deleted')),
  ai_validation_status text not null default 'pending' check (ai_validation_status in ('pending', 'valid', 'invalid', 'unclear', 'failed', 'skipped')),
  ai_validation_summary text,
  unclear_image boolean not null default false,
  detected_subject text check (detected_subject in ('Math', 'ELA', 'Writing')),
  learning_session_id uuid references public.learning_sessions(id) on delete set null,
  parent_report_visible boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists homework_uploads_child_created_idx
  on public.homework_uploads(child_id, created_at desc);

create index if not exists homework_uploads_parent_created_idx
  on public.homework_uploads(parent_id, created_at desc);

create index if not exists homework_uploads_session_idx
  on public.homework_uploads(learning_session_id)
  where learning_session_id is not null;

alter table public.learning_sessions
  add column if not exists session_started_at timestamptz;

alter table public.learning_sessions
  add column if not exists session_ended_at timestamptz;

alter table public.learning_sessions
  add column if not exists active_time_seconds integer not null default 0;

alter table public.learning_sessions
  add column if not exists inactive_time_seconds integer not null default 0;

alter table public.learning_sessions
  add column if not exists paused_time_seconds integer not null default 0;

alter table public.learning_sessions
  add column if not exists session_status text not null default 'active'
    check (session_status in ('active', 'paused', 'completed', 'abandoned'));

alter table public.learning_sessions
  add column if not exists learning_mode text not null default 'text'
    check (learning_mode in ('text', 'voice'));

alter table public.learning_sessions
  add column if not exists last_activity_at timestamptz;

alter table public.learning_sessions
  add column if not exists inactivity_nudge_sent_at timestamptz;

alter table public.learning_sessions
  add column if not exists auto_paused_at timestamptz;

alter table public.learning_sessions
  add column if not exists resumed_at timestamptz;

create index if not exists learning_sessions_parent_status_idx
  on public.learning_sessions(parent_id, session_status, created_at desc);

create table if not exists public.session_activity_events (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  learning_session_id uuid references public.learning_sessions(id) on delete cascade,
  event_type text not null check (event_type in ('activity', 'inactivity_nudge', 'auto_pause', 'resume', 'message_sent', 'message_received', 'voice_started', 'voice_failed')),
  learning_mode text not null default 'text' check (learning_mode in ('text', 'voice')),
  active_seconds_delta integer not null default 0,
  inactive_seconds_delta integer not null default 0,
  event_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists session_activity_events_session_idx
  on public.session_activity_events(learning_session_id, created_at desc);

create index if not exists session_activity_events_child_idx
  on public.session_activity_events(child_id, created_at desc);

create table if not exists public.session_pause_events (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  learning_session_id uuid references public.learning_sessions(id) on delete cascade,
  pause_reason text not null check (pause_reason in ('inactivity', 'brain_break', 'student_action', 'system', 'voice_failure')),
  paused_at timestamptz not null default now(),
  resumed_at timestamptz,
  active_time_before_pause_seconds integer not null default 0,
  inactive_time_before_pause_seconds integer not null default 0,
  resumed_from_pause boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists session_pause_events_session_idx
  on public.session_pause_events(learning_session_id, paused_at desc);

create index if not exists session_pause_events_child_idx
  on public.session_pause_events(child_id, paused_at desc);

create table if not exists public.daily_learning_counters (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  counter_date date not null,
  active_tutoring_seconds integer not null default 0,
  inactive_seconds integer not null default 0,
  brain_break_required boolean not null default false,
  currently_locked_out boolean not null default false,
  warning_30_min_sent_at timestamptz,
  warning_10_min_sent_at timestamptz,
  warning_5_min_sent_at timestamptz,
  break_started_at timestamptz,
  break_ends_at timestamptz,
  break_completed_at timestamptz,
  daily_reset_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id, counter_date)
);

create index if not exists daily_learning_counters_parent_date_idx
  on public.daily_learning_counters(parent_id, counter_date desc);

create index if not exists daily_learning_counters_child_date_idx
  on public.daily_learning_counters(child_id, counter_date desc);

create table if not exists public.brain_break_events (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  learning_session_id uuid references public.learning_sessions(id) on delete set null,
  daily_counter_id uuid references public.daily_learning_counters(id) on delete set null,
  event_type text not null check (event_type in ('warning_30', 'warning_10', 'warning_5', 'started', 'ended', 'auto_resume', 'lockout_checked')),
  active_seconds_at_event integer not null default 0,
  break_started_at timestamptz,
  break_ended_at timestamptz,
  is_lockout_active boolean not null default false,
  completed boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists brain_break_events_child_created_idx
  on public.brain_break_events(child_id, created_at desc);

create index if not exists brain_break_events_session_idx
  on public.brain_break_events(learning_session_id, created_at desc);

create table if not exists public.weekly_learning_rhythm (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  week_start_date date not null,
  week_end_date date not null,
  session_count integer not null default 0,
  active_tutoring_seconds integer not null default 0,
  achievement_label text not null default 'fresh_start'
    check (achievement_label in ('fresh_start', 'getting_started', 'strong_week', 'perfect_week', 'superstar')),
  parent_visible_summary text,
  child_visible_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id, week_start_date)
);

create index if not exists weekly_learning_rhythm_parent_week_idx
  on public.weekly_learning_rhythm(parent_id, week_start_date desc);

create index if not exists weekly_learning_rhythm_child_week_idx
  on public.weekly_learning_rhythm(child_id, week_start_date desc);

create table if not exists public.problem_reports (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  learning_session_id uuid references public.learning_sessions(id) on delete set null,
  chat_message_id uuid references public.chat_messages(id) on delete set null,
  reporter_user_id uuid references auth.users(id) on delete set null,
  reporter_type text not null check (reporter_type in ('parent', 'child', 'admin', 'system')),
  issue_category text not null default 'other',
  description text,
  status text not null default 'open' check (status in ('open', 'in_review', 'resolved', 'dismissed')),
  alert_sent_to_support boolean not null default false,
  resolved_by uuid references auth.users(id) on delete set null,
  resolved_at timestamptz,
  admin_notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists problem_reports_parent_status_idx
  on public.problem_reports(parent_id, status, created_at desc);

create index if not exists problem_reports_child_created_idx
  on public.problem_reports(child_id, created_at desc);

create index if not exists problem_reports_session_idx
  on public.problem_reports(learning_session_id, created_at desc);

create table if not exists public.flagged_interactions (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  learning_session_id uuid references public.learning_sessions(id) on delete set null,
  chat_message_id uuid references public.chat_messages(id) on delete set null,
  flag_category text not null check (flag_category in ('violence', 'adult_content', 'politics', 'religion', 'unsafe_request', 'hallucination_risk', 'other')),
  severity text not null default 'medium' check (severity in ('low', 'medium', 'high', 'critical')),
  review_status text not null default 'pending' check (review_status in ('pending', 'in_review', 'resolved', 'dismissed')),
  flagged_by text not null default 'system' check (flagged_by in ('system', 'parent', 'child', 'admin')),
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  resolved_at timestamptz,
  review_notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists flagged_interactions_status_severity_idx
  on public.flagged_interactions(review_status, severity, created_at desc);

create index if not exists flagged_interactions_child_idx
  on public.flagged_interactions(child_id, created_at desc);

create index if not exists flagged_interactions_message_idx
  on public.flagged_interactions(chat_message_id)
  where chat_message_id is not null;

create table if not exists public.owner_financial_access (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  granted_by uuid references auth.users(id) on delete set null,
  access_level text not null default 'owner' check (access_level in ('owner', 'read_only')),
  is_active boolean not null default true,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_user_id)
);

create index if not exists owner_financial_access_owner_idx
  on public.owner_financial_access(owner_user_id, is_active);

create or replace function public.current_user_has_financial_access()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.owner_financial_access
    where owner_user_id = auth.uid()
      and is_active = true
  )
  or public.current_user_has_admin_permission('view_financials');
$$;

create table if not exists public.financial_events (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  billing_subscription_id uuid references public.billing_subscriptions(id) on delete set null,
  stripe_customer_id text,
  stripe_subscription_id text,
  stripe_invoice_id text,
  stripe_payment_intent_id text,
  event_type text not null,
  billing_status text,
  amount_cents integer not null default 0,
  currency text not null default 'usd',
  coupon_code text,
  stripe_coupon_id text,
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists financial_events_parent_occurred_idx
  on public.financial_events(parent_id, occurred_at desc);

create index if not exists financial_events_subscription_idx
  on public.financial_events(billing_subscription_id, occurred_at desc);

create index if not exists financial_events_stripe_subscription_idx
  on public.financial_events(stripe_subscription_id)
  where stripe_subscription_id is not null;

create table if not exists public.subject_working_level_overrides (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  enrolled_grade text,
  approved_working_level text not null,
  previous_working_level text,
  status text not null default 'requested' check (status in ('requested', 'approved', 'rejected', 'revoked')),
  requested_by uuid references auth.users(id) on delete set null,
  approved_by_parent_id uuid references auth.users(id) on delete set null,
  approved_by_admin_id uuid references auth.users(id) on delete set null,
  requested_at timestamptz not null default now(),
  approved_at timestamptz,
  revoked_at timestamptz,
  audit_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id, subject)
);

create index if not exists subject_working_level_overrides_parent_idx
  on public.subject_working_level_overrides(parent_id, status, created_at desc);

create index if not exists subject_working_level_overrides_child_subject_idx
  on public.subject_working_level_overrides(child_id, subject);

create table if not exists public.data_deletion_requests (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references auth.users(id) on delete set null,
  child_id uuid references public.child_profiles(id) on delete set null,
  requested_by uuid references auth.users(id) on delete set null,
  request_scope text not null check (request_scope in ('account', 'child', 'partial')),
  status text not null default 'requested' check (status in ('requested', 'in_review', 'verified', 'completed', 'denied', 'canceled')),
  requested_at timestamptz not null default now(),
  due_at timestamptz not null default (now() + interval '30 days'),
  completed_at timestamptz,
  completed_by uuid references auth.users(id) on delete set null,
  admin_notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists data_deletion_requests_parent_status_idx
  on public.data_deletion_requests(parent_id, status, created_at desc);

create index if not exists data_deletion_requests_due_idx
  on public.data_deletion_requests(due_at)
  where status in ('requested', 'in_review', 'verified');

alter table public.billing_customers enable row level security;
alter table public.billing_subscriptions enable row level security;
alter table public.stripe_events enable row level security;
alter table public.parent_trial_history enable row level security;
alter table public.billing_discounts enable row level security;
alter table public.referral_codes enable row level security;
alter table public.referrals enable row level security;
alter table public.referral_rewards enable row level security;
alter table public.coupon_redemptions enable row level security;
alter table public.email_events enable row level security;
alter table public.email_delivery_logs enable row level security;
alter table public.homework_uploads enable row level security;
alter table public.session_activity_events enable row level security;
alter table public.session_pause_events enable row level security;
alter table public.daily_learning_counters enable row level security;
alter table public.brain_break_events enable row level security;
alter table public.weekly_learning_rhythm enable row level security;
alter table public.problem_reports enable row level security;
alter table public.flagged_interactions enable row level security;
alter table public.owner_financial_access enable row level security;
alter table public.financial_events enable row level security;
alter table public.subject_working_level_overrides enable row level security;
alter table public.data_deletion_requests enable row level security;

drop policy if exists "Service role can manage billing customers" on public.billing_customers;
create policy "Service role can manage billing customers"
  on public.billing_customers for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own billing customers" on public.billing_customers;
create policy "Parents can read own billing customers"
  on public.billing_customers for select
  using (auth.uid() = parent_id);

drop policy if exists "Billing admins can read billing customers" on public.billing_customers;
create policy "Billing admins can read billing customers"
  on public.billing_customers for select
  using (public.current_user_has_admin_permission('manage_subscriptions'));

drop policy if exists "Service role can manage billing subscriptions" on public.billing_subscriptions;
create policy "Service role can manage billing subscriptions"
  on public.billing_subscriptions for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own billing subscriptions" on public.billing_subscriptions;
create policy "Parents can read own billing subscriptions"
  on public.billing_subscriptions for select
  using (auth.uid() = parent_id);

drop policy if exists "Billing admins can read billing subscriptions" on public.billing_subscriptions;
create policy "Billing admins can read billing subscriptions"
  on public.billing_subscriptions for select
  using (public.current_user_has_admin_permission('manage_subscriptions'));

drop policy if exists "Service role can manage stripe events" on public.stripe_events;
create policy "Service role can manage stripe events"
  on public.stripe_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Service role can manage parent trial history" on public.parent_trial_history;
create policy "Service role can manage parent trial history"
  on public.parent_trial_history for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own trial history" on public.parent_trial_history;
create policy "Parents can read own trial history"
  on public.parent_trial_history for select
  using (auth.uid() = parent_id);

drop policy if exists "Billing admins can read trial history" on public.parent_trial_history;
create policy "Billing admins can read trial history"
  on public.parent_trial_history for select
  using (public.current_user_has_admin_permission('manage_subscriptions'));

drop policy if exists "Service role can manage billing discounts" on public.billing_discounts;
create policy "Service role can manage billing discounts"
  on public.billing_discounts for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own billing discounts" on public.billing_discounts;
create policy "Parents can read own billing discounts"
  on public.billing_discounts for select
  using (auth.uid() = parent_id);

drop policy if exists "Billing admins can read billing discounts" on public.billing_discounts;
create policy "Billing admins can read billing discounts"
  on public.billing_discounts for select
  using (public.current_user_has_admin_permission('manage_subscriptions'));

drop policy if exists "Service role can manage referral codes" on public.referral_codes;
create policy "Service role can manage referral codes"
  on public.referral_codes for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can manage own referral codes" on public.referral_codes;
create policy "Parents can manage own referral codes"
  on public.referral_codes for all
  using (auth.uid() = parent_id)
  with check (auth.uid() = parent_id);

drop policy if exists "Service role can manage referrals" on public.referrals;
create policy "Service role can manage referrals"
  on public.referrals for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read related referrals" on public.referrals;
create policy "Parents can read related referrals"
  on public.referrals for select
  using (auth.uid() = referrer_parent_id or auth.uid() = referred_parent_id);

drop policy if exists "Service role can manage referral rewards" on public.referral_rewards;
create policy "Service role can manage referral rewards"
  on public.referral_rewards for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own referral rewards" on public.referral_rewards;
create policy "Parents can read own referral rewards"
  on public.referral_rewards for select
  using (auth.uid() = referrer_parent_id);

drop policy if exists "Service role can manage coupon redemptions" on public.coupon_redemptions;
create policy "Service role can manage coupon redemptions"
  on public.coupon_redemptions for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own coupon redemptions" on public.coupon_redemptions;
create policy "Parents can read own coupon redemptions"
  on public.coupon_redemptions for select
  using (auth.uid() = parent_id);

drop policy if exists "Service role can manage email events" on public.email_events;
create policy "Service role can manage email events"
  on public.email_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own email events" on public.email_events;
create policy "Parents can read own email events"
  on public.email_events for select
  using (auth.uid() = parent_id);

drop policy if exists "Service role can manage email delivery logs" on public.email_delivery_logs;
create policy "Service role can manage email delivery logs"
  on public.email_delivery_logs for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own email delivery logs" on public.email_delivery_logs;
create policy "Parents can read own email delivery logs"
  on public.email_delivery_logs for select
  using (auth.uid() = parent_id);

drop policy if exists "Service role can manage homework uploads" on public.homework_uploads;
create policy "Service role can manage homework uploads"
  on public.homework_uploads for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own homework uploads" on public.homework_uploads;
create policy "Parents can read own homework uploads"
  on public.homework_uploads for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Parents can create own homework uploads" on public.homework_uploads;
create policy "Parents can create own homework uploads"
  on public.homework_uploads for insert
  with check (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage session activity events" on public.session_activity_events;
create policy "Service role can manage session activity events"
  on public.session_activity_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own session activity events" on public.session_activity_events;
create policy "Parents can read own session activity events"
  on public.session_activity_events for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage session pause events" on public.session_pause_events;
create policy "Service role can manage session pause events"
  on public.session_pause_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own session pause events" on public.session_pause_events;
create policy "Parents can read own session pause events"
  on public.session_pause_events for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage daily learning counters" on public.daily_learning_counters;
create policy "Service role can manage daily learning counters"
  on public.daily_learning_counters for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own daily learning counters" on public.daily_learning_counters;
create policy "Parents can read own daily learning counters"
  on public.daily_learning_counters for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage brain break events" on public.brain_break_events;
create policy "Service role can manage brain break events"
  on public.brain_break_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own brain break events" on public.brain_break_events;
create policy "Parents can read own brain break events"
  on public.brain_break_events for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage weekly learning rhythm" on public.weekly_learning_rhythm;
create policy "Service role can manage weekly learning rhythm"
  on public.weekly_learning_rhythm for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own weekly learning rhythm" on public.weekly_learning_rhythm;
create policy "Parents can read own weekly learning rhythm"
  on public.weekly_learning_rhythm for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage problem reports" on public.problem_reports;
create policy "Service role can manage problem reports"
  on public.problem_reports for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can create own problem reports" on public.problem_reports;
create policy "Parents can create own problem reports"
  on public.problem_reports for insert
  with check (child_id is null or public.current_user_owns_child(child_id));

drop policy if exists "Parents can read own problem reports" on public.problem_reports;
create policy "Parents can read own problem reports"
  on public.problem_reports for select
  using (auth.uid() = parent_id or (child_id is not null and public.current_user_owns_child(child_id)));

drop policy if exists "Admins can read problem reports" on public.problem_reports;
create policy "Admins can read problem reports"
  on public.problem_reports for select
  using (public.current_user_has_admin_permission('view_analytics'));

drop policy if exists "Service role can manage flagged interactions" on public.flagged_interactions;
create policy "Service role can manage flagged interactions"
  on public.flagged_interactions for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Admins can read flagged interactions" on public.flagged_interactions;
create policy "Admins can read flagged interactions"
  on public.flagged_interactions for select
  using (public.current_user_has_admin_permission('view_analytics'));

drop policy if exists "Service role can manage owner financial access" on public.owner_financial_access;
create policy "Service role can manage owner financial access"
  on public.owner_financial_access for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Owners can read own financial access" on public.owner_financial_access;
create policy "Owners can read own financial access"
  on public.owner_financial_access for select
  using (
    auth.uid() = owner_user_id
    and exists (
      select 1
      from public.profiles
      where profiles.id = auth.uid()
        and profiles.role = 'super_admin'
        and coalesce(profiles.status, 'active') = 'active'
    )
  );

drop policy if exists "Service role can manage financial events" on public.financial_events;
create policy "Service role can manage financial events"
  on public.financial_events for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Owner financial users can read financial events" on public.financial_events;
create policy "Owner financial users can read financial events"
  on public.financial_events for select
  using (public.current_user_has_financial_access());

drop policy if exists "Service role can manage working level overrides" on public.subject_working_level_overrides;
create policy "Service role can manage working level overrides"
  on public.subject_working_level_overrides for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own working level overrides" on public.subject_working_level_overrides;
create policy "Parents can read own working level overrides"
  on public.subject_working_level_overrides for select
  using (public.current_user_owns_child(child_id));

drop policy if exists "Parents can create own working level override requests" on public.subject_working_level_overrides;
create policy "Parents can create own working level override requests"
  on public.subject_working_level_overrides for insert
  with check (public.current_user_owns_child(child_id));

drop policy if exists "Service role can manage data deletion requests" on public.data_deletion_requests;
create policy "Service role can manage data deletion requests"
  on public.data_deletion_requests for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can create own data deletion requests" on public.data_deletion_requests;
create policy "Parents can create own data deletion requests"
  on public.data_deletion_requests for insert
  with check (auth.uid() = parent_id and (child_id is null or public.current_user_owns_child(child_id)));

drop policy if exists "Parents can read own data deletion requests" on public.data_deletion_requests;
create policy "Parents can read own data deletion requests"
  on public.data_deletion_requests for select
  using (auth.uid() = parent_id);

drop policy if exists "Admins can read data deletion requests" on public.data_deletion_requests;
create policy "Admins can read data deletion requests"
  on public.data_deletion_requests for select
  using (public.current_user_has_admin_permission('manage_users'));

drop trigger if exists billing_customers_set_updated_at on public.billing_customers;
create trigger billing_customers_set_updated_at before update on public.billing_customers for each row execute function public.set_updated_at();

drop trigger if exists billing_subscriptions_set_updated_at on public.billing_subscriptions;
create trigger billing_subscriptions_set_updated_at before update on public.billing_subscriptions for each row execute function public.set_updated_at();

drop trigger if exists stripe_events_set_updated_at on public.stripe_events;
create trigger stripe_events_set_updated_at before update on public.stripe_events for each row execute function public.set_updated_at();

drop trigger if exists parent_trial_history_set_updated_at on public.parent_trial_history;
create trigger parent_trial_history_set_updated_at before update on public.parent_trial_history for each row execute function public.set_updated_at();

drop trigger if exists billing_discounts_set_updated_at on public.billing_discounts;
create trigger billing_discounts_set_updated_at before update on public.billing_discounts for each row execute function public.set_updated_at();

drop trigger if exists referral_codes_set_updated_at on public.referral_codes;
create trigger referral_codes_set_updated_at before update on public.referral_codes for each row execute function public.set_updated_at();

drop trigger if exists referrals_set_updated_at on public.referrals;
create trigger referrals_set_updated_at before update on public.referrals for each row execute function public.set_updated_at();

drop trigger if exists referral_rewards_set_updated_at on public.referral_rewards;
create trigger referral_rewards_set_updated_at before update on public.referral_rewards for each row execute function public.set_updated_at();

drop trigger if exists coupon_redemptions_set_updated_at on public.coupon_redemptions;
create trigger coupon_redemptions_set_updated_at before update on public.coupon_redemptions for each row execute function public.set_updated_at();

drop trigger if exists email_events_set_updated_at on public.email_events;
create trigger email_events_set_updated_at before update on public.email_events for each row execute function public.set_updated_at();

drop trigger if exists email_delivery_logs_set_updated_at on public.email_delivery_logs;
create trigger email_delivery_logs_set_updated_at before update on public.email_delivery_logs for each row execute function public.set_updated_at();

drop trigger if exists homework_uploads_set_updated_at on public.homework_uploads;
create trigger homework_uploads_set_updated_at before update on public.homework_uploads for each row execute function public.set_updated_at();

drop trigger if exists session_pause_events_set_updated_at on public.session_pause_events;
create trigger session_pause_events_set_updated_at before update on public.session_pause_events for each row execute function public.set_updated_at();

drop trigger if exists daily_learning_counters_set_updated_at on public.daily_learning_counters;
create trigger daily_learning_counters_set_updated_at before update on public.daily_learning_counters for each row execute function public.set_updated_at();

drop trigger if exists weekly_learning_rhythm_set_updated_at on public.weekly_learning_rhythm;
create trigger weekly_learning_rhythm_set_updated_at before update on public.weekly_learning_rhythm for each row execute function public.set_updated_at();

drop trigger if exists problem_reports_set_updated_at on public.problem_reports;
create trigger problem_reports_set_updated_at before update on public.problem_reports for each row execute function public.set_updated_at();

drop trigger if exists flagged_interactions_set_updated_at on public.flagged_interactions;
create trigger flagged_interactions_set_updated_at before update on public.flagged_interactions for each row execute function public.set_updated_at();

drop trigger if exists owner_financial_access_set_updated_at on public.owner_financial_access;
create trigger owner_financial_access_set_updated_at before update on public.owner_financial_access for each row execute function public.set_updated_at();

drop trigger if exists subject_working_level_overrides_set_updated_at on public.subject_working_level_overrides;
create trigger subject_working_level_overrides_set_updated_at before update on public.subject_working_level_overrides for each row execute function public.set_updated_at();

drop trigger if exists data_deletion_requests_set_updated_at on public.data_deletion_requests;
create trigger data_deletion_requests_set_updated_at before update on public.data_deletion_requests for each row execute function public.set_updated_at();

notify pgrst, 'reload schema';
