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
  setView,
}: {
  student: StudentProfile;
  accessToken?: string;
  childId?: string;
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
    getStudentDashboard(accessToken, childId)
      .then(setDashboard)
      .catch(err => {
        setDashboard(fallback);
        setError(err instanceof Error ? err.message : 'Could not load student dashboard data.');
      })
      .finally(() => setLoading(false));
  }, [accessToken, childId, student]);

  return <div className="page-stack">
    <SectionHeader eyebrow="Student Dashboard" title={`${student.name}'s learning home`} desc="A focused view of progress, recent activity, achievements, and the next best learning actions." />
    {loading && <p className="muted-note">Loading student dashboard...</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="student-dashboard-hero">
      <StudentSummaryCard student={student} weeklyFocus={dashboard.weeklyFocus} />
      <StudentNextActions actions={dashboard.recommendedNextActions} setView={setView} />
    </div>

    <StudentStatusCards assessmentStatus={dashboard.assessmentStatus} homeworkStatus={dashboard.homeworkStatus} weeklyFocus={dashboard.weeklyFocus} />
    <StudentProgressCards progress={dashboard.subjectProgress} />

    <div className="student-dashboard-grid">
      <StudentActivityList activity={dashboard.recentActivity} />
      <StudentAchievementCards achievements={dashboard.achievements} />
    </div>
  </div>;
}
