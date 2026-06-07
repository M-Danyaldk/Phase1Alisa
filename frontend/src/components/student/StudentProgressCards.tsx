import { BookOpen, ClipboardCheck, PenTool } from 'lucide-react';
import { subjectLabel } from '../../constants';
import { StudentProgressItem } from '../../types/studentDashboard';

export function StudentProgressCards({ progress }: { progress: StudentProgressItem[] }) {
  return <section className="report-card">
    <h3>Subject Progress</h3>
    <div className="subject-progress-grid">
      {progress.map(item => <article className="subject-progress-card" key={item.subject}>
        <div className="subject-progress-title">
          {iconForSubject(item.subject)}
          <div>
            <strong>{subjectLabel(item.subject)}</strong>
            <span>{item.status}</span>
          </div>
        </div>
        <div className="progress-track" aria-label={`${subjectLabel(item.subject)} progress ${item.progressPercentage}%`}>
          <span style={{ width: `${item.progressPercentage}%` }} />
        </div>
        <p>{displayStudentProgressLevel(item)}</p>
        <div className="report-detail-list">
          <span>Focus: {item.currentFocus}</span>
          <span>Next: {item.nextStep}</span>
        </div>
      </article>)}
    </div>
  </section>;
}

function displayStudentProgressLevel(item: StudentProgressItem): string {
  if (item.enrolledGrade) return item.level;
  return item.level.replace(/^Grade\s+\d+\s*[-:–—]?\s*/i, 'Practice focus: ');
}

function iconForSubject(subject: StudentProgressItem['subject']) {
  if (subject === 'ELA') return <BookOpen />;
  if (subject === 'Writing') return <PenTool />;
  return <ClipboardCheck />;
}
