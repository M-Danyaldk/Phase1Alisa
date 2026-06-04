import { Clock } from 'lucide-react';
import { subjectLabel } from '../../constants';
import { StudentActivityItem } from '../../types/studentDashboard';

export function StudentActivityList({ activity }: { activity: StudentActivityItem[] }) {
  return <section className="report-card">
    <h3>Recent Learning Activity</h3>
    <div className="student-activity-list">
      {activity.map(item => <article className="student-activity-item" key={item.id}>
        <Clock />
        <div>
          <strong>{item.title}</strong>
          <p>{item.detail}</p>
          <span>{item.subject ? `${subjectLabel(item.subject)} - ` : ''}{item.when}</span>
        </div>
      </article>)}
    </div>
  </section>;
}
