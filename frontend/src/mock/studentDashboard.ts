import { StudentProfile } from '../types';
import { subjectLabel } from '../constants';
import { StudentDashboardData, StudentProgressItem } from '../types/studentDashboard';

function progressForLevel(level: string): number {
  const normalized = level.toLowerCase();
  if (normalized.includes('strong') || normalized.includes('above')) return 72;
  if (normalized.includes('grade') || normalized.includes('on track')) return 54;
  if (normalized.includes('review') || normalized.includes('needs')) return 28;
  return 0;
}

function progressItem(subject: StudentProgressItem['subject'], level: string): StudentProgressItem {
  const hasCheckIn = !level.toLowerCase().includes('not assessed');
  const displaySubject = subjectLabel(subject);
  return {
    subject,
    level,
    progressPercentage: progressForLevel(level),
    currentFocus: hasCheckIn ? `${displaySubject} practice path` : 'Start with a short check-in',
    nextStep: hasCheckIn ? 'Practice one guided lesson with MsAlisia' : `Try the ${displaySubject} Quick Check-In`,
    status: hasCheckIn ? 'Learning path started' : 'Check-In ready',
  };
}

export function buildStudentDashboardMock(student: StudentProfile): StudentDashboardData {
  const progress = [
    progressItem('Math', student.math_level),
    progressItem('ELA', student.ela_level),
    progressItem('Writing', student.writing_level),
  ];
  const assessedCount = progress.filter(item => item.progressPercentage > 0).length;

  return {
    assessmentStatus: assessedCount ? `${assessedCount} of 3 subjects have a starting signal` : 'No check-ins finished yet',
    homeworkStatus: 'No homework upload reviewed yet',
    weeklyFocus: student.focus_notes || 'Start with short lessons and quick check-ins',
    weeklyRhythm: {
      childId: 'mock-child',
      weekStartDate: '',
      weekEndDate: '',
      sessionCount: 0,
      activeTutoringSeconds: 0,
      achievementLabel: 'fresh_start',
      displayLabel: 'Fresh Start',
      childMessage: 'A fresh week is ready when you are. No pressure, just one good step.',
      parentSummary: 'Fresh Start: no sessions yet this week.',
    },
    subjectProgress: progress,
    recentActivity: assessedCount ? [
      {
        id: 'profile-ready',
        title: 'Learning profile ready',
        detail: `${student.name}'s grade and focus notes are available for tutoring.`,
        when: 'Today',
      },
      {
        id: 'next-practice',
        title: 'Next practice recommended',
        detail: progress.find(item => item.progressPercentage > 0)?.nextStep || 'Begin with a Quick Check-In.',
        when: 'Next step',
      },
    ] : [
      {
        id: 'empty-check-in',
        title: 'No learning activity yet',
        detail: 'Start a quick check-in or tutoring chat so Ms. Alisia can help you pick the next step.',
        when: 'Not started',
      },
    ],
    achievements: [
      {
        id: 'profile-created',
        title: 'Profile Started',
        detail: `${student.name}'s learning profile is ready.`,
        status: 'earned',
      },
      {
        id: 'first-check-in',
        title: 'First Check-In',
        detail: 'Complete one subject check to unlock a learning path.',
        status: assessedCount ? 'earned' : 'in_progress',
      },
      {
        id: 'three-subjects',
        title: 'Three Subject Starter',
        detail: 'Complete Math, Reading, and Writing checks.',
        status: assessedCount === 3 ? 'earned' : 'locked',
      },
    ],
    recommendedNextActions: [
      assessedCount ? 'Continue the strongest subject with a short guided lesson.' : 'Start with a Quick Check-In.',
      'Try one MsAlisia learning chat after the first check-in.',
      'Use Homework Help when written work is ready for lightweight feedback.',
    ],
  };
}
