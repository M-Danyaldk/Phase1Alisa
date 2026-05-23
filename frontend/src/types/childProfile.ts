export type ChildSubject = 'Math' | 'ELA' | 'Writing';
export type ChildStatus = 'active' | 'inactive' | 'pending_consent';

export type ChildProfile = {
  id: string;
  parent_id: string;
  name: string;
  grade_level: string;
  date_of_birth?: string | null;
  subjects: ChildSubject[];
  learning_goals?: string | null;
  difficulty_level?: string | null;
  parent_notes?: string | null;
  status: ChildStatus;
  parental_consent_accepted: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  learning_levels?: Record<string, string>;
};

export type ChildProfileFormValues = {
  name: string;
  grade_level: string;
  date_of_birth: string;
  subjects: ChildSubject[];
  learning_goals: string;
  difficulty_level: string;
  parent_notes: string;
  parental_consent_accepted: boolean;
};
