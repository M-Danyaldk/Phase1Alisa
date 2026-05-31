create extension if not exists vector with schema extensions;

alter table public.learning_session_summaries
  add column if not exists embedding vector(1536),
  add column if not exists embedding_model text,
  add column if not exists embedding_text text,
  add column if not exists embedding_updated_at timestamptz;

create index if not exists learning_session_summaries_child_subject_created_idx
  on public.learning_session_summaries(child_id, subject, created_at desc);

create or replace function public.match_learning_session_summaries(
  query_embedding vector(1536),
  match_child_id uuid,
  match_subject text,
  match_count int default 3
)
returns table (
  id uuid,
  parent_id uuid,
  child_id uuid,
  session_id uuid,
  thread_id uuid,
  subject text,
  topic text,
  grade_level text,
  working_level text,
  worked_on text,
  struggled_with text,
  mastered text,
  next_step text,
  child_facing_summary text,
  parent_facing_summary text,
  similarity float,
  created_at timestamptz
)
language sql
stable
as $$
  select
    lss.id,
    lss.parent_id,
    lss.child_id,
    lss.session_id,
    lss.thread_id,
    lss.subject,
    lss.topic,
    lss.grade_level,
    lss.working_level,
    lss.worked_on,
    lss.struggled_with,
    lss.mastered,
    lss.next_step,
    lss.child_facing_summary,
    lss.parent_facing_summary,
    1 - (lss.embedding <=> query_embedding) as similarity,
    lss.created_at
  from public.learning_session_summaries lss
  where lss.child_id = match_child_id
    and lower(lss.subject) = lower(match_subject)
    and lss.embedding is not null
  order by lss.embedding <=> query_embedding
  limit match_count;
$$;
