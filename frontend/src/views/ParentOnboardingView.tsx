import { useState } from 'react';
import { ChildProfileForm } from '../components/parent/ChildProfileForm';
import { SectionHeader } from '../components/SectionHeader';
import { createChild } from '../lib/api/children';
import { ChildProfile, ChildProfileFormValues } from '../types/childProfile';

export function ParentOnboardingView({
  accessToken,
  parentName,
  onChildCreated,
  onContinue,
}: {
  accessToken: string;
  parentName: string;
  onChildCreated: (child: ChildProfile) => void;
  onContinue: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [createdCount, setCreatedCount] = useState(0);

  async function submit(values: ChildProfileFormValues) {
    setSaving(true);
    setError('');
    try {
      const child = await createChild(accessToken, values);
      onChildCreated(child);
      setCreatedCount(count => count + 1);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not create child profile.');
    } finally {
      setSaving(false);
    }
  }

  return <div className="page-stack narrow">
    <SectionHeader eyebrow="Parent Setup" title={`Welcome, ${parentName}`} desc="Create a child profile so Ms Alisia can keep learning data, reports, and progress separate for each child." />
    <div className="form-card">
      <h3>{createdCount ? 'Add another child' : 'Create the first child profile'}</h3>
      <p className="muted-copy">Each child gets separate assessments, tutoring history, progress, and reports.</p>
      <ChildProfileForm key={createdCount} submitLabel={createdCount ? 'Add Child' : 'Create Child Profile'} saving={saving} onSubmit={submit} />
      {error && <p className="error-note">{error}</p>}
      {createdCount > 0 && <div className="onboarding-actions">
        <button className="secondary-button" onClick={() => setCreatedCount(count => count)}>Add another child</button>
        <button className="primary-button" onClick={onContinue}>Continue to dashboard</button>
      </div>}
    </div>
  </div>;
}
