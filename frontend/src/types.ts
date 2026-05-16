export type View = 'home' | 'profile' | 'onboarding' | 'children' | 'assessments' | 'learn' | 'homework' | 'reports' | 'admin' | 'billing' | 'future';
export type Subject = 'Math' | 'ELA' | 'Writing';

export type StudentProfile = {
  id?: number | string;
  name: string;
  grade: number;
  math_level: string;
  ela_level: string;
  writing_level: string;
  confidence: string;
  focus_notes: string;
  parent_notes: string;
  created_at?: string;
};

export type ChatMessage = { role: 'student' | 'msalisia'; content: string; provider?: string; subject?: string };

export type TutoringState = {
  active_problem: string;
  current_subject?: string;
  full_problem?: string;
  completed_steps?: string[];
  current_expression?: string;
  remaining_steps?: string[];
  current_step: string;
  current_question?: string;
  expected_answer?: string;
  student_answer?: string;
  correctness_status?: string;
  skill?: string;
  step_number?: number;
  attempt_count: number;
  hint_given?: boolean;
  answer_revealed: boolean;
  next_similar_question?: string;
  mode: string;
  status: string;
  memory_note: string;
};

export type AssessmentResult = {
  subject: Subject;
  enrolled_grade: number;
  estimated_level: string;
  score_label: string;
  strengths: string[];
  learning_gaps: string[];
  recommended_progression: string[];
  parent_summary: string;
};

export type StoredAssessmentResult = {
  id?: number | string;
  student_name?: string;
  subject: string;
  estimated_level: string;
  learning_gaps?: string;
  recommended_progression?: string;
  parent_summary?: string;
  created_at?: string;
};

export type LLMEvent = {
  id?: number | string;
  provider: string;
  model: string;
  purpose: string;
  fallback_used: number | boolean;
  created_at?: string;
};

export type AdminOverview = {
  students: StudentProfile[];
  assessments: StoredAssessmentResult[];
  llm_events: LLMEvent[];
};
