alter table public.billing_discounts
  alter column removes_at_period_end set default false;

update public.billing_discounts
set removes_at_period_end = false
where removes_at_period_end is null;

alter table public.billing_discounts
  alter column removes_at_period_end set not null;

notify pgrst, 'reload schema';
