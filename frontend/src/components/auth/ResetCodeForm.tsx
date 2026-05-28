import { useState } from 'react';

export function ResetCodeForm({
  email,
  message = '',
  onSubmit,
  onBack,
}: {
  email: string;
  message?: string;
  onSubmit: (code: string) => Promise<void>;
  onBack: () => void;
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!/^\d{6}$/.test(code)) {
      setError('Please enter the 6-digit reset code.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await onSubmit(code);
    } catch {
      setError('That reset code is invalid or expired. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Password Reset</span>
      <h2>Enter your reset code</h2>
      <p>Check the inbox for {email}. The reset code expires soon.</p>
      {message && <p>{message}</p>}
    </div>
    <div className="auth-form">
      <label>Reset Code<input inputMode="numeric" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} onKeyDown={event => { if (event.key === 'Enter') submit(); }} /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Verifying...' : 'Verify Code'}</button>
      <button className="link-button" onClick={onBack} type="button">Use a different email</button>
    </div>
  </div>;
}
