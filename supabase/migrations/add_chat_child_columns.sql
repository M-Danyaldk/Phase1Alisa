alter table public.chat_threads
  add column if not exists child_id uuid references public.child_profiles(id) on delete cascade;

alter table public.chat_messages
  add column if not exists child_id uuid references public.child_profiles(id) on delete cascade;

create index if not exists chat_threads_child_updated_idx
  on public.chat_threads(child_id, updated_at desc);

create index if not exists chat_messages_child_created_idx
  on public.chat_messages(child_id, created_at desc);

notify pgrst, 'reload schema';
