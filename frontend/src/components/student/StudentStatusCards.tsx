import { CalendarDays, ClipboardCheck, ImageUp, Target } from 'lucide-react';
import { InfoCard } from '../InfoCard';
import { WeeklyRhythm } from '../../types/studentDashboard';

export function StudentStatusCards({
  assessmentStatus,
  homeworkStatus,
  weeklyFocus,
  weeklyRhythm,
}: {
  assessmentStatus: string;
  homeworkStatus: string;
  weeklyFocus: string;
  weeklyRhythm: WeeklyRhythm;
}) {
  return <div className="card-grid four">
    <InfoCard icon={<ClipboardCheck />} title="Latest Assessment" desc={assessmentStatus} />
    <InfoCard icon={<ImageUp />} title="Homework Status" desc={homeworkStatus} />
    <InfoCard icon={<Target />} title="Weekly Focus" desc={weeklyFocus} />
    <InfoCard icon={<CalendarDays />} title="Weekly Rhythm" desc={`${weeklyRhythm.displayLabel}: ${weeklyRhythm.sessionCount} session${weeklyRhythm.sessionCount === 1 ? '' : 's'} this week.`} />
  </div>;
}
