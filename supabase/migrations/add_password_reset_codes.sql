create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create table if not exists public.password_reset_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  normalized_email text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0,
  max_attempts integer not null default 5,
  used_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists password_reset_codes_normalized_email_idx
  on public.password_reset_codes(normalized_email);

create index if not exists password_reset_codes_expires_at_idx
  on public.password_reset_codes(expires_at);

create index if not exists password_reset_codes_used_at_idx
  on public.password_reset_codes(used_at);

create index if not exists password_reset_codes_email_unused_created_idx
  on public.password_reset_codes(normalized_email, used_at, created_at desc);

alter table public.password_reset_codes enable row level security;

drop policy if exists "Service role can manage password reset codes" on public.password_reset_codes;
create policy "Service role can manage password reset codes"
  on public.password_reset_codes
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop trigger if exists password_reset_codes_set_updated_at on public.password_reset_codes;
create trigger password_reset_codes_set_updated_at
before update on public.password_reset_codes
for each row execute function public.set_updated_at();
