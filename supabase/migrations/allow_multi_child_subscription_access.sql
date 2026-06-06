drop index if exists public.child_access_stripe_subscription_uidx;

create index if not exists child_access_stripe_subscription_idx
  on public.child_access(stripe_subscription_id)
  where stripe_subscription_id is not null;

notify pgrst, 'reload schema';
