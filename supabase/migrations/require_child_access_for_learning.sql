alter table public.child_access
  alter column access_status set default 'inactive';

insert into public.child_access (
  parent_id,
  child_id,
  access_status,
  plan_name,
  trial_ends_at,
  current_period_ends_at,
  created_at,
  updated_at
)
select
  child.parent_id,
  child.id,
  'inactive',
  'No paid plan selected',
  null,
  null,
  now(),
  now()
from public.child_profiles child
where child.status <> 'inactive'
  and not exists (
    select 1
    from public.child_access access
    where access.child_id = child.id
  );

notify pgrst, 'reload schema';
