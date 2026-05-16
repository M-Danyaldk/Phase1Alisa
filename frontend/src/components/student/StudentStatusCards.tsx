import { ClipboardCheck, ImageUp, Target } from 'lucide-react';
import { InfoCard } from '../InfoCard';

export function StudentStatusCards({
  assessmentStatus,
  homeworkStatus,
  weeklyFocus,
}: {
  assessmentStatus: string;
  homeworkStatus: string;
  weeklyFocus: string;
}) {
  return <div className="card-grid three">
    <InfoCard icon={<ClipboardCheck />} title="Assessment Status" desc={assessmentStatus} />
    <InfoCard icon={<ImageUp />} title="Homework Status" desc={homeworkStatus} />
    <InfoCard icon={<Target />} title="Weekly Focus" desc={weeklyFocus} />
  </div>;
}
