create unique index if not exists referral_rewards_referral_id_uidx
  on public.referral_rewards(referral_id);

notify pgrst, 'reload schema';
