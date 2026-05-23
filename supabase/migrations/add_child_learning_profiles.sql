create table if not exists public.child_learning_profiles (
  id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  assessed_level text not null,
  learning_gaps jsonb not null default '[]'::jsonb,
  strengths jsonb not null default '[]'::jsonb,
  recommended_next_steps jsonb not null default '[]'::jsonb,
  recommended_next_topics jsonb not null default '[]'::jsonb,
  last_assessed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id, subject)
);

alter table public.assessment_results
  add column if not exists recommended_next_topics jsonb not null default '[]'::jsonb;

create index if not exists child_learning_profiles_child_subject_idx
  on public.child_learning_profiles(child_id, subject);

create index if not exists child_learning_profiles_assessed_idx
  on public.child_learning_profiles(child_id, last_assessed_at desc);

alter table public.child_learning_profiles enable row level security;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop policy if exists "Service role can manage child learning profiles" on public.child_learning_profiles;
create policy "Service role can manage child learning profiles"
  on public.child_learning_profiles
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read child learning profiles" on public.child_learning_profiles;
create policy "Parents can read child learning profiles"
  on public.child_learning_profiles
  for select
  using (
    exists (
      select 1
      from public.child_profiles
      where child_profiles.id = child_learning_profiles.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop trigger if exists child_learning_profiles_set_updated_at on public.child_learning_profiles;
create trigger child_learning_profiles_set_updated_at
before update on public.child_learning_profiles
for each row
execute function public.set_updated_at();

notify pgrst, 'reload schema';
