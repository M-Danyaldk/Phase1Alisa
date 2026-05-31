create extension if not exists pgcrypto;

create table if not exists public.learning_session_summaries (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  session_id uuid,
  thread_id uuid references public.chat_threads(id) on delete set null,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  topic text,
  grade_level text,
  working_level text,
  worked_on text,
  struggled_with text,
  mastered text,
  next_step text,
  child_facing_summary text,
  parent_facing_summary text,
  source text not null default 'session',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create index if not exists learning_session_summaries_child_subject_created_idx
  on public.learning_session_summaries(child_id, subject, created_at desc);

create index if not exists learning_session_summaries_parent_child_idx
  on public.learning_session_summaries(parent_id, child_id);

create index if not exists learning_session_summaries_session_idx
  on public.learning_session_summaries(session_id);

create index if not exists learning_session_summaries_thread_idx
  on public.learning_session_summaries(thread_id);

alter table public.learning_session_summaries enable row level security;

drop policy if exists "Service role can manage learning session summaries" on public.learning_session_summaries;
create policy "Service role can manage learning session summaries"
  on public.learning_session_summaries
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read own learning session summaries" on public.learning_session_summaries;
create policy "Parents can read own learning session summaries"
  on public.learning_session_summaries
  for select
  using (
    auth.uid() = parent_id
    or exists (
      select 1
      from public.child_profiles child
      where child.id = learning_session_summaries.child_id
        and child.parent_id = auth.uid()
    )
  );

drop trigger if exists learning_session_summaries_set_updated_at on public.learning_session_summaries;
create trigger learning_session_summaries_set_updated_at
before update on public.learning_session_summaries
for each row execute function public.set_updated_at();
