import { BookOpen, ClipboardCheck, PenTool } from 'lucide-react';
import { StudentProgressItem } from '../../types/studentDashboard';

export function StudentProgressCards({ progress }: { progress: StudentProgressItem[] }) {
  return <section className="report-card">
    <h3>Subject Progress</h3>
    <div className="subject-progress-grid">
      {progress.map(item => <article className="subject-progress-card" key={item.subject}>
        <div className="subject-progress-title">
          {iconForSubject(item.subject)}
          <div>
            <strong>{item.subject}</strong>
            <span>{item.status}</span>
          </div>
        </div>
        <div className="progress-track" aria-label={`${item.subject} progress ${item.progressPercentage}%`}>
          <span style={{ width: `${item.progressPercentage}%` }} />
        </div>
        <p>{item.level}</p>
        <div className="report-detail-list">
          <span>Focus: {item.currentFocus}</span>
          <span>Next: {item.nextStep}</span>
        </div>
      </article>)}
    </div>
  </section>;
}

function iconForSubject(subject: StudentProgressItem['subject']) {
  if (subject === 'ELA') return <BookOpen />;
  if (subject === 'Writing') return <PenTool />;
  return <ClipboardCheck />;
}
