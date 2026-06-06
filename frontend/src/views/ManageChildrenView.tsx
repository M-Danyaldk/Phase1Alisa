import { BookOpen, CalendarDays, CreditCard, Eye, GraduationCap, KeyRound, Lock, Pencil, PlusCircle, SlidersHorizontal, User, UsersRound } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ChildProfileForm } from '../components/parent/ChildProfileForm';
import { StudentAccessForm } from '../components/parent/StudentAccessForm';
import { SectionHeader } from '../components/SectionHeader';
import { getStudentAccess, saveStudentAccess } from '../lib/api/studentAccess';
import { createChild, updateChild } from '../lib/api/children';
import { BillingStatus, ChildAccess } from '../types/billing';
import { ChildProfile, ChildProfileFormValues, ChildSubject } from '../types/childProfile';
import { StudentAccess } from '../types/studentAccess';

const BILLING_TARGET_CHILD_KEY = 'msalisia_billing_target_child';

export function ManageChildrenView({
  accessToken,
  children,
  selectedChildId,
  billingStatus,
  onSelectChild,
  onOpenBilling,
  onChildrenChanged,
}: {
  accessToken: string;
  children: ChildProfile[];
  selectedChildId: string;
  billingStatus?: BillingStatus | null;
  onSelectChild: (childId: string) => void;
  onOpenBilling: () => void;
  onChildrenChanged: (children: ChildProfile[], selectedChildId?: string) => void;
}) {
  const [editingChildId, setEditingChildId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [newStudentUsername, setNewStudentUsername] = useState('');
  const [newStudentPin, setNewStudentPin] = useState('');
  const [studentAccessByChildId, setStudentAccessByChildId] = useState<Record<string, StudentAccess | null>>({});
  const selectedChild = children.find(child => child.id === selectedChildId) || children[0] || null;
  const editingChild = children.find(child => child.id === editingChildId) || null;
  const childAccessById = useMemo(() => {
    const entries = (billingStatus?.children || []).map(record => [record.child_id, record] as const);
    return Object.fromEntries(entries) as Record<string, ChildAccess | undefined>;
  }, [billingStatus?.children]);

  useEffect(() => {
    if (!children.length) {
      setStudentAccessByChildId({});
      return;
    }
    let cancelled = false;
    Promise.all(children.map(child => getStudentAccess(accessToken, child.id).then(record => [child.id, record] as const).catch(() => [child.id, null] as const)))
      .then(entries => {
        if (!cancelled) setStudentAccessByChildId(Object.fromEntries(entries));
      });
    return () => { cancelled = true; };
  }, [accessToken, children]);

  useEffect(() => {
    if (!editingChildId || adding || !selectedChildId || editingChildId === selectedChildId) return;
    if (children.some(child => child.id === selectedChildId)) {
      setEditingChildId(selectedChildId);
    }
  }, [adding, children, editingChildId, selectedChildId]);

  async function add(values: ChildProfileFormValues) {
    const username = newStudentUsername.trim().toLowerCase();
    const pin = newStudentPin.trim();
    if (!username || !pin) {
      setError('Username and PIN are required when creating a child profile.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const child = await createChild(accessToken, values);
      const studentAccess = await saveStudentAccess(accessToken, child.id, {
        username,
        pin,
        is_active: true,
      });
      setStudentAccessByChildId(prev => ({ ...prev, [child.id]: studentAccess }));
      onChildrenChanged([...children, child], child.id);
      setAdding(false);
      setNewStudentUsername('');
      setNewStudentPin('');
      setMessage(`${child.name} was added with student login access.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not add child profile.');
    } finally {
      setSaving(false);
    }
  }

  async function save(values: ChildProfileFormValues) {
    if (!editingChild) return;
    setSaving(true);
    setError('');
    try {
      const updated = await updateChild(accessToken, editingChild.id, { ...values, status: editingChild.status });
      onChildrenChanged(children.map(child => child.id === updated.id ? updated : child), selectedChildId);
      setEditingChildId(null);
      setMessage(`${updated.name} was updated.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not update child profile.');
    } finally {
      setSaving(false);
    }
  }

  function startAddChild() {
    setAdding(true);
    setEditingChildId(null);
    setNewStudentUsername('');
    setNewStudentPin('');
    setMessage('');
    setError('');
    window.setTimeout(() => {
      document.getElementById('child-profile-form-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  }

  function selectChild(childId: string) {
    onSelectChild(childId);
    setAdding(false);
  }

  function editChild(childId: string) {
    selectChild(childId);
    setEditingChildId(childId);
  }

  function openBillingForChild(childId: string) {
    onSelectChild(childId);
    sessionStorage.setItem(BILLING_TARGET_CHILD_KEY, childId);
    onOpenBilling();
  }

  const selectedAccess = selectedChild ? childAccessById[selectedChild.id] : undefined;
  const selectedStudentAccess = selectedChild ? studentAccessByChildId[selectedChild.id] : null;
  const selectedStudentUsername = selectedStudentAccess?.child_id === selectedChild?.id
    ? selectedStudentAccess.username
    : '';

  return <div className="page-stack manage-children-redesign">
    <SectionHeader
      eyebrow="Parent Controls"
      title="Manage child profiles"
      desc="View each child's profile, learning settings, and subscription status. Sensitive identity details are locked after setup."
    />
    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="manage-profile-layout">
      <section className="form-card child-roster-panel">
        <div className="section-row">
          <h3>Children</h3>
        </div>
        <div className="child-roster-list">
          {children.map(child => {
            const access = childAccessById[child.id];
            const accessState = childAccessState(access);
            return <article key={child.id} className={`child-roster-card${selectedChild?.id === child.id ? ' selected' : ''}`}>
              <div className="child-roster-main">
                <div className="child-roster-avatar" aria-hidden="true">{child.name.charAt(0).toUpperCase()}</div>
                <div>
                  <h4>{child.name}</h4>
                  <p>{child.grade_level} · {formatSubjects(child.subjects)}</p>
                  <span className={`child-status-pill ${child.status === 'inactive' ? 'paused' : 'active'}`}>{child.status === 'inactive' ? 'Profile Paused' : 'Profile Active'}</span>
                </div>
              </div>
              <div className="child-roster-subscription">
                <span className={`access-summary ${accessState.kind}`}>{accessState.label}</span>
                <span>{accessState.detail}</span>
              </div>
              <div className="child-roster-actions">
                <button className="secondary-button compact outline" onClick={() => selectChild(child.id)}><Eye /> View Details</button>
                <button className="secondary-button compact outline" onClick={() => editChild(child.id)}><SlidersHorizontal /> Edit Learning Settings</button>
                {accessState.needsBilling
                  ? <button className="primary-button compact-action" onClick={() => openBillingForChild(child.id)}><CreditCard /> Subscribe Now</button>
                  : <button className="secondary-button compact outline" onClick={() => editChild(child.id)}><UsersRound /> Manage Login</button>}
              </div>
              <p className="identity-lock-note"><Lock /> Name / DOB locked after setup</p>
            </article>;
          })}
          {!children.length && <p className="muted-copy">No child profiles yet.</p>}
        </div>
        <div className="profile-action-row">
          <button className="secondary-button" onClick={startAddChild}><PlusCircle /> Add Child</button>
          <button className="secondary-button outline" onClick={onOpenBilling}><CreditCard /> Pay for All Children</button>
        </div>
      </section>

      <section className="form-card selected-child-panel">
        <div className="section-row">
          <h3>Selected Child Details</h3>
          <span className="locked-detail-badge"><Lock /> Identity details are locked after setup.</span>
        </div>
        {selectedChild ? <>
          <div className="selected-child-details">
            <DetailRow icon={<User />} label="Name" value={`${selectedChild.name} (Locked)`} locked />
            <DetailRow icon={<CalendarDays />} label="Date of Birth" value={selectedChild.date_of_birth ? 'Locked' : 'Locked'} locked />
            <DetailRow icon={<User />} label="Username" value={selectedStudentUsername || 'Not created yet'} />
            <DetailRow icon={<KeyRound />} label="PIN" value="****" action={<button className="link-button inline-link" onClick={() => editChild(selectedChild.id)}>Reset PIN</button>} />
            <DetailRow icon={<GraduationCap />} label="Grade" value={selectedChild.grade_level} />
            <DetailRow icon={<BookOpen />} label="Subjects" value={formatSubjects(selectedChild.subjects)} />
            <DetailRow icon={<SlidersHorizontal />} label="Learning Settings" value="Editable" action={<button className="link-button inline-link" onClick={() => editChild(selectedChild.id)}>Edit</button>} />
            <DetailRow icon={<CreditCard />} label="Subscription Status" value={childAccessState(selectedAccess).label} emphasis={childAccessState(selectedAccess).needsBilling ? 'warning' : 'success'} />
          </div>
          <p className="selected-child-note"><Pencil /> Learning settings, grade, subjects, and student login can be updated. Identity details remain locked.</p>
        </> : <p className="muted-copy">Select or add a child to view profile details.</p>}
      </section>
    </div>

    {(adding || editingChild) && <section className="form-card manage-edit-panel" id="child-profile-form-panel">
      <h3>{editingChild ? `Edit ${editingChild.name}` : 'Add child profile'}</h3>
      <ChildProfileForm
        key={editingChild ? editingChild.id : 'new-child'}
        child={editingChild}
        lockedAfterSetup={Boolean(editingChild)}
        submitLabel={editingChild ? 'Save Child' : 'Add Child and Login Access'}
        saving={saving}
        onSubmit={editingChild ? save : add}
        onCancel={() => { setAdding(false); setEditingChildId(null); }}
        extraFields={adding ? <StudentAccessCreateFields
          username={newStudentUsername}
          pin={newStudentPin}
          onUsernameChange={setNewStudentUsername}
          onPinChange={setNewStudentPin}
        /> : undefined}
      />
      {editingChild && <StudentAccessForm accessToken={accessToken} child={editingChild} />}
    </section>}
  </div>;
}

function DetailRow({
  icon,
  label,
  value,
  action,
  locked = false,
  emphasis = '',
}: {
  icon: ReactNode;
  label: string;
  value: string;
  action?: ReactNode;
  locked?: boolean;
  emphasis?: 'success' | 'warning' | '';
}) {
  return <div className="selected-child-detail-row">
    <span className="detail-icon">{icon}</span>
    <span>{label}</span>
    <strong className={emphasis}>{value}</strong>
    {action || (locked ? <Lock className="detail-lock" /> : <span />)}
  </div>;
}

export function StudentAccessCreateFields({
  username,
  pin,
  onUsernameChange,
  onPinChange,
}: {
  username: string;
  pin: string;
  onUsernameChange: (value: string) => void;
  onPinChange: (value: string) => void;
}) {
  return <div className="student-access-panel create-student-access">
    <div>
      <h3>Student login access</h3>
      <p className="muted-copy">Create a Username and PIN now so this child can log in without email.</p>
    </div>
    <label>Username
      <input value={username} onChange={event => onUsernameChange(event.target.value.toLowerCase())} placeholder="aliysa" />
    </label>
    <label>PIN
      <input type="password" value={pin} onChange={event => onPinChange(event.target.value)} placeholder="Create a simple PIN" />
    </label>
  </div>;
}

function formatSubjects(subjects: ChildSubject[]): string {
  return subjects.map(subject => subject === 'ELA' ? 'Reading' : subject).join(', ');
}

function childAccessState(access?: ChildAccess) {
  if (!access) {
    return {
      kind: 'billing-required',
      label: 'Billing Required',
      detail: 'No active subscription yet',
      needsBilling: true,
    };
  }
  if (access.cancel_at_period_end) {
    return {
      kind: 'paused',
      label: 'Pauses After Period',
      detail: access.current_period_ends_at ? `Access pauses ${formatDate(access.current_period_ends_at)}` : 'Pause scheduled',
      needsBilling: false,
    };
  }
  if (access.access_status === 'active') {
    return {
      kind: 'active',
      label: 'Subscription: Active',
      detail: `${access.plan_name || 'Plan active'}${access.current_period_ends_at ? ` · Renews ${formatDate(access.current_period_ends_at)}` : ''}`,
      needsBilling: false,
    };
  }
  if (access.access_status === 'trial') {
    return {
      kind: 'trial',
      label: 'Trial Active',
      detail: access.trial_ends_at ? `Trial ends ${formatDate(access.trial_ends_at)}` : 'Trial period active',
      needsBilling: false,
    };
  }
  if (access.access_status === 'past_due') {
    return {
      kind: 'billing-required',
      label: 'Payment Needed',
      detail: 'Billing needs attention',
      needsBilling: true,
    };
  }
  return {
    kind: 'billing-required',
    label: 'Billing Required',
    detail: 'Access locked until billing is completed',
    needsBilling: true,
  };
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'soon';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}
