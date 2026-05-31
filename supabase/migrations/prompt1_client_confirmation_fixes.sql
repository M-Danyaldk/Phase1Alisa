alter table public.profiles
  add column if not exists coppa_parent_consent_accepted boolean,
  add column if not exists coppa_parent_consent_at timestamptz,
  add column if not exists coppa_consent_version text,
  add column if not exists coppa_consent_source text;

do $$
declare
  constraint_name text;
begin
  if to_regclass('public.email_events') is null then
    return;
  end if;

  select conname into constraint_name
  from pg_constraint
  where conrelid = 'public.email_events'::regclass
    and contype = 'c'
    and pg_get_constraintdef(oid) like '%trigger_type%';

  if constraint_name is not null then
    execute format('alter table public.email_events drop constraint %I', constraint_name);
  end if;
end $$;

alter table public.email_events
  add constraint email_events_trigger_type_check
  check (trigger_type in (
    'signup_welcome',
    'trial_day_5',
    'trial_day_7',
    'trial_expired_day_8',
    'payment_success',
    'payment_failed',
    'annual_renewal_reminder',
    'weekly_progress',
    'referral_success'
  ));
