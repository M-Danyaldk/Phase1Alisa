create extension if not exists pgcrypto;

create table if not exists public.waitlist (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  source text not null default 'prelaunch_landing',
  status text not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists waitlist_created_idx
  on public.waitlist(created_at desc);

alter table public.waitlist enable row level security;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop policy if exists "Service role can manage waitlist" on public.waitlist;
create policy "Service role can manage waitlist"
  on public.waitlist
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop trigger if exists waitlist_set_updated_at on public.waitlist;
create trigger waitlist_set_updated_at
before update on public.waitlist
for each row
execute function public.set_updated_at();

notify pgrst, 'reload schema';
