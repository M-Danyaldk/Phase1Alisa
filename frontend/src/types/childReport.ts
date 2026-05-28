import { HomeworkUpload } from './homework';

export type SubjectProgress = {
  subject: string;
  level: string;
  progress_percentage: number;
  current_topic?: string | null;
  strong_area?: string | null;
  needs_review?: string | null;
  recent_improvement?: string | null;
  completed_lessons: number;
  assessment_count: number;
  chat_count: number;
  message_count: number;
  last_activity_at?: string | null;
};

export type AssessmentSummary = {
  id?: number | string | null;
  subject: string;
  estimated_level: string;
  score_label?: string | null;
  strengths: string[];
  learning_gaps: string[];
  recommended_progression: string[];
  recommended_next_topics: string[];
  parent_summary?: string | null;
  created_at?: string | null;
};

export type TutorSessionSummary = {
  thread_id: string;
  subject: string;
  topic?: string | null;
  title?: string | null;
  message_count: number;
  time_spent: string;
  hints_used: number;
  practice_attempts: number;
  improvement_status: string;
  next_step: string;
  last_activity_at?: string | null;
};

export type ChildReport = {
  child_id: string;
  child_name: string;
  grade_level: string;
  report_period: string;
  subject_filter: string;
  current_learning_level: string;
  last_updated_at?: string | null;
  lessons_completed: number;
  questions_practiced: number;
  assessment_status: string;
  overall_summary: string;
  weekly_progress: string;
  time_spent_learning: string;
  brain_break_summary: string;
  subject_progress: SubjectProgress[];
  recent_assessments: AssessmentSummary[];
  recent_tutor_sessions: TutorSessionSummary[];
  homework_uploads: HomeworkUpload[];
  strengths: string[];
  weak_areas: string[];
  recommended_next_steps: string[];
};

export type WeeklyReportEmailPreview = {
  child_id: string;
  child_name: string;
  parent_id: string;
  report_period: string;
  subject_line: string;
  greeting: string;
  summary: string;
  subject_progress: SubjectProgress[];
  strengths: string[];
  weak_areas: string[];
  recommended_next_steps: string[];
  brain_break_summary: string;
  generated_at: string;
  email_connected: boolean;
  email_note: string;
};
