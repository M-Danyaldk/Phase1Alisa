import { ReactNode, useMemo, useState } from 'react';
import { gradeLevelOptions, isLaunchGradeLevel, launchSubjects, subjectLabel } from '../../constants';
import { ChildProfile, ChildProfileFormValues, ChildSubject } from '../../types/childProfile';

const subjects = launchSubjects as ChildSubject[];

const defaultValues: ChildProfileFormValues = {
  name: '',
  grade_level: 'Grade 4',
  date_of_birth: '',
  subjects: ['Math', 'ELA', 'Writing'],
  learning_goals: '',
  difficulty_level: '',
  parent_notes: '',
  parental_consent_accepted: false,
};

function getAge(dateOfBirth: string): number | null {
  if (!dateOfBirth) return null;
  const birthDate = new Date(`${dateOfBirth}T00:00:00`);
  if (Number.isNaN(birthDate.getTime())) return null;
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const birthdayPassed = today.getMonth() > birthDate.getMonth() || (today.getMonth() === birthDate.getMonth() && today.getDate() >= birthDate.getDate());
  if (!birthdayPassed) age -= 1;
  return age;
}

function valuesFromChild(child?: ChildProfile | null): ChildProfileFormValues {
  if (!child) return defaultValues;
  return {
    name: child.name,
    grade_level: isLaunchGradeLevel(child.grade_level) ? child.grade_level : defaultValues.grade_level,
    date_of_birth: child.date_of_birth || '',
    subjects: child.subjects,
    learning_goals: child.learning_goals || '',
    difficulty_level: child.difficulty_level || '',
    parent_notes: child.parent_notes || '',
    parental_consent_accepted: child.parental_consent_accepted,
  };
}

export function ChildProfileForm({
  child,
  submitLabel,
  saving,
  onSubmit,
  onCancel,
  extraFields,
}: {
  child?: ChildProfile | null;
  submitLabel: string;
  saving: boolean;
  onSubmit: (values: ChildProfileFormValues) => Promise<void> | void;
  onCancel?: () => void;
  extraFields?: ReactNode;
}) {
  const [values, setValues] = useState<ChildProfileFormValues>(() => valuesFromChild(child));
  const [error, setError] = useState('');
  const age = useMemo(() => getAge(values.date_of_birth), [values.date_of_birth]);
  const needsConsent = age !== null && age < 13;

  function toggleSubject(subject: ChildSubject) {
    setValues(prev => {
      const nextSubjects = prev.subjects.includes(subject) ? prev.subjects.filter(item => item !== subject) : [...prev.subjects, subject];
      return { ...prev, subjects: nextSubjects };
    });
  }

  async function submit() {
    if (!values.name.trim()) {
      setError('Child name or nickname is required.');
      return;
    }
    if (!values.subjects.length) {
      setError('Select at least one subject.');
      return;
    }
    if (needsConsent && !values.parental_consent_accepted) {
      setError('Please confirm parental consent for this child profile.');
      return;
    }
    setError('');
    await onSubmit(values);
  }

  return <div className="child-form">
    <label>Child name
      <input value={values.name} onChange={event => setValues(prev => ({ ...prev, name: event.target.value }))} />
    </label>
    <label>Grade level
      <select value={values.grade_level} onChange={event => setValues(prev => ({ ...prev, grade_level: event.target.value }))}>
        {gradeLevelOptions.map(grade => <option key={grade}>{grade}</option>)}
      </select>
    </label>
    <label>Date of birth
      <input type="date" value={values.date_of_birth} onChange={event => setValues(prev => ({ ...prev, date_of_birth: event.target.value }))} />
    </label>
    <div className="field-group">
      <strong>Subjects</strong>
      <div className="subject-checks">
        {subjects.map(subject => <label key={subject} className="check-row">
          <input type="checkbox" checked={values.subjects.includes(subject)} onChange={() => toggleSubject(subject)} />
          <span>{subjectLabel(subject)}</span>
        </label>)}
      </div>
    </div>
    <label>Learning goals
      <textarea value={values.learning_goals} onChange={event => setValues(prev => ({ ...prev, learning_goals: event.target.value }))} placeholder="Example: Build confidence with fractions." />
    </label>
    <label>Current difficulty level
      <input value={values.difficulty_level} onChange={event => setValues(prev => ({ ...prev, difficulty_level: event.target.value }))} placeholder="Optional" />
    </label>
    <label>Parent notes
      <textarea value={values.parent_notes} onChange={event => setValues(prev => ({ ...prev, parent_notes: event.target.value }))} placeholder="Anything Ms Alisia should know later." />
    </label>
    {needsConsent && <label className="check-row consent-row">
      <input type="checkbox" checked={values.parental_consent_accepted} onChange={event => setValues(prev => ({ ...prev, parental_consent_accepted: event.target.checked }))} />
      <span>I confirm I am this child&apos;s parent or guardian and consent to creating this learning profile.</span>
    </label>}
    {extraFields}
    {error && <p className="error-note">{error}</p>}
    <div className="form-actions">
      {onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>}
      <button type="button" className="primary-button" onClick={submit} disabled={saving}>{saving ? 'Saving...' : submitLabel}</button>
    </div>
  </div>;
}
