import { Subject } from '../types';

export type StudentProgressItem = {
  subject: Subject;
  level: string;
  progressPercentage: number;
  currentFocus: string;
  nextStep: string;
  status: string;
};

export type StudentActivityItem = {
  id: string;
  title: string;
  detail: string;
  when: string;
  subject?: Subject;
};

export type StudentAchievement = {
  id: string;
  title: string;
  detail: string;
  status: 'earned' | 'locked' | 'in_progress';
};

export type StudentDashboardData = {
  assessmentStatus: string;
  homeworkStatus: string;
  weeklyFocus: string;
  subjectProgress: StudentProgressItem[];
  recentActivity: StudentActivityItem[];
  achievements: StudentAchievement[];
  recommendedNextActions: string[];
};
