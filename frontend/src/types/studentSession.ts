export type StudentSession = {
  access_token: string;
  token_type: 'student';
  role: 'child';
  child_id: string;
  parent_id: string;
  student_name: string;
  grade_level: string;
  learning_levels?: Record<string, string>;
  access_allowed?: boolean;
  billing_status?: string | null;
  blocked_reason?: string | null;
  voice_allowed?: boolean;
  child_blocked_message?: string | null;
  expires_at: string;
  message: string;
};

export type FamilyClassroomLink = {
  family_code: string;
  classroom_path: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type StudentMe = {
  role: 'child';
  child_id: string;
  parent_id: string;
  student_name: string;
  grade_level: string;
  subjects: string[];
  learning_levels?: Record<string, string>;
  access_allowed?: boolean;
  billing_status?: string | null;
  blocked_reason?: string | null;
  voice_allowed?: boolean;
  child_blocked_message?: string | null;
  session_expires_at: string;
};
