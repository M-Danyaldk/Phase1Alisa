export type BrainBreakWarning = '30_minute_warning' | '10_minute_warning' | '5_minute_warning' | string;

export type SessionStatusResponse = {
  child_id: string;
  session_id?: string | null;
  session_status: string;
  active_tutoring_seconds_today: number;
  brain_break_required: boolean;
  brain_break_active: boolean;
  break_ends_at?: string | null;
  seconds_until_resume: number;
  seconds_until_brain_break: number;
  warnings_due: BrainBreakWarning[];
  message: string;
};
