alter table public.child_access
  add column if not exists cancel_at_period_end boolean not null default false;

create index if not exists child_access_cancel_at_period_end_idx
  on public.child_access(cancel_at_period_end, current_period_ends_at)
  where cancel_at_period_end is true;

notify pgrst, 'reload schema';
