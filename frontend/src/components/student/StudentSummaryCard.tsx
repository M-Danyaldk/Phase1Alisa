import { GraduationCap } from 'lucide-react';
import { StudentProfile } from '../../types';
import { WeeklyRhythm } from '../../types/studentDashboard';

export function StudentSummaryCard({ student, weeklyFocus, weeklyRhythm }: { student: StudentProfile; weeklyFocus: string; weeklyRhythm: WeeklyRhythm }) {
  return <section className="student-summary-card">
    <div className="student-avatar" aria-hidden="true">{student.name.charAt(0).toUpperCase()}</div>
    <div>
      <span>Selected Student</span>
      <h3>{student.name}</h3>
      <p><GraduationCap /> Grade {student.grade}</p>
      <p>{weeklyFocus}</p>
      <div className="weekly-rhythm-pill">
        <strong>{weeklyRhythm.displayLabel}</strong>
        <small>{weeklyRhythm.childMessage}</small>
      </div>
    </div>
  </section>;
}
