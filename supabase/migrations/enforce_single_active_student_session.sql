with ranked_active_sessions as (
  select
    id,
    row_number() over (
      partition by student_access_id
      order by created_at desc, expires_at desc, id desc
    ) as active_rank
  from public.student_sessions
  where revoked_at is null
)
update public.student_sessions as sessions
set revoked_at = now()
from ranked_active_sessions ranked
where sessions.id = ranked.id
  and ranked.active_rank > 1;

create unique index if not exists student_sessions_one_active_per_access_idx
  on public.student_sessions(student_access_id)
  where revoked_at is null;

notify pgrst, 'reload schema';
