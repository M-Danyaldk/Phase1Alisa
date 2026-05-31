import { useState } from 'react';

export function LoginForm({ onSubmit, onSignup, onForgotPassword, notice = '' }: { onSubmit: (email: string, password: string) => Promise<void>; onSignup: () => void; onForgotPassword: () => void; notice?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !password) {
      setError('Email and password are required.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await onSubmit(normalizedEmail, password);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Welcome Back</span>
      <h2>Log in to continue</h2>
      <p>Welcome to MsAlisia — log in to continue.</p>
    </div>
    <div className="auth-form">
      <label>Email Address<input type="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit(); }} /></label>
      {notice && <p className="success-note">{notice}</p>}
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
      <button className="link-button" onClick={onForgotPassword} type="button">Forgot password?</button>
      <button className="link-button" onClick={onSignup} type="button">Create a new account</button>
    </div>
  </div>;
}
