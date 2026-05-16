export type ChildAccessStatus = 'trial' | 'active' | 'inactive' | 'past_due';

export type ChildAccess = {
  id?: string | null;
  child_id: string;
  parent_id: string;
  child_name: string;
  grade_level: string;
  access_status: ChildAccessStatus;
  plan_name: string;
  trial_ends_at?: string | null;
  current_period_ends_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
