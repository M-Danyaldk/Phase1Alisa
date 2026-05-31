import { BarChart3, Copy, FileText, Gift, ShieldCheck, UserRoundPlus, WalletCards } from 'lucide-react';
import { useEffect, useState } from 'react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { getFilteredChildReport } from '../lib/api/reports';
import { getMyReferrals } from '../lib/api/referrals';
import { getParentWeeklyRhythm } from '../lib/api/studentDashboard';
import { ParentView } from '../types';
import { ChildProfile } from '../types/childProfile';
import { ReferralSummary } from '../types/referrals';
import { WeeklyRhythm } from '../types/studentDashboard';

type Props = {
  accessToken: string;
  parentName: string;
  children: ChildProfile[];
  selectedChildId: string;
  onSelectChild: (childId: string) => void;
  onOpenChildSession: (childId: string) => void;
  onViewChange: (view: ParentView) => void;
};

export function ParentDashboardView({
  accessToken,
  parentName,
  children,
  selectedChildId,
  onSelectChild,
  onOpenChildSession,
  onViewChange,
}: Props) {
  const selectedChild = children.find(child => child.id === selectedChildId) || children[0];
  const selectedChildPaused = selectedChild?.status === 'inactive';
  const [referralSummary, setReferralSummary] = useState<ReferralSummary | null>(null);
  const [weeklyRhythms, setWeeklyRhythms] = useState<WeeklyRhythm[]>([]);
  const [referralMessage, setReferralMessage] = useState('');
  const [hasLearningHistory, setHasLearningHistory] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    getMyReferrals(accessToken)
      .then(data => { if (!cancelled) setReferralSummary(data); })
      .catch(() => { if (!cancelled) setReferralSummary(null); });
    getParentWeeklyRhythm(accessToken)
      .then(data => { if (!cancelled) setWeeklyRhythms(data); })
      .catch(() => { if (!cancelled) setWeeklyRhythms([]); });
    return () => { cancelled = true; };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken || !children.length) {
      setHasLearningHistory(false);
      return;
    }
    let cancelled = false;
    Promise.all(children.map(child => getFilteredChildReport(accessToken, child.id, 'all', 'All').catch(() => null)))
      .then(reports => {
        if (!cancelled) setHasLearningHistory(reports.some(reportHasLearningHistory));
      })
      .catch(() => { if (!cancelled) setHasLearningHistory(false); });
    return () => { cancelled = true; };
  }, [accessToken, children]);

  const dashboardMessage = parentDashboardMessage(children, weeklyRhythms, hasLearningHistory);

  async function copyReferralLink() {
    if (!referralSummary?.referral_url) return;
    try {
      await navigator.clipboard.writeText(referralSummary.referral_url);
      setReferralMessage('Referral link copied.');
    } catch {
      setReferralMessage('Select and copy the referral link below.');
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent Dashboard" title={`Welcome, ${parentName}`} desc={dashboardMessage} />

    <div className="parent-dashboard-grid">
      <section className="hero-card wide">
        <h3>Parent control center</h3>
        <p>Use this area for child profiles, reports, billing, and oversight. Live tutoring and assessment-taking happen only after the student logs in with their own username and PIN.</p>
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
          <p>Select one child, then open the separate student login screen. Students use their Username and PIN.</p>
        </div>
        {children.length ? <>
          <label>Student
            <select value={selectedChild?.id || ''} onChange={event => onSelectChild(event.target.value)}>
              {children.map(child => <option key={child.id} value={child.id}>{child.name}{child.status === 'inactive' ? ' (paused)' : ''}</option>)}
            </select>
          </label>
          {selectedChildPaused && <p className="paused-access-note">This child&apos;s learning access is paused. Reactivate access before opening the student classroom.</p>}
          <button className="primary-button" onClick={() => selectedChild && onOpenChildSession(selectedChild.id)} disabled={selectedChildPaused}>Go to Child Login</button>
        </> : <>
          <p className="muted-copy">Create a child profile before opening a student classroom.</p>
          <button className="primary-button" onClick={() => onViewChange('children')}>Create Child Profile</button>
        </>}
      </section>
    </div>

    <div className="card-grid four">
      <InfoCard icon={<FileText />} title="Reports" desc="Review completed assessment results, summaries, strengths, and learning gaps." />
      <InfoCard icon={<BarChart3 />} title="Session History" desc="Monitor saved tutoring sessions and recent practice activity." />
      <InfoCard icon={<WalletCards />} title="Billing" desc="Manage child access and subscription readiness from the parent side." />
      <InfoCard icon={<ShieldCheck />} title="Brain Break Visibility" desc="See healthy learning safeguards without changing child-only tutoring behavior." />
    </div>

    <section className="report-card">
      <div className="section-row">
        <h3>Weekly Learning Rhythm</h3>
        <button className="secondary-button compact" onClick={() => onViewChange('reports')}>Reports</button>
      </div>
      <p className="muted-copy">Weekly rhythm resets every Monday. Missing a day never lowers a child&apos;s status; each new week starts fresh.</p>
      <div className="weekly-rhythm-list">
        {children.map(child => {
          const rhythm = weeklyRhythms.find(item => item.childId === child.id);
          return <div className="weekly-rhythm-row" key={child.id}>
            <strong>{child.name}</strong>
            <span>{rhythm?.displayLabel || 'Fresh Start'}</span>
            <small>{rhythm?.sessionCount ?? 0} session{(rhythm?.sessionCount ?? 0) === 1 ? '' : 's'} this week</small>
          </div>;
        })}
        {!children.length && <p className="muted-copy">Create a child profile to start weekly rhythm tracking.</p>}
      </div>
    </section>

    <section className="report-card">
      <div className="section-row">
        <h3><Gift /> Refer a Friend</h3>
        <button className="secondary-button compact" onClick={copyReferralLink} disabled={!referralSummary?.referral_url}><Copy /> Copy Link</button>
      </div>
      <p className="muted-copy">Share MsAlisia with another family. Referred parents receive the standard 7-day trial; rewards are earned automatically after qualifying paid activity.</p>
      {referralSummary ? <>
        <input className="referral-link-input" readOnly value={referralSummary.referral_url} aria-label="Referral link" />
        {referralMessage && <p className="success-note">{referralMessage}</p>}
        <div className="report-detail-list">
          <span>Referrals Sent: {referralSummary.referrals_sent}</span>
          <span>Successful Referrals: {referralSummary.successful_referrals}</span>
          <span>Rewards Earned: {referralSummary.rewards_earned}</span>
          <span>Latest Reward Status: {latestRewardStatus(referralSummary)}</span>
        </div>
      </> : <p className="muted-copy">Referral details will appear after your account is ready.</p>}
    </section>

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

function latestRewardStatus(summary: ReferralSummary): string {
  const latest = summary.rewards[0];
  if (latest?.status_label) return latest.status_label.replace(/_/g, ' ');
  if (latest?.reward_status) return latest.reward_status.replace(/_/g, ' ');
  const referral = summary.referrals[0];
  if (referral?.status_label) return referral.status_label.replace(/_/g, ' ');
  if (referral?.status) return referral.status.replace(/_/g, ' ');
  return 'No rewards yet';
}

function statusLabel(status: ChildProfile['status']): string {
  if (status === 'pending_consent') return 'Pending consent';
  if (status === 'inactive') return 'Paused';
  return 'Active';
}

function parentDashboardMessage(children: ChildProfile[], weeklyRhythms: WeeklyRhythm[], hasLearningHistory: boolean): string {
  if (!children.length) return 'Welcome to MsAlisia — let’s create your child’s profile.';
  const hasWeeklyActivity = weeklyRhythms.some(item => item.sessionCount > 0);
  if (hasLearningHistory || hasWeeklyActivity) return 'Welcome back — your child’s progress is waiting for you.';
  return 'Your child profile is ready — let’s start the first learning session.';
}

function reportHasLearningHistory(report: Awaited<ReturnType<typeof getFilteredChildReport>> | null): boolean {
  if (!report) return false;
  return Boolean(
    report.lessons_completed > 0
    || report.questions_practiced > 0
    || (report.recent_tutor_sessions || []).length
    || (report.recent_assessments || []).length
    || (report.recent_learning_memory || []).length
  );
}
