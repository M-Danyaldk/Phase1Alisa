create extension if not exists pgcrypto;

create table if not exists public.students (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  grade integer not null check (grade between 3 and 6),
  math_level text,
  ela_level text,
  writing_level text,
  confidence text,
  focus_notes text,
  parent_notes text,
  created_at timestamptz not null default now()
);

create index if not exists students_created_idx
  on public.students(created_at desc);

create table if not exists public.assessment_results (
  id uuid primary key default gen_random_uuid(),
  child_id uuid references public.child_profiles(id) on delete set null,
  student_name text,
  subject text not null check (subject in ('Math', 'ELA', 'Writing')),
  enrolled_grade integer check (enrolled_grade between 3 and 6),
  estimated_level text not null,
  score_label text,
  strengths jsonb not null default '[]'::jsonb,
  learning_gaps jsonb not null default '[]'::jsonb,
  recommended_progression jsonb not null default '[]'::jsonb,
  parent_summary text,
  provider text,
  model text,
  created_at timestamptz not null default now()
);

alter table public.assessment_results
  add column if not exists child_id uuid references public.child_profiles(id) on delete set null;

alter table public.assessment_results
  add column if not exists enrolled_grade integer check (enrolled_grade between 3 and 6);

alter table public.assessment_results
  add column if not exists score_label text;

alter table public.assessment_results
  add column if not exists strengths jsonb not null default '[]'::jsonb;

alter table public.assessment_results
  add column if not exists provider text;

alter table public.assessment_results
  add column if not exists model text;

create index if not exists assessment_results_child_created_idx
  on public.assessment_results(child_id, created_at desc);

create index if not exists assessment_results_created_idx
  on public.assessment_results(created_at desc);

create table if not exists public.llm_events (
  id uuid primary key default gen_random_uuid(),
  provider text,
  model text,
  purpose text,
  fallback_used boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists llm_events_created_idx
  on public.llm_events(created_at desc);

insert into storage.buckets (id, name, public)
values ('homework-uploads', 'homework-uploads', false)
on conflict (id) do update set public = excluded.public;

alter table public.students enable row level security;
alter table public.assessment_results enable row level security;
alter table public.llm_events enable row level security;

drop policy if exists "Service role can manage students" on public.students;
create policy "Service role can manage students"
  on public.students
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Service role can manage assessment results" on public.assessment_results;
create policy "Service role can manage assessment results"
  on public.assessment_results
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Parents can read child assessment results" on public.assessment_results;
create policy "Parents can read child assessment results"
  on public.assessment_results
  for select
  using (
    child_id is not null
    and exists (
      select 1
      from public.child_profiles
      where child_profiles.id = assessment_results.child_id
        and child_profiles.parent_id = auth.uid()
    )
  );

drop policy if exists "Service role can manage llm events" on public.llm_events;
create policy "Service role can manage llm events"
  on public.llm_events
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "Service role can manage homework uploads" on storage.objects;
create policy "Service role can manage homework uploads"
  on storage.objects
  for all
  using (bucket_id = 'homework-uploads' and auth.role() = 'service_role')
  with check (bucket_id = 'homework-uploads' and auth.role() = 'service_role');

notify pgrst, 'reload schema';
