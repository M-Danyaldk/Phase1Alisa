import { useEffect, useState } from 'react';
import { StudentAchievementCards } from '../components/student/StudentAchievementCards';
import { StudentActivityList } from '../components/student/StudentActivityList';
import { StudentNextActions } from '../components/student/StudentNextActions';
import { StudentProgressCards } from '../components/student/StudentProgressCards';
import { StudentStatusCards } from '../components/student/StudentStatusCards';
import { StudentSummaryCard } from '../components/student/StudentSummaryCard';
import { SectionHeader } from '../components/SectionHeader';
import { getStudentDashboard } from '../lib/api/studentDashboard';
import { buildStudentDashboardMock } from '../mock/studentDashboard';
import { StudentProfile, View } from '../types';
import { StudentDashboardData } from '../types/studentDashboard';

export function HomeView({
  student,
  accessToken = '',
  childId = '',
  studentSession = false,
  notice = '',
  setView,
}: {
  student: StudentProfile;
  accessToken?: string;
  childId?: string;
  studentSession?: boolean;
  notice?: string;
  setView: (v: View) => void;
}) {
  const [dashboard, setDashboard] = useState<StudentDashboardData>(() => buildStudentDashboardMock(student));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fallback = buildStudentDashboardMock(student);
    setDashboard(fallback);
    if (!accessToken || !childId) {
      setError('');
      return;
    }
    setLoading(true);
    setError('');
    getStudentDashboard(accessToken, childId, studentSession)
      .then(setDashboard)
      .catch(err => {
        setDashboard(fallback);
        const message = err instanceof Error ? err.message : 'Could not load student dashboard data.';
        setError(childFriendlyMessage(message));
      })
      .finally(() => setLoading(false));
  }, [accessToken, childId, student, studentSession]);

  return <div className="page-stack">
    <SectionHeader eyebrow="Student Dashboard" title={`${student.name}'s learning home`} desc="A focused view of progress, recent activity, achievements, and the next best learning actions." />
    {notice && <p className="success-note dashboard-notice">{notice}</p>}
    {loading && <p className="muted-note">Loading student dashboard...</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="student-dashboard-hero">
      <StudentSummaryCard student={student} weeklyFocus={dashboard.weeklyFocus} weeklyRhythm={dashboard.weeklyRhythm} />
      <StudentNextActions actions={dashboard.recommendedNextActions} setView={setView} />
    </div>

    <StudentStatusCards assessmentStatus={dashboard.assessmentStatus} homeworkStatus={dashboard.homeworkStatus} weeklyFocus={dashboard.weeklyFocus} weeklyRhythm={dashboard.weeklyRhythm} />
    <StudentProgressCards progress={dashboard.subjectProgress} />

    <div className="student-dashboard-grid">
      <StudentActivityList activity={dashboard.recentActivity} />
      <StudentAchievementCards achievements={dashboard.achievements} />
    </div>
  </div>;
}

function childFriendlyMessage(message: string): string {
  if (message.includes('There is something your parent needs to take care of')) return message;
  if (message.toLowerCase().includes('payment') || message.toLowerCase().includes('billing') || message.toLowerCase().includes('subscription')) {
    return 'There is something your parent needs to take care of before learning can continue.';
  }
  return message;
}
