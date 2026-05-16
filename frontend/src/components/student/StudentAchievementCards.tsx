import { Award, Lock, Sparkles } from 'lucide-react';
import { StudentAchievement } from '../../types/studentDashboard';

export function StudentAchievementCards({ achievements }: { achievements: StudentAchievement[] }) {
  return <section className="report-card">
    <h3>Achievements</h3>
    <div className="student-achievement-grid">
      {achievements.map(item => <article className={`student-achievement-card ${item.status}`} key={item.id}>
        {iconForStatus(item.status)}
        <strong>{item.title}</strong>
        <p>{item.detail}</p>
      </article>)}
    </div>
  </section>;
}

function iconForStatus(status: StudentAchievement['status']) {
  if (status === 'locked') return <Lock />;
  if (status === 'in_progress') return <Sparkles />;
  return <Award />;
}
