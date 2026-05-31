alter table public.waitlist
  add column if not exists metadata jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
