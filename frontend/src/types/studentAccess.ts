export type StudentAccess = {
  id?: string | null;
  parent_id: string;
  child_id: string;
  username: string;
  is_active: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type StudentAccessFormValues = {
  username: string;
  pin: string;
  is_active: boolean;
};
