export type StudentSession = {
  access_token: string;
  token_type: 'student';
  role: 'child';
  child_id: string;
  parent_id: string;
  student_name: string;
  grade_level: string;
  expires_at: string;
  message: string;
};

export type StudentMe = {
  role: 'child';
  child_id: string;
  parent_id: string;
  student_name: string;
  grade_level: string;
  subjects: string[];
  session_expires_at: string;
};
