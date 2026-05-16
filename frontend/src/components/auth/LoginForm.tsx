import { useState } from 'react';

export function LoginForm({ onSubmit, onSignup }: { onSubmit: (email: string, password: string) => Promise<void>; onSignup: () => void }) {
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
      <p>Use your verified email and password to open the MsAlisia dashboard.</p>
    </div>
    <div className="auth-form">
      <label>Email Address<input type="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit(); }} /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
      <button className="link-button" onClick={onSignup} type="button">Create a new account</button>
    </div>
  </div>;
}
