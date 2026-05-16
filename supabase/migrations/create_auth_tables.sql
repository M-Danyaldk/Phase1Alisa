create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  email text not null unique,
  role text not null default 'parent' check (role in ('parent', 'student', 'admin')),
  grade_level text,
  date_of_birth date,
  parent_guardian_email text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles
  add column if not exists avatar_url text;

alter table public.profiles
  add column if not exists role text not null default 'parent';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_role_check'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_role_check check (role in ('parent', 'student', 'admin'));
  end if;
end $$;

update public.profiles
set role = 'parent'
where role is null;

alter table public.profiles
  alter column grade_level drop not null;

alter table public.profiles
  alter column date_of_birth drop not null;

create table if not exists public.signup_verification_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  hashed_code text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0,
  used boolean not null default false,
  pending_signup_data jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists signup_verification_codes_email_idx
  on public.signup_verification_codes(email);

create index if not exists signup_verification_codes_email_used_created_idx
  on public.signup_verification_codes(email, used, created_at desc);

create table if not exists public.child_profiles (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  grade_level text not null check (grade_level in ('Grade 3', 'Grade 4', 'Grade 5', 'Grade 6')),
  date_of_birth date,
  subjects jsonb not null default '["Math", "ELA", "Writing"]'::jsonb,
  learning_goals text,
  difficulty_level text,
  parent_notes text,
  status text not null default 'active' check (status in ('active', 'inactive', 'pending_consent')),
  parental_consent_accepted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists child_profiles_parent_status_idx
  on public.child_profiles(parent_id, status, created_at asc);

create table if not exists public.child_access (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  access_status text not null default 'trial' check (access_status in ('trial', 'active', 'inactive', 'past_due')),
  plan_name text not null default 'Phase 1 MVP',
  trial_ends_at timestamptz,
  current_period_ends_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(child_id)
);

create index if not exists child_access_parent_status_idx
  on public.child_access(parent_id, access_status, created_at asc);

create table if not exists public.learning_sessions (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  topic text,
  time_spent_seconds integer not null default 0,
  hints_used integer not null default 0,
  questions_attempted integer not null default 0,
  correct_answers integer not null default 0,
  completed_lessons integer not null default 0,
  improvement_status text,
  brain_break_triggered boolean not null default false,
  brain_break_started_at timestamptz,
  brain_break_ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists learning_sessions_child_created_idx
  on public.learning_sessions(child_id, created_at desc);

create table if not exists public.report_snapshots (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  report_period text not null check (report_period in ('week', 'month', 'all')),
  summary text not null,
  subject_progress jsonb not null default '[]'::jsonb,
  strengths jsonb not null default '[]'::jsonb,
  weak_areas jsonb not null default '[]'::jsonb,
  assessment_summary jsonb not null default '[]'::jsonb,
  session_summary jsonb not null default '[]'::jsonb,
  recommended_next_steps jsonb not null default '[]'::jsonb,
  brain_break_summary text,
  generated_at timestamptz not null default now()
);

create index if not exists report_snapshots_child_generated_idx
  on public.report_snapshots(child_id, generated_at desc);

create table if not exists public.weekly_report_summaries (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid not null references public.child_profiles(id) on delete cascade,
  week_start date not null,
  week_end date not null,
  email_subject text not null,
  email_preview jsonb not null,
  email_sent boolean not null default false,
  email_sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique(child_id, week_start)
);

create index if not exists weekly_report_summaries_parent_created_idx
  on public.weekly_report_summaries(parent_id, created_at desc);

create table if not exists public.chat_threads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid references public.child_profiles(id) on delete cascade,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  topic text,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.chat_threads(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  child_id uuid references public.child_profiles(id) on delete cascade,
  role text not null check (role in ('student', 'msalisia')),
  content text not null,
  subject text,
  topic text,
  provider text,
  model text,
  tutoring_state jsonb,
  created_at timestamptz not null default now()
);

alter table public.chat_threads
  add column if not exists child_id uuid references public.child_profiles(id) on delete cascade;

alter table public.chat_messages
  add column if not exists child_id uuid references public.child_profiles(id) on delete cascade;

create index if not exists chat_threads_user_updated_idx
  on public.chat_threads(user_id, updated_at desc);

create index if not exists chat_threads_child_updated_idx
  on public.chat_threads(child_id, updated_at desc);

create index if not exists chat_messages_thread_created_idx
  on public.chat_messages(thread_id, created_at asc);

create index if not exists chat_messages_user_created_idx
  on public.chat_messages(user_id, created_at desc);

create index if not exists chat_messages_child_created_idx
  on public.chat_messages(child_id, created_at desc);

alter table public.profiles enable row level security;
alter table public.signup_verification_codes enable row level security;
alter table public.child_profiles enable row level security;
alter table public.child_access enable row level security;
alter table public.learning_sessions enable row level security;
alter table public.report_snapshots enable row level security;
alter table public.weekly_report_summaries enable row level security;
alter table public.chat_threads enable row level security;
alter table public.chat_messages enable row level security;

drop policy if exists "Users can read their own profile" on public.profiles;
create policy "Users can read their own profile"
  on public.profiles
  for select
  using (auth.uid() = id);

drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile"
  on public.profiles
  for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

drop policy if exists "Parents can read their own child profiles" on public.child_profiles;
create policy "Parents can read their own child profiles"
  on public.child_profiles
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Parents can create their own child profiles" on public.child_profiles;
create policy "Parents can create their own child profiles"
  on public.child_profiles
  for insert
  with check (auth.uid() = parent_id);

drop policy if exists "Parents can update their own child profiles" on public.child_profiles;
create policy "Parents can update their own child profiles"
  on public.child_profiles
  for update
  using (auth.uid() = parent_id)
  with check (auth.uid() = parent_id);

drop policy if exists "Parents can read their own child access" on public.child_access;
create policy "Parents can read their own child access"
  on public.child_access
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Parents can create their own child access" on public.child_access;
create policy "Parents can create their own child access"
  on public.child_access
  for insert
  with check (
    auth.uid() = parent_id
    and exists (
      select 1
      from public.child_profiles
      where child_profiles.id = child_access.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Parents can update their own child access" on public.child_access;
create policy "Parents can update their own child access"
  on public.child_access
  for update
  using (auth.uid() = parent_id)
  with check (
    auth.uid() = parent_id
    and exists (
      select 1
      from public.child_profiles
      where child_profiles.id = child_access.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Parents can read their own learning sessions" on public.learning_sessions;
create policy "Parents can read their own learning sessions"
  on public.learning_sessions
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Parents can create their own learning sessions" on public.learning_sessions;
create policy "Parents can create their own learning sessions"
  on public.learning_sessions
  for insert
  with check (
    auth.uid() = parent_id
    and exists (
      select 1 from public.child_profiles
      where child_profiles.id = learning_sessions.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Parents can read their own report snapshots" on public.report_snapshots;
create policy "Parents can read their own report snapshots"
  on public.report_snapshots
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Parents can create their own report snapshots" on public.report_snapshots;
create policy "Parents can create their own report snapshots"
  on public.report_snapshots
  for insert
  with check (
    auth.uid() = parent_id
    and exists (
      select 1 from public.child_profiles
      where child_profiles.id = report_snapshots.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Parents can read their own weekly report summaries" on public.weekly_report_summaries;
create policy "Parents can read their own weekly report summaries"
  on public.weekly_report_summaries
  for select
  using (auth.uid() = parent_id);

drop policy if exists "Parents can create their own weekly report summaries" on public.weekly_report_summaries;
create policy "Parents can create their own weekly report summaries"
  on public.weekly_report_summaries
  for insert
  with check (
    auth.uid() = parent_id
    and exists (
      select 1 from public.child_profiles
      where child_profiles.id = weekly_report_summaries.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Users can read their own chat threads" on public.chat_threads;
create policy "Users can read their own chat threads"
  on public.chat_threads
  for select
  using (
    auth.uid() = user_id
    and (
      child_id is null
      or exists (
        select 1
        from public.child_profiles
        where child_profiles.id = chat_threads.child_id
          and child_profiles.parent_id = auth.uid()
      )
    )
  );

drop policy if exists "Users can create their own chat threads" on public.chat_threads;
create policy "Users can create their own chat threads"
  on public.chat_threads
  for insert
  with check (
    auth.uid() = user_id
    and (
      child_id is null
      or exists (
        select 1
        from public.child_profiles
        where child_profiles.id = chat_threads.child_id
          and child_profiles.parent_id = auth.uid()
      )
    )
  );

drop policy if exists "Users can update their own chat threads" on public.chat_threads;
create policy "Users can update their own chat threads"
  on public.chat_threads
  for update
  using (auth.uid() = user_id)
  with check (
    auth.uid() = user_id
    and (
      child_id is null
      or exists (
        select 1
        from public.child_profiles
        where child_profiles.id = chat_threads.child_id
          and child_profiles.parent_id = auth.uid()
      )
    )
  );

drop policy if exists "Users can delete their own chat threads" on public.chat_threads;
create policy "Users can delete their own chat threads"
  on public.chat_threads
  for delete
  using (
    auth.uid() = user_id
    and (
      child_id is null
      or exists (
        select 1
        from public.child_profiles
        where child_profiles.id = chat_threads.child_id
          and child_profiles.parent_id = auth.uid()
      )
    )
  );

drop policy if exists "Users can read their own chat messages" on public.chat_messages;
create policy "Users can read their own chat messages"
  on public.chat_messages
  for select
  using (
    auth.uid() = user_id
    and (
      child_id is null
      or exists (
        select 1
        from public.child_profiles
        where child_profiles.id = chat_messages.child_id
          and child_profiles.parent_id = auth.uid()
      )
    )
  );

drop policy if exists "Users can create their own chat messages" on public.chat_messages;
create policy "Users can create their own chat messages"
  on public.chat_messages
  for insert
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.chat_threads
      where chat_threads.id = chat_messages.thread_id
        and chat_threads.user_id = auth.uid()
        and (
          chat_messages.child_id is null
          or chat_threads.child_id = chat_messages.child_id
        )
        and (
          chat_messages.child_id is null
          or exists (
            select 1
            from public.child_profiles
            where child_profiles.id = chat_messages.child_id
              and child_profiles.parent_id = auth.uid()
          )
        )
    )
  );

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();

drop trigger if exists child_profiles_set_updated_at on public.child_profiles;
create trigger child_profiles_set_updated_at
before update on public.child_profiles
for each row
execute function public.set_updated_at();

drop trigger if exists child_access_set_updated_at on public.child_access;
create trigger child_access_set_updated_at
before update on public.child_access
for each row
execute function public.set_updated_at();

drop trigger if exists learning_sessions_set_updated_at on public.learning_sessions;
create trigger learning_sessions_set_updated_at
before update on public.learning_sessions
for each row
execute function public.set_updated_at();

notify pgrst, 'reload schema';
