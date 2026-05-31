import { apiGet } from '../api';
import { StudentDashboardData, StudentProgressItem, WeeklyRhythm } from '../../types/studentDashboard';

type DashboardProgressResponse = {
  subject: StudentProgressItem['subject'];
  level: string;
  progress_percentage: number;
  current_focus: string;
  next_step: string;
  status: string;
};

type DashboardActivityResponse = {
  id: string;
  title: string;
  detail: string;
  when: string;
  subject?: StudentProgressItem['subject'] | null;
};

type DashboardAchievementResponse = {
  id: string;
  title: string;
  detail: string;
  status: 'earned' | 'locked' | 'in_progress';
};

type StudentDashboardResponse = {
  assessment_status: string;
  homework_status: string;
  weekly_focus: string;
  weekly_rhythm: WeeklyRhythmResponse;
  subject_progress: DashboardProgressResponse[];
  recent_activity: DashboardActivityResponse[];
  achievements: DashboardAchievementResponse[];
  recommended_next_actions: string[];
};

type WeeklyRhythmResponse = {
  child_id: string;
  week_start_date: string;
  week_end_date: string;
  session_count: number;
  active_tutoring_seconds: number;
  achievement_label: string;
  display_label: string;
  child_message: string;
  parent_summary: string;
};

function authHeaders(accessToken: string, studentSession = false): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
  if (!studentSession) headers['x-access-mode'] = 'child';
  return headers;
}

export async function getStudentDashboard(accessToken: string, childId: string, studentSession = false): Promise<StudentDashboardData> {
  const data = await apiGet<StudentDashboardResponse>(`/children/${childId}/dashboard`, authHeaders(accessToken, studentSession));
  return {
    assessmentStatus: data.assessment_status,
    homeworkStatus: data.homework_status,
    weeklyFocus: data.weekly_focus,
    weeklyRhythm: rhythmFromResponse(data.weekly_rhythm),
    subjectProgress: data.subject_progress.map(item => ({
      subject: item.subject,
      level: item.level,
      progressPercentage: item.progress_percentage,
      currentFocus: item.current_focus,
      nextStep: item.next_step,
      status: item.status,
    })),
    recentActivity: data.recent_activity.map(item => ({
      id: item.id,
      title: item.title,
      detail: item.detail,
      when: item.when,
      subject: item.subject || undefined,
    })),
    achievements: data.achievements,
    recommendedNextActions: data.recommended_next_actions,
  };
}

export async function getParentWeeklyRhythm(accessToken: string): Promise<WeeklyRhythm[]> {
  const data = await apiGet<{ rhythms: WeeklyRhythmResponse[] }>('/children/weekly-rhythm', { Authorization: `Bearer ${accessToken}` });
  return data.rhythms.map(rhythmFromResponse);
}

function rhythmFromResponse(item: WeeklyRhythmResponse): WeeklyRhythm {
  return {
    childId: item.child_id,
    weekStartDate: item.week_start_date,
    weekEndDate: item.week_end_date,
    sessionCount: item.session_count,
    activeTutoringSeconds: item.active_tutoring_seconds,
    achievementLabel: item.achievement_label,
    displayLabel: item.display_label,
    childMessage: item.child_message,
    parentSummary: item.parent_summary,
  };
}
