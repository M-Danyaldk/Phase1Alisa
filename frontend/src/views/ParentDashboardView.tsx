import { BarChart3, FileText, ShieldCheck, UserRoundPlus, WalletCards } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { ParentView } from '../types';
import { ChildProfile } from '../types/childProfile';

type Props = {
  parentName: string;
  children: ChildProfile[];
  selectedChildId: string;
  onSelectChild: (childId: string) => void;
  onOpenChildSession: (childId: string) => void;
  onViewChange: (view: ParentView) => void;
};

export function ParentDashboardView({
  parentName,
  children,
  selectedChildId,
  onSelectChild,
  onOpenChildSession,
  onViewChange,
}: Props) {
  const selectedChild = children.find(child => child.id === selectedChildId) || children[0];
  const selectedChildPaused = selectedChild?.status === 'inactive';

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent Dashboard" title={`Welcome, ${parentName}`} desc="Manage learning setup, review progress, and open a separate student classroom when a child is ready to learn." />

    <div className="parent-dashboard-grid">
      <section className="hero-card wide">
        <h3>Parent control center</h3>
        <p>Use this area for child profiles, reports, billing, and oversight. Live tutoring and assessment-taking happen only inside a child learning session.</p>
        <div className="parent-action-row">
          <button className="primary-button" onClick={() => onViewChange('reports')} disabled={!selectedChild}>View Reports</button>
          <button className="secondary-button" onClick={() => onViewChange('children')}>Manage Child Profiles</button>
          <button className="secondary-button" onClick={() => onViewChange('billing')}>Manage Billing</button>
        </div>
      </section>

      <section className="report-card child-entry-card">
        <div>
          <span className="eyebrow">Child Classroom</span>
          <h3>Who is learning today?</h3>
          <p>Select one child, then open the separate student login screen. Students use their Student Username and PIN.</p>
        </div>
        {children.length ? <>
          <label>Student
            <select value={selectedChild?.id || ''} onChange={event => onSelectChild(event.target.value)}>
              {children.map(child => <option key={child.id} value={child.id}>{child.name}{child.status === 'inactive' ? ' (paused)' : ''}</option>)}
            </select>
          </label>
          {selectedChildPaused && <p className="paused-access-note">This child&apos;s learning access is paused. Reactivate access before opening the student classroom.</p>}
          <button className="primary-button" onClick={() => selectedChild && onOpenChildSession(selectedChild.id)} disabled={selectedChildPaused}>Go to Student Login</button>
        </> : <>
          <p className="muted-copy">Create a child profile before opening a student classroom.</p>
          <button className="primary-button" onClick={() => onViewChange('children')}>Create Child Profile</button>
        </>}
      </section>
    </div>

    <div className="card-grid four">
      <InfoCard icon={<FileText />} title="Reports" desc="Review assessment results, summaries, strengths, and learning gaps." />
      <InfoCard icon={<BarChart3 />} title="Session History" desc="Monitor saved tutoring sessions and recent practice activity." />
      <InfoCard icon={<WalletCards />} title="Billing" desc="Manage child access and subscription readiness from the parent side." />
      <InfoCard icon={<ShieldCheck />} title="Brain Break Visibility" desc="See healthy learning safeguards without changing child-only tutoring behavior." />
    </div>

    <section className="report-card">
      <div className="section-row">
        <h3>Latest child context</h3>
        <button className="secondary-button compact" onClick={() => onViewChange('children')}><UserRoundPlus /> Child Profiles</button>
      </div>
      {selectedChild ? <div className="report-detail-list">
        <span>Viewing as parent: {selectedChild.name}</span>
        <span>Grade level: {selectedChild.grade_level}</span>
        <span>Subjects: {selectedChild.subjects.join(', ')}</span>
        <span>Status: {statusLabel(selectedChild.status)}</span>
      </div> : <p className="muted-copy">No child profile selected yet.</p>}
    </section>
  </div>;
}

function statusLabel(status: ChildProfile['status']): string {
  if (status === 'pending_consent') return 'Pending consent';
  if (status === 'inactive') return 'Paused';
  return 'Active';
}
