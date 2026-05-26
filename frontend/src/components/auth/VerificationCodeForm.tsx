import { useState } from 'react';
import { PendingVerification } from '../../types/auth';

export function VerificationCodeForm({
  pending,
  onSubmit,
  onResend,
  onBack
}: {
  pending: PendingVerification;
  onSubmit: (code: string) => Promise<void>;
  onResend: () => Promise<void>;
  onBack: () => void;
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  async function submit() {
    if (!/^\d{6}$/.test(code)) {
      setError('Please enter the 6-digit verification code.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await onSubmit(code);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Invalid code entered. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function resend() {
    setError('');
    setResending(true);
    try {
      await onResend();
    } catch (resendError) {
      setError(resendError instanceof Error ? resendError.message : 'Could not resend code. Please try again.');
    } finally {
      setResending(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Email Verification</span>
      <h2>Enter your 6-digit code</h2>
      <p>We sent a verification code to {pending.email}. Please check your inbox. It expires in {pending.expires_in_minutes} minutes.</p>
      {pending.message && <p>{pending.message}</p>}
    </div>
    <div className="auth-form">
      <label>Verification Code<input inputMode="numeric" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Verifying...' : 'Verify Account'}</button>
      <button className="secondary-button" onClick={resend} disabled={resending}>{resending ? 'Sending...' : 'Resend Code'}</button>
      <button className="link-button" onClick={onBack} type="button">Use a different email</button>
    </div>
  </div>;
}
