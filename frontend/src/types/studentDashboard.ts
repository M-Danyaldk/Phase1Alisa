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

export type WeeklyRhythm = {
  childId: string;
  weekStartDate: string;
  weekEndDate: string;
  sessionCount: number;
  activeTutoringSeconds: number;
  achievementLabel: string;
  displayLabel: string;
  childMessage: string;
  parentSummary: string;
};

export type StudentDashboardData = {
  assessmentStatus: string;
  homeworkStatus: string;
  weeklyFocus: string;
  weeklyRhythm: WeeklyRhythm;
  subjectProgress: StudentProgressItem[];
  recentActivity: StudentActivityItem[];
  achievements: StudentAchievement[];
  recommendedNextActions: string[];
};
