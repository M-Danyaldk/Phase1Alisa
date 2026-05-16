import { GraduationCap } from 'lucide-react';
import { StudentProfile } from '../../types';

export function StudentSummaryCard({ student, weeklyFocus }: { student: StudentProfile; weeklyFocus: string }) {
  return <section className="student-summary-card">
    <div className="student-avatar" aria-hidden="true">{student.name.charAt(0).toUpperCase()}</div>
    <div>
      <span>Selected Student</span>
      <h3>{student.name}</h3>
      <p><GraduationCap /> Grade {student.grade}</p>
      <p>{weeklyFocus}</p>
    </div>
  </section>;
}
