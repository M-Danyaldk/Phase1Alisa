import { useState } from 'react';

export function ResetPasswordForm({
  onSubmit,
  onBack,
}: {
  onSubmit: (password: string, confirmPassword: string) => Promise<void>;
  onBack: () => void;
}) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!password) {
      setError('New password is required.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Confirm password must match password.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await onSubmit(password, confirmPassword);
    } catch {
      setError('Could not reset password. Please check your code and try again.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>New Password</span>
      <h2>Create a new password</h2>
      <p>Choose a new password for your parent account.</p>
    </div>
    <div className="auth-form">
      <label>New Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} /></label>
      <label>Confirm Password<input type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submit(); }} /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Resetting...' : 'Reset Password'}</button>
      <button className="link-button" onClick={onBack} type="button">Back to login</button>
    </div>
  </div>;
}
