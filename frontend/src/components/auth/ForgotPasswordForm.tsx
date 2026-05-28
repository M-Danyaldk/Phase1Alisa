import { useState } from 'react';

const GENERIC_MESSAGE = 'If an account exists for this email, we sent password reset instructions.';

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function ForgotPasswordForm({
  onSubmit,
  onBack,
}: {
  onSubmit: (email: string) => Promise<void>;
  onBack: () => void;
}) {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !isValidEmail(normalizedEmail)) {
      setError('Please enter a valid email address.');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      await onSubmit(normalizedEmail);
      setMessage(GENERIC_MESSAGE);
    } catch {
      setError('We could not send the reset email. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Password Help</span>
      <h2>Reset your password</h2>
      <p>Enter your parent account email and we will send a short reset code.</p>
    </div>
    <div className="auth-form">
      <label>Email Address<input type="email" value={email} onChange={event => setEmail(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submit(); }} /></label>
      {message && <p className="success-note">{message}</p>}
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Sending...' : 'Send Reset Code'}</button>
      <button className="link-button" onClick={onBack} type="button">Back to login</button>
    </div>
  </div>;
}
