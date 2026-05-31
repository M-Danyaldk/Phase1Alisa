import { Subject } from '../types';

export type ProblemReportSource = 'learning' | 'homework' | 'assessment';
export type ProblemReportCategory = 'something_wrong' | 'unsafe_or_uncomfortable' | 'confusing_answer' | 'technical_issue' | 'other';

export type ProblemReportPayload = {
  reporter_type: 'child' | 'parent';
  child_id: string;
  source: ProblemReportSource;
  category: ProblemReportCategory;
  description: string;
  subject?: Subject;
  session_id?: string | null;
  thread_id?: string | null;
  message_id?: string | null;
  message_context?: string | null;
};

export type ProblemReportResponse = {
  success: boolean;
  message: string;
  report_id?: string | null;
  support_alert_sent: boolean;
};
