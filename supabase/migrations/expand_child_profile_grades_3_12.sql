do $$
declare
  constraint_record record;
begin
  for constraint_record in
    select conname
    from pg_constraint
    where conrelid = 'public.child_profiles'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) like '%grade_level%'
  loop
    execute format('alter table public.child_profiles drop constraint if exists %I', constraint_record.conname);
  end loop;
end $$;

alter table public.child_profiles
  add constraint child_profiles_grade_level_check
  check (grade_level in (
    'Grade 3',
    'Grade 4',
    'Grade 5',
    'Grade 6',
    'Grade 7',
    'Grade 8',
    'Grade 9',
    'Grade 10',
    'Grade 11',
    'Grade 12'
  ));

notify pgrst, 'reload schema';
