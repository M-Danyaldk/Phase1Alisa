import { useState } from 'react';
import { ChildProfileForm } from '../components/parent/ChildProfileForm';
import { SectionHeader } from '../components/SectionHeader';
import { createChild, deactivateChild, updateChild } from '../lib/api/children';
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
  const editingChild = children.find(child => child.id === editingChildId) || null;

  async function add(values: ChildProfileFormValues) {
    setSaving(true);
    setError('');
    try {
      const child = await createChild(accessToken, values);
      onChildrenChanged([...children, child], child.id);
      setAdding(false);
      setMessage(`${child.name} was added.`);
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

  async function deactivate(child: ChildProfile) {
    setSaving(true);
    setError('');
    try {
      await deactivateChild(accessToken, child.id);
      const nextChildren = children.filter(item => item.id !== child.id);
      onChildrenChanged(nextChildren, nextChildren[0]?.id);
      setMessage(`${child.name} was deactivated.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not deactivate child profile.');
    } finally {
      setSaving(false);
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent Controls" title="Manage child profiles" desc="Add, edit, or deactivate child profiles. Learning data stays separated by child." />
    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}
    <div className="manage-children-grid">
      <div className="form-card">
        <div className="section-row">
          <h3>Children</h3>
          <button className="secondary-button compact" onClick={() => { setAdding(true); setEditingChildId(null); }}>Add Child</button>
        </div>
        <div className="child-card-list">
          {children.map(child => <div key={child.id} className="child-profile-card">
            <div>
              <h4>{child.name}</h4>
              <p>{child.grade_level} · {child.subjects.join(', ')}</p>
              <span>{child.status === 'pending_consent' ? 'Pending consent' : 'Active'}</span>
            </div>
            <div className="child-card-actions">
              <button className="secondary-button compact" onClick={() => { setEditingChildId(child.id); setAdding(false); }}>Edit</button>
              <button className="secondary-button compact danger" onClick={() => deactivate(child)} disabled={saving}>Deactivate</button>
            </div>
          </div>)}
          {!children.length && <p className="muted-copy">No child profiles yet.</p>}
        </div>
      </div>
      {(adding || editingChild) && <div className="form-card">
        <h3>{editingChild ? `Edit ${editingChild.name}` : 'Add child profile'}</h3>
        <ChildProfileForm child={editingChild} submitLabel={editingChild ? 'Save Child' : 'Add Child'} saving={saving} onSubmit={editingChild ? save : add} onCancel={() => { setAdding(false); setEditingChildId(null); }} />
      </div>}
    </div>
  </div>;
}
