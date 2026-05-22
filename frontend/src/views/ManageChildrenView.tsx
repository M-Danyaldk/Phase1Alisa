import { useState } from 'react';
import { ConfirmDeactivateChildModal } from '../components/parent/ConfirmDeactivateChildModal';
import { ConfirmReactivateChildModal } from '../components/parent/ConfirmReactivateChildModal';
import { ChildProfileForm } from '../components/parent/ChildProfileForm';
import { StudentAccessForm } from '../components/parent/StudentAccessForm';
import { SectionHeader } from '../components/SectionHeader';
import { saveStudentAccess } from '../lib/api/studentAccess';
import { createChild, deactivateChild, reactivateChild, updateChild } from '../lib/api/children';
import { ChildProfile, ChildProfileFormValues } from '../types/childProfile';

export function ManageChildrenView({
  accessToken,
  children,
  selectedChildId,
  onChildrenChanged,
}: {
  accessToken: string;
  children: ChildProfile[];
  selectedChildId: string;
  onChildrenChanged: (children: ChildProfile[], selectedChildId?: string) => void;
}) {
  const [editingChildId, setEditingChildId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [deactivateTarget, setDeactivateTarget] = useState<ChildProfile | null>(null);
  const [reactivateTarget, setReactivateTarget] = useState<ChildProfile | null>(null);
  const [newStudentUsername, setNewStudentUsername] = useState('');
  const [newStudentPin, setNewStudentPin] = useState('');
  const editingChild = children.find(child => child.id === editingChildId) || null;

  async function add(values: ChildProfileFormValues) {
    const username = newStudentUsername.trim().toLowerCase();
    const pin = newStudentPin.trim();
    if (!username || !pin) {
      setError('Student Username and PIN are required when creating a child profile.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const child = await createChild(accessToken, values);
      await saveStudentAccess(accessToken, child.id, {
        username,
        pin,
        is_active: true,
      });
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

  async function deactivate() {
    if (!deactivateTarget) return;
    setSaving(true);
    setError('');
    try {
      const updated = await deactivateChild(accessToken, deactivateTarget.id);
      onChildrenChanged(children.map(child => child.id === updated.id ? updated : child), selectedChildId);
      if (editingChildId === updated.id) setEditingChildId(null);
      setDeactivateTarget(null);
      setMessage(`${updated.name}'s learning access is paused. Their history has not been deleted.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not deactivate child profile.');
    } finally {
      setSaving(false);
    }
  }

  async function reactivate() {
    if (!reactivateTarget) return;
    setSaving(true);
    setError('');
    try {
      const updated = await reactivateChild(accessToken, reactivateTarget.id);
      onChildrenChanged(children.map(child => child.id === updated.id ? updated : child), updated.id);
      setReactivateTarget(null);
      setMessage(`${updated.name}'s learning access is active again. Their history was not changed.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not reactivate child profile.');
    } finally {
      setSaving(false);
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent Controls" title="Manage child profiles" desc="Add, edit, or deactivate child profiles. Learning data stays separated by child." />
    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}
    {deactivateTarget && <ConfirmDeactivateChildModal child={deactivateTarget} saving={saving} onCancel={() => setDeactivateTarget(null)} onConfirm={deactivate} />}
    {reactivateTarget && <ConfirmReactivateChildModal child={reactivateTarget} saving={saving} onCancel={() => setReactivateTarget(null)} onConfirm={reactivate} />}
    <div className="manage-children-grid">
      <div className="form-card">
        <div className="section-row">
          <h3>Children</h3>
          <button className="secondary-button compact" onClick={() => { setAdding(true); setEditingChildId(null); setNewStudentUsername(''); setNewStudentPin(''); }}>Add Child</button>
        </div>
        <div className="child-card-list">
          {children.map(child => <div key={child.id} className="child-profile-card">
            <div>
              <h4>{child.name}</h4>
              <p>{child.grade_level} · {child.subjects.join(', ')}</p>
              <span className={`child-status ${child.status}`}>{statusLabel(child.status)}</span>
            </div>
            <div className="child-card-actions">
              <button className="secondary-button compact" onClick={() => { setEditingChildId(child.id); setAdding(false); }}>Edit</button>
              {child.status === 'inactive'
                ? <button className="secondary-button compact" onClick={() => setReactivateTarget(child)} disabled={saving}>Reactivate</button>
                : <button className="secondary-button compact muted-danger" onClick={() => setDeactivateTarget(child)} disabled={saving}>Deactivate</button>}
            </div>
          </div>)}
          {!children.length && <p className="muted-copy">No child profiles yet.</p>}
        </div>
      </div>
      {(adding || editingChild) && <div className="form-card">
        <h3>{editingChild ? `Edit ${editingChild.name}` : 'Add child profile'}</h3>
        <ChildProfileForm
          child={editingChild}
          submitLabel={editingChild ? 'Save Child' : 'Add Child and Student Login'}
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
      </div>}
    </div>
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
      <p className="muted-copy">Create a Student Username and PIN now so this child can log in without email.</p>
    </div>
    <label>Student Username
      <input value={username} onChange={event => onUsernameChange(event.target.value.toLowerCase())} placeholder="aliysa" />
    </label>
    <label>PIN or Access Code
      <input type="password" value={pin} onChange={event => onPinChange(event.target.value)} placeholder="Create a simple PIN" />
    </label>
  </div>;
}

function statusLabel(status: ChildProfile['status']): string {
  if (status === 'pending_consent') return 'Pending consent';
  if (status === 'inactive') return 'Paused';
  return 'Active';
}
