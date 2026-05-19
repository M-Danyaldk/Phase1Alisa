create extension if not exists pgcrypto;

create table if not exists public.student_access (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  username text not null,
  pin_hash text not null,
  is_active boolean not null default true,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id),
  unique(username),
  constraint student_access_username_format check (username ~ '^[a-z0-9][a-z0-9._-]{2,31}$')
);

create index if not exists student_access_parent_idx
  on public.student_access(parent_id, created_at asc);

create index if not exists student_access_username_idx
  on public.student_access(username);

create table if not exists public.student_sessions (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  student_access_id uuid not null references public.student_access(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists student_sessions_token_hash_idx
  on public.student_sessions(token_hash);

create index if not exists student_sessions_child_expires_idx
  on public.student_sessions(child_id, expires_at desc);

alter table public.student_access enable row level security;
alter table public.student_sessions enable row level security;

drop policy if exists "Service role can manage student access" on public.student_access;
create policy "Service role can manage student access"
  on public.student_access
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read their own student access" on public.student_access;
create policy "Parents can read their own student access"
  on public.student_access
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Service role can manage student sessions" on public.student_sessions;
create policy "Service role can manage student sessions"
  on public.student_sessions
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop trigger if exists student_access_set_updated_at on public.student_access;
create trigger student_access_set_updated_at
before update on public.student_access
for each row
execute function public.set_updated_at();

notify pgrst, 'reload schema';
