import { FormEvent, useState } from 'react';

export function LoginForm({ onSubmit, onSignup, onForgotPassword, notice = '' }: { onSubmit: (email: string, password: string) => Promise<void>; onSignup: () => void; onForgotPassword: () => void; notice?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const normalizedEmail = String(formData.get('email') || email).trim().toLowerCase();
    const nextPassword = String(formData.get('password') || password);
    if (!normalizedEmail || !nextPassword) {
      setError('Email and password are required.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await onSubmit(normalizedEmail, nextPassword);
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
    </div>
    <form className="auth-form" onSubmit={submit}>
      <label>Email Address<input name="email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Password<input name="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
      {notice && <p className="success-note">{notice}</p>}
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" type="submit" disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
      <button className="link-button" onClick={onForgotPassword} type="button">Forgot password?</button>
      <button className="link-button" onClick={onSignup} type="button">Create a new account</button>
    </form>
  </div>;
}
