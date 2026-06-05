import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { updateCurrentProfile, uploadProfileAvatar } from '../lib/api/auth';
import { ProfileResponse, ProfileUpdateValues } from '../types/auth';

function initialValues(profile: ProfileResponse): ProfileUpdateValues {
  return {
    full_name: profile.full_name,
  };
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
  const isAdminProfile = profile.role === 'admin' || profile.role === 'super_admin';

  async function save() {
    const validationError = !values.full_name.trim() ? 'Full name is required.' : '';
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
    <SectionHeader eyebrow="Profile" title={isAdminProfile ? 'Admin account' : 'Parent account'} desc={isAdminProfile ? 'Review admin account details and profile photo.' : 'Review parent account details and profile photo.'} />
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
      {isAdminProfile && <label>Admin Role<input value={profile.role || 'admin'} disabled /></label>}
      {error && <p className="error-note">{error}</p>}
      {success && <p className="success-note">{success}</p>}
      <button className="primary-button" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save Profile'}</button>
    </div>
  </div>;
}
