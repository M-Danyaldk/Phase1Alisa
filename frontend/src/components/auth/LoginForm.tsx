import { FormEvent, useEffect, useRef, useState } from 'react';

export function LoginForm({ onSubmit, onSignup, onForgotPassword, notice = '' }: { onSubmit: (email: string, password: string) => Promise<void>; onSignup: () => void; onForgotPassword: () => void; notice?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);
  const submittingRef = useRef(false);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;
    const formData = new FormData(event.currentTarget);
    const normalizedEmail = String(formData.get('email') || email).trim().toLowerCase();
    const nextPassword = String(formData.get('password') || password);
    if (!normalizedEmail || !nextPassword) {
      setError('Email and password are required.');
      return;
    }
    setError('');
    submittingRef.current = true;
    setLoading(true);
    try {
      await onSubmit(normalizedEmail, nextPassword);
    } catch (submitError) {
      if (mountedRef.current) setError(submitError instanceof Error ? submitError.message : 'Invalid email or password.');
    } finally {
      submittingRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Welcome Back</span>
      <h2>Log in to continue</h2>
    </div>
    <form className="auth-form" onSubmit={submit}>
      <label>Email Address<input name="email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} disabled={loading} /></label>
      <label>Password<input name="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} disabled={loading} /></label>
      {notice && <p className="success-note">{notice}</p>}
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button auth-submit-button" type="submit" disabled={loading} aria-busy={loading}>
        {loading && <span className="button-spinner" aria-hidden="true" />}
        {loading ? 'Signing you in...' : 'Login'}
      </button>
      {loading && <p className="auth-processing-note" role="status">Please wait while we open your dashboard.</p>}
      <button className="link-button" onClick={onForgotPassword} type="button" disabled={loading}>Forgot password?</button>
      <button className="link-button" onClick={onSignup} type="button" disabled={loading}>Create a new account</button>
    </form>
  </div>;
}
