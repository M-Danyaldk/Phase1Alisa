import { ReactNode, useEffect, useState } from 'react';
import { gradeLevelOptions, isLaunchGradeLevel, launchSubjects, subjectLabel } from '../../constants';
import { ChildProfile, ChildProfileFormValues, ChildSubject } from '../../types/childProfile';

const subjects = launchSubjects as ChildSubject[];
const difficultyOptions = ['Below Grade Level', 'At Grade Level', 'Above Grade Level'];

const defaultValues: ChildProfileFormValues = {
  name: '',
  grade_level: 'Grade 4',
  date_of_birth: '',
  subjects: ['Math', 'ELA', 'Writing'],
  learning_goals: '',
  difficulty_level: 'At Grade Level',
  parent_notes: '',
  parental_consent_accepted: true,
};

function valuesFromChild(child?: ChildProfile | null): ChildProfileFormValues {
  if (!child) return defaultValues;
  const difficultyLevel = difficultyOptions.includes(child.difficulty_level || '') ? child.difficulty_level || '' : defaultValues.difficulty_level;
  return {
    name: child.name,
    grade_level: isLaunchGradeLevel(child.grade_level) ? child.grade_level : defaultValues.grade_level,
    date_of_birth: child.date_of_birth || '',
    subjects: child.subjects,
    learning_goals: child.learning_goals || '',
    difficulty_level: difficultyLevel,
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
  lockedAfterSetup = false,
}: {
  child?: ChildProfile | null;
  submitLabel: string;
  saving: boolean;
  onSubmit: (values: ChildProfileFormValues) => Promise<void> | void;
  onCancel?: () => void;
  extraFields?: ReactNode;
  lockedAfterSetup?: boolean;
}) {
  const [values, setValues] = useState<ChildProfileFormValues>(() => valuesFromChild(child));
  const [error, setError] = useState('');
  const fixedDetailsLocked = lockedAfterSetup && Boolean(child);

  useEffect(() => {
    setValues(valuesFromChild(child));
    setError('');
  }, [child?.id]);

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
    setError('');
    await onSubmit(values);
  }

  return <div className="child-form">
    {fixedDetailsLocked && <p className="muted-copy locked-profile-note">Name and date of birth are locked after setup. To correct fixed profile details, deactivate this profile and create a new one. You can still update grade level, subjects, and learning settings.</p>}
    <label>Child name
      <input value={values.name} onChange={event => setValues(prev => ({ ...prev, name: event.target.value }))} disabled={fixedDetailsLocked} />
    </label>
    <label>Grade level
      <select value={values.grade_level} onChange={event => setValues(prev => ({ ...prev, grade_level: event.target.value }))}>
        {gradeLevelOptions.map(grade => <option key={grade}>{grade}</option>)}
      </select>
    </label>
    <label>Date of birth
      <input type="date" value={values.date_of_birth} onChange={event => setValues(prev => ({ ...prev, date_of_birth: event.target.value }))} disabled={fixedDetailsLocked} />
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
      <select value={values.difficulty_level} onChange={event => setValues(prev => ({ ...prev, difficulty_level: event.target.value }))}>
        {difficultyOptions.map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
    <label>Parent notes
      <textarea value={values.parent_notes} onChange={event => setValues(prev => ({ ...prev, parent_notes: event.target.value }))} placeholder="Anything Ms. Alisia should know later." />
    </label>
    {extraFields}
    {error && <p className="error-note">{error}</p>}
    <div className="form-actions">
      {onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>}
      <button type="button" className="primary-button" onClick={submit} disabled={saving}>{saving ? 'Saving...' : submitLabel}</button>
    </div>
  </div>;
}
