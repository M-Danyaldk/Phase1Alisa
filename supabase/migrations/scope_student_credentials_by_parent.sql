create extension if not exists pgcrypto;

alter table public.student_access
  add column if not exists normalized_username text;

update public.student_access
set normalized_username = lower(trim(username))
where normalized_username is null;

create or replace function public.set_student_access_normalized_username()
returns trigger
language plpgsql
as $$
begin
  new.normalized_username := lower(trim(new.username));
  return new;
end;
$$;

drop trigger if exists student_access_normalized_username on public.student_access;
create trigger student_access_normalized_username
before insert or update of username
on public.student_access
for each row
execute function public.set_student_access_normalized_username();

alter table public.student_access
  drop constraint if exists student_access_username_key;

drop index if exists public.student_access_username_key;

create unique index if not exists student_access_parent_normalized_username_unique
  on public.student_access(parent_id, normalized_username);

create table if not exists public.classroom_login_contexts (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  context_token_hash text not null unique,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists classroom_login_contexts_parent_child_idx
  on public.classroom_login_contexts(parent_id, child_id, created_at desc);

create index if not exists classroom_login_contexts_expires_idx
  on public.classroom_login_contexts(expires_at);

alter table public.classroom_login_contexts enable row level security;

drop policy if exists "Service role can manage classroom login contexts" on public.classroom_login_contexts;
create policy "Service role can manage classroom login contexts"
  on public.classroom_login_contexts
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

notify pgrst, 'reload schema';
