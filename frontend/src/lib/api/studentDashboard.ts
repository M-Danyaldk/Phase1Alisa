import { apiGet } from '../api';
import { StudentDashboardData, StudentProgressItem } from '../../types/studentDashboard';

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
  subject_progress: DashboardProgressResponse[];
  recent_activity: DashboardActivityResponse[];
  achievements: DashboardAchievementResponse[];
  recommended_next_actions: string[];
};

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getStudentDashboard(accessToken: string, childId: string): Promise<StudentDashboardData> {
  const data = await apiGet<StudentDashboardResponse>(`/children/${childId}/dashboard`, authHeaders(accessToken));
  return {
    assessmentStatus: data.assessment_status,
    homeworkStatus: data.homework_status,
    weeklyFocus: data.weekly_focus,
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
