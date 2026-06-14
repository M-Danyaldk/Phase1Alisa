import { BarChart3, Copy, FileText, Gift, ShieldCheck, UserRoundPlus, WalletCards } from 'lucide-react';
import { useEffect, useState } from 'react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { subjectLabel } from '../constants';
import { getMyReferrals } from '../lib/api/referrals';
import { getFamilyClassroomLink } from '../lib/api/studentAuth';
import { getParentWeeklyRhythm } from '../lib/api/studentDashboard';
import { ParentView } from '../types';
import { ChildAccess } from '../types/billing';
import { ChildProfile } from '../types/childProfile';
import { ReferralSummary } from '../types/referrals';
import { FamilyClassroomLink } from '../types/studentSession';
import { WeeklyRhythm } from '../types/studentDashboard';

type Props = {
  accessToken: string;
  parentName: string;
  children: ChildProfile[];
  selectedChildId: string;
  selectedChildAccess?: ChildAccess | null;
  trialAvailable?: boolean;
  billingLocked?: boolean;
  onSelectChild: (childId: string) => void;
  onViewChange: (view: ParentView) => void;
};

export function ParentDashboardView({
  accessToken,
  parentName,
  children,
  selectedChildId,
  selectedChildAccess = null,
  trialAvailable = false,
  billingLocked = false,
  onSelectChild,
  onViewChange,
}: Props) {
  const selectedChild = children.find(child => child.id === selectedChildId) || children[0];
  const hasActiveChild = children.some(child => child.status !== 'inactive');
  const [referralSummary, setReferralSummary] = useState<ReferralSummary | null>(null);
  const [weeklyRhythms, setWeeklyRhythms] = useState<WeeklyRhythm[]>([]);
  const [familyLink, setFamilyLink] = useState<FamilyClassroomLink | null>(null);
  const [referralMessage, setReferralMessage] = useState('');
  const [classroomMessage, setClassroomMessage] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    getMyReferrals(accessToken)
      .then(data => { if (!cancelled) setReferralSummary(data); })
      .catch(() => { if (!cancelled) setReferralSummary(null); });
    getParentWeeklyRhythm(accessToken)
      .then(data => { if (!cancelled) setWeeklyRhythms(data); })
      .catch(() => { if (!cancelled) setWeeklyRhythms([]); });
    getFamilyClassroomLink(accessToken)
      .then(data => { if (!cancelled) setFamilyLink(data); })
      .catch(() => { if (!cancelled) setFamilyLink(null); });
    return () => { cancelled = true; };
  }, [accessToken]);

  const selectedChildRhythm = selectedChild ? weeklyRhythms.find(item => item.childId === selectedChild.id) : null;
  const dashboardMessage = parentDashboardMessage(children, selectedChild, selectedChildRhythm);
  const selectedChildHasLearningAccess = childAccessAllowsLearning(selectedChildAccess);
  const selectedChildCanStartTrial = Boolean(selectedChild && trialAvailable && !selectedChildHasLearningAccess && !billingLocked);

  async function copyReferralLink() {
    if (!referralSummary?.referral_url) return;
    try {
      await navigator.clipboard.writeText(referralSummary.referral_url);
      setReferralMessage('Referral link copied.');
    } catch {
      setReferralMessage('Select and copy the referral link below.');
    }
  }

  const classroomUrl = familyLink ? `${window.location.origin}${familyLink.classroom_path}` : '';

  async function copyClassroomLink() {
    if (!classroomUrl) return;
    try {
      await navigator.clipboard.writeText(classroomUrl);
      setClassroomMessage('Family classroom link copied.');
    } catch {
      setClassroomMessage('Select and copy the family classroom link below.');
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent Dashboard" title={`Welcome, ${parentName}`} desc={dashboardMessage} />

    <div className="parent-dashboard-grid">
      <section className="hero-card wide">
        <h3>{selectedChild ? `${selectedChild.name}'s parent control center` : 'Parent control center'}</h3>
        <p>{selectedChild ? `${selectedChild.name}'s profile, reports, billing, and classroom access are selected.` : 'Use this area for child profiles, reports, billing, and oversight.'} Live tutoring and assessment-taking happen only after the student logs in with their own username and PIN.</p>
        <div className="parent-action-row">
          <button className="primary-button" onClick={() => onViewChange('reports')} disabled={!selectedChild}>View Reports</button>
          <button className="secondary-button" onClick={() => onViewChange('children')}>Manage Child Profiles</button>
          <button className="secondary-button" onClick={() => onViewChange('billing')}>Manage Billing</button>
        </div>
      </section>

      <section className="report-card child-entry-card">
        <div>
          <span className="eyebrow">Child Classroom</span>
          <h3>{selectedChild ? `${selectedChild.name}'s classroom access` : 'Family classroom link'}</h3>
          <p>{selectedChild ? `${selectedChild.name} signs in from the family classroom link with their own username and PIN.` : 'Use this family classroom link for your children. Each child signs in with their own username and PIN.'}</p>
        </div>
        {children.length ? <>
          <label>Student
            <select value={selectedChild?.id || ''} onChange={event => onSelectChild(event.target.value)}>
              {children.map(child => <option key={child.id} value={child.id}>{child.name}{child.status === 'inactive' ? ' (paused)' : ''}</option>)}
            </select>
          </label>
          {!hasActiveChild && <p className="paused-access-note">Learning access is paused for every child. Reactivate access before using the classroom link.</p>}
          {selectedChildCanStartTrial && <p className="success-note">The 7-day free trial starts automatically when this child logs in for the first time.</p>}
          {billingLocked && <p className="paused-access-note">{selectedChild?.name || 'This child'} needs a paid plan before the classroom can open.</p>}
          {classroomUrl ? <>
            <input className="referral-link-input" readOnly value={classroomUrl} aria-label="Family classroom link" />
            <div className="parent-action-row">
              <button className="primary-button" onClick={() => billingLocked ? onViewChange('billing') : window.location.assign(classroomUrl)} disabled={!hasActiveChild}>
                {billingLocked ? 'Choose Plan' : 'Open Classroom'}
              </button>
              <button className="secondary-button" onClick={copyClassroomLink} type="button"><Copy /> Copy Link</button>
            </div>
            {classroomMessage && <p className="success-note">{classroomMessage}</p>}
        </> : <p className="muted-copy">Family classroom link will appear when your account is ready.</p>}
      </> : <>
        <p className="muted-copy">Create a child profile before opening a student classroom.</p>
        <button className="primary-button" onClick={() => onViewChange('children')}>Create Child Profile</button>
      </>}
      </section>
    </div>

    <section className="report-card">
      <div className="section-row">
        <h3>How to use MsAlisia</h3>
        <span className="muted-note">Quick start</span>
      </div>
      <ul>
        <li>Create or review each child profile.</li>
        <li>Set each child&apos;s username and PIN.</li>
        <li>Share the family classroom link with your children.</li>
        <li>Review reports and homework history from the parent dashboard.</li>
        <li>Manage billing and access from the billing page.</li>
      </ul>
    </section>

    <div className="card-grid four">
      <InfoCard icon={<FileText />} title="Reports" desc="Review completed assessment results, summaries, strengths, and areas to review." />
      <InfoCard icon={<BarChart3 />} title="Session History" desc="Monitor saved tutoring sessions and recent practice activity." />
      <InfoCard icon={<WalletCards />} title="Billing" desc="Manage child access and subscription readiness from the parent side." />
      <InfoCard icon={<ShieldCheck />} title="Brain Break Visibility" desc="See healthy learning safeguards without changing child-only tutoring behavior." />
    </div>

    <section className="report-card">
      <div className="section-row">
        <h3>{selectedChild ? `${selectedChild.name}'s Weekly Rhythm` : 'Weekly Learning Rhythm'}</h3>
        <button className="secondary-button compact" onClick={() => onViewChange('reports')}>Reports</button>
      </div>
      <p className="muted-copy">Weekly rhythm resets every Monday. Missing a day never lowers a child&apos;s status; each new week starts fresh.</p>
      {selectedChild && <div className="report-detail-list">
        <span>Selected child: {selectedChild.name}</span>
        <span>Weekly status: {selectedChildRhythm?.displayLabel || 'Fresh Start'}</span>
        <span>Sessions this week: {selectedChildRhythm?.sessionCount ?? 0}</span>
        <span>Access: {selectedChildHasLearningAccess ? 'Active' : billingLocked ? 'Billing required' : statusLabel(selectedChild.status)}</span>
      </div>}
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
        <span>Subjects: {selectedChild.subjects.map(subjectLabel).join(', ')}</span>
        <span>Status: {statusLabel(selectedChild.status)}</span>
      </div> : <p className="muted-copy">No child profile selected yet.</p>}
    </section>
  </div>;
}

function childAccessAllowsLearning(record: ChildAccess | null): boolean {
  if (!record) return false;
  const now = Date.now();
  if (record.access_status === 'trial') {
    return Boolean(record.trial_ends_at && Date.parse(record.trial_ends_at) > now);
  }
  if (record.access_status === 'active') {
    return !record.current_period_ends_at || Date.parse(record.current_period_ends_at) > now;
  }
  return false;
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
  if (status === 'inactive') return 'Paused';
  return 'Active';
}

function parentDashboardMessage(children: ChildProfile[], selectedChild?: ChildProfile, selectedChildRhythm?: WeeklyRhythm | null): string {
  if (!children.length) return 'Welcome to MsAlisia - let us create your child profile.';
  if (!selectedChild) return 'Select a child to review classroom access, reports, and weekly rhythm.';
  if ((selectedChildRhythm?.sessionCount ?? 0) > 0) return `Welcome back - ${selectedChild.name}'s progress is waiting for you.`;
  return `${selectedChild.name}'s profile is ready - start the first learning session when your child is ready.`;
}
