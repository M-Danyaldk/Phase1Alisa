import { GraduationCap } from 'lucide-react';
import { StudentProfile } from '../../types';
import { WeeklyRhythm } from '../../types/studentDashboard';

export function StudentSummaryCard({ student, weeklyFocus, weeklyRhythm }: { student: StudentProfile; weeklyFocus: string; weeklyRhythm: WeeklyRhythm }) {
  return <section className="student-summary-card">
    <div className="student-avatar" aria-hidden="true">{student.name.charAt(0).toUpperCase()}</div>
    <div>
      <h3>{student.name}</h3>
      <p><GraduationCap /> Grade {student.grade}</p>
      <p>{childFriendlyWeeklyFocus(weeklyFocus)}</p>
      <div className="weekly-rhythm-pill">
        <strong>{weeklyRhythm.displayLabel}</strong>
        <small>{weeklyRhythm.childMessage}</small>
      </div>
    </div>
  </section>;
}

function childFriendlyWeeklyFocus(weeklyFocus: string): string {
  const value = weeklyFocus.trim();
  if (!value) return 'This week: Try one practice activity and keep going.';

  const subject = value.match(/\b(reading|vocabulary|math|writing|ela|homework)\b/i)?.[1] ?? 'learning';
  const label = subject.toLowerCase() === 'ela' ? 'Reading' : subject.charAt(0).toUpperCase() + subject.slice(1).toLowerCase();

  return `This week: Practice ${label} - you're getting there!`;
}
