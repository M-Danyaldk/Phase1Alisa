import { useEffect, useState } from 'react';
import { getStudentAccess, saveStudentAccess } from '../../lib/api/studentAccess';
import { ChildProfile } from '../../types/childProfile';
import { StudentAccess } from '../../types/studentAccess';

function suggestedUsername(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/^\.+|\.+$/g, '').slice(0, 24);
}

export function StudentAccessForm({
  accessToken,
  child,
}: {
  accessToken: string;
  child: ChildProfile;
}) {
  const [record, setRecord] = useState<StudentAccess | null>(null);
  const [username, setUsername] = useState(() => suggestedUsername(child.name));
  const [pin, setPin] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMessage('');
    setError('');
    setPin('');
    getStudentAccess(accessToken, child.id)
      .then(data => {
        if (cancelled) return;
        setRecord(data);
        setUsername(data?.username || suggestedUsername(child.name));
        setIsActive(data?.is_active ?? true);
      })
      .catch(fetchError => {
        if (cancelled) return;
        setRecord(null);
        setUsername(suggestedUsername(child.name));
        setError(fetchError instanceof Error ? fetchError.message : 'Could not load student access.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [accessToken, child.id, child.name]);

  async function submit() {
    const normalizedUsername = username.trim().toLowerCase();
    if (!normalizedUsername) {
      setError('Username is required.');
      return;
    }
    if (!pin.trim()) {
      setError('PIN is required when saving student access.');
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await saveStudentAccess(accessToken, child.id, {
        username: normalizedUsername,
        pin: pin.trim(),
        is_active: isActive,
      });
      setRecord(saved);
      setUsername(saved.username);
      setPin('');
      setMessage(`Student access saved for ${child.name}.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not save student access.');
    } finally {
      setSaving(false);
    }
  }

  return <div className="student-access-panel">
    <div>
      <h3>Student login access</h3>
      <p className="muted-copy">Create a simple username and PIN your child can use to log in without email.</p>
    </div>
    {loading && <p className="muted-note">Loading student access...</p>}
    {record && <p className="success-note">Current Username: {record.username}</p>}
    <label>Username
      <input value={username} onChange={event => setUsername(event.target.value.toLowerCase())} placeholder="aliysa" />
    </label>
    <label>PIN
      <input type="password" value={pin} onChange={event => setPin(event.target.value)} placeholder={record ? 'Enter a new PIN to reset' : 'Create a simple PIN'} />
    </label>
    <label className="check-row">
      <input type="checkbox" checked={isActive} onChange={event => setIsActive(event.target.checked)} />
      <span>Student login is active</span>
    </label>
    {error && <p className="error-note">{error}</p>}
    {message && <p className="success-note">{message}</p>}
    <button className="primary-button" onClick={submit} disabled={saving || loading}>{saving ? 'Saving...' : record ? 'Update Student Access' : 'Create Student Access'}</button>
  </div>;
}
