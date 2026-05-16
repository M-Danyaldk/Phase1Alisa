import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { updateCurrentProfile, uploadProfileAvatar } from '../lib/api/auth';
import { ProfileResponse, ProfileUpdateValues } from '../types/auth';

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

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

function formatDateTime(value?: string | null): string {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function initialValues(profile: ProfileResponse): ProfileUpdateValues {
  return {
    full_name: profile.full_name,
    grade_level: profile.grade_level || 'Grade 4',
    date_of_birth: profile.date_of_birth || '2012-01-01',
    parent_guardian_email: profile.parent_guardian_email || ''
  };
}

function validate(values: ProfileUpdateValues, email: string): string {
  if (!values.full_name.trim()) return 'Full name is required.';
  if (!values.grade_level) return 'Student grade level is required.';
  if (!values.date_of_birth) return 'Date of birth is required.';
  const age = getAge(values.date_of_birth);
  if (age === null || age < 0) return 'Please enter a valid date of birth.';
  if (age < 13 && !values.parent_guardian_email.trim()) return 'Parent/Guardian email is required if the student is under 13.';
  if (values.parent_guardian_email && !isValidEmail(values.parent_guardian_email)) return 'Please enter a valid parent or guardian email.';
  if (values.parent_guardian_email.toLowerCase() === email.toLowerCase()) return 'Parent/Guardian email must be different from student email.';
  return '';
}

export function ProfileView({
  accessToken,
  profile,
  onProfileUpdated
}: {
  accessToken: string;
  profile: ProfileResponse;
  onProfileUpdated: (profile: ProfileResponse) => void;
}) {
  const [values, setValues] = useState<ProfileUpdateValues>(() => initialValues(profile));
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function save() {
    const validationError = validate(values, profile.email);
    if (validationError) {
      setError(validationError);
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const updated = await updateCurrentProfile(accessToken, values);
      onProfileUpdated(updated);
      setValues(initialValues(updated));
      setSuccess('Profile updated successfully.');
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not update profile. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  async function uploadAvatar(file: File | undefined) {
    if (!file) return;
    setError('');
    setSuccess('');
    setUploading(true);
    try {
      const updated = await uploadProfileAvatar(accessToken, file);
      onProfileUpdated(updated);
      setSuccess('Profile photo updated successfully.');
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Could not upload profile photo. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  return <div className="page-stack narrow">
    <SectionHeader eyebrow="Profile" title="Your learning profile" desc="Review account details and keep learner information up to date." />
    <div className="form-card profile-form">
      <div className="profile-header-row">
        {profile.avatar_url ? <img className="profile-avatar-image" src={profile.avatar_url} alt={`${profile.full_name} profile`} /> : <div className="avatar">{profile.full_name.slice(0, 1).toUpperCase()}</div>}
        <div>
          <h3>{profile.full_name}</h3>
          <p>{profile.email}</p>
          <label className="upload-button">
            {uploading ? 'Uploading...' : 'Upload Photo'}
            <input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={e => uploadAvatar(e.target.files?.[0])} />
          </label>
        </div>
      </div>
      <label>Full Name<input value={values.full_name} onChange={e => setValues({ ...values, full_name: e.target.value })} /></label>
      <label>Email Address<input value={profile.email} disabled /></label>
      <label>Student Grade Level<select value={values.grade_level} onChange={e => setValues({ ...values, grade_level: e.target.value })}><option value="">Select grade</option><option>Grade 3</option><option>Grade 4</option><option>Grade 5</option><option>Grade 6</option></select></label>
      <label>Date of Birth<input type="date" value={values.date_of_birth} onChange={e => setValues({ ...values, date_of_birth: e.target.value })} /></label>
      <label>Parent/Guardian Email<input type="email" value={values.parent_guardian_email} onChange={e => setValues({ ...values, parent_guardian_email: e.target.value })} /></label>
      <div className="readonly-grid">
        <div><span>Created At</span><strong>{formatDateTime(profile.created_at)}</strong></div>
        <div><span>Updated At</span><strong>{formatDateTime(profile.updated_at)}</strong></div>
      </div>
      {error && <p className="error-note">{error}</p>}
      {success && <p className="success-note">{success}</p>}
      <button className="primary-button" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save Profile'}</button>
    </div>
  </div>;
}
