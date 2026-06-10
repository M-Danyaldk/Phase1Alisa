alter table public.assessment_results
  add column if not exists assessment_version integer;

alter table public.assessment_results
  add column if not exists assessment_question_ids jsonb not null default '[]'::jsonb;

alter table public.assessment_results
  add column if not exists assessment_question_results jsonb not null default '[]'::jsonb;

alter table public.assessment_results
  add column if not exists correct_count integer;

alter table public.assessment_results
  add column if not exists total_questions integer;

create index if not exists assessment_results_child_subject_version_idx
  on public.assessment_results(child_id, subject, assessment_version, created_at desc);
