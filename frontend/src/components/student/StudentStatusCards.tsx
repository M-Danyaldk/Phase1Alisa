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
    <InfoCard icon={<ClipboardCheck />} title="Latest Check-In" desc={assessmentStatus} />
    <InfoCard icon={<ImageUp />} title="Homework Help" desc={homeworkStatus} />
    <InfoCard icon={<Target />} title="Weekly Focus" desc={childFriendlyWeeklyFocus(weeklyFocus)} />
    <InfoCard icon={<CalendarDays />} title="Weekly Rhythm" desc={`${weeklyRhythm.displayLabel}: ${weeklyRhythm.sessionCount} session${weeklyRhythm.sessionCount === 1 ? '' : 's'} this week.`} />
  </div>;
}

function childFriendlyWeeklyFocus(weeklyFocus: string): string {
  const value = weeklyFocus.trim();
  if (!value) return 'This week: Try one practice activity and keep going.';

  const subject = value.match(/\b(reading|vocabulary|math|writing|ela|homework)\b/i)?.[1] ?? 'learning';
  const label = subject.toLowerCase() === 'ela' ? 'Reading' : subject.charAt(0).toUpperCase() + subject.slice(1).toLowerCase();

  return `This week: Practice ${label} - you're getting there!`;
}
