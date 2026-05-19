import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { studentLogin } from '../lib/api/studentAuth';
import { StudentSession } from '../types/studentSession';

export function StudentLoginView({ onLoggedIn, onParentLogin }: { onLoggedIn: (session: StudentSession) => void; onParentLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!username.trim() || !pin.trim()) {
      setError('Enter your Student Username and PIN.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const session = await studentLogin(username, pin);
      onLoggedIn(session);
    } catch (loginError) {
      const message = loginError instanceof Error ? loginError.message : '';
      setError(message.includes('learning access is currently paused') ? message : 'Please check the username and PIN, then try again.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-shell">
    <div className="auth-brand">
      <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
      <span>MsAlisia</span>
    </div>
    <div className="auth-panel student-login-panel">
      <SectionHeader eyebrow="Student Login" title="Start learning" desc="Use your Student Username and PIN to open your classroom." />
      <div className="auth-form">
        <label>Student Username
          <input value={username} onChange={event => setUsername(event.target.value.toLowerCase())} onKeyDown={event => { if (event.key === 'Enter') submit(); }} />
        </label>
        <label>PIN or Access Code
          <input type="password" value={pin} onChange={event => setPin(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submit(); }} />
        </label>
        {error && <p className="error-note">{error}</p>}
        <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Opening...' : 'Start Learning'}</button>
        <button className="link-button" type="button" onClick={onParentLogin}>Parent login</button>
      </div>
    </div>
  </div>;
}
