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
  const hasAssessment = !level.toLowerCase().includes('not assessed');
  const displaySubject = subjectLabel(subject);
  return {
    subject,
    level,
    progressPercentage: progressForLevel(level),
    currentFocus: hasAssessment ? `${displaySubject} practice path` : 'Start with a short placement check',
    nextStep: hasAssessment ? 'Practice one guided lesson with MsAlisia' : `Complete the ${displaySubject} quick assessment`,
    status: hasAssessment ? 'Learning path started' : 'Assessment needed',
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
    assessmentStatus: assessedCount ? `${assessedCount} of 3 subjects have a starting signal` : 'No assessments completed yet',
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
        detail: progress.find(item => item.progressPercentage > 0)?.nextStep || 'Begin with an assessment.',
        when: 'Next step',
      },
    ] : [
      {
        id: 'empty-assessment',
        title: 'No learning activity yet',
        detail: 'Start an assessment to unlock progress, reports, and recommendations.',
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
        id: 'first-assessment',
        title: 'First Assessment',
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
      assessedCount ? 'Continue the strongest subject with a short guided lesson.' : 'Start with the assessment center.',
      'Try one MsAlisia learning chat after the first assessment.',
      'Upload homework when written work is ready for lightweight feedback.',
    ],
  };
}
