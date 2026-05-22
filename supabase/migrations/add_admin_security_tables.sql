alter table public.profiles
  drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check check (role in ('parent', 'student', 'admin', 'super_admin'));

alter table public.profiles
  add column if not exists status text not null default 'active'
    check (status in ('active', 'suspended', 'inactive'));

alter table public.profiles
  add column if not exists admin_permissions jsonb not null default '[]'::jsonb;

alter table public.profiles
  add column if not exists admin_2fa_enabled boolean not null default false;

create table if not exists public.admin_audit_logs (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid references auth.users(id) on delete set null,
  action text not null,
  target_type text not null,
  target_id text,
  metadata jsonb not null default '{}'::jsonb,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now()
);

create index if not exists admin_audit_logs_created_idx
  on public.admin_audit_logs(created_at desc);

create index if not exists admin_audit_logs_admin_created_idx
  on public.admin_audit_logs(admin_user_id, created_at desc);

create table if not exists public.app_settings (
  key text primary key,
  value jsonb not null default '{}'::jsonb,
  updated_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.login_security_events (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  event_type text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists login_security_events_email_created_idx
  on public.login_security_events(email, created_at desc);

alter table public.admin_audit_logs enable row level security;
alter table public.app_settings enable row level security;
alter table public.login_security_events enable row level security;

drop policy if exists "Service role can manage admin audit logs" on public.admin_audit_logs;
create policy "Service role can manage admin audit logs"
  on public.admin_audit_logs
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Service role can manage app settings" on public.app_settings;
create policy "Service role can manage app settings"
  on public.app_settings
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Service role can manage login security events" on public.login_security_events;
create policy "Service role can manage login security events"
  on public.login_security_events
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

insert into public.app_settings (key, value)
values
  ('admin_security', '{"admin_2fa_required": true, "session_minutes": 60, "failed_login_lockout_minutes": 15}'::jsonb),
  ('platform', '{"maintenance_mode": false}'::jsonb)
on conflict (key) do nothing;

notify pgrst, 'reload schema';
