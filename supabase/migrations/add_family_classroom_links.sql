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

create table if not exists public.family_classroom_links (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references public.profiles(id) on delete cascade,
  family_code text not null unique,
  is_active boolean not null default true,
  last_used_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists family_classroom_links_one_active_parent_uidx
  on public.family_classroom_links(parent_id)
  where is_active;

create index if not exists family_classroom_links_code_active_idx
  on public.family_classroom_links(family_code, is_active);

alter table public.family_classroom_links enable row level security;

drop policy if exists "Service role can manage family classroom links" on public.family_classroom_links;
create policy "Service role can manage family classroom links"
  on public.family_classroom_links
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own family classroom links" on public.family_classroom_links;
create policy "Parents can read own family classroom links"
  on public.family_classroom_links
  for select
  using (auth.uid() = parent_id);

drop trigger if exists family_classroom_links_set_updated_at on public.family_classroom_links;
create trigger family_classroom_links_set_updated_at
before update on public.family_classroom_links
for each row
execute function public.set_updated_at();

update public.student_sessions
set revoked_at = now()
where revoked_at is null;

notify pgrst, 'reload schema';
