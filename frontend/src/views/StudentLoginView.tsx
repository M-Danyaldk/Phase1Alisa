import { useMemo, useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { studentLogin } from '../lib/api/studentAuth';
import { StudentSession } from '../types/studentSession';

const loginMessages = [
  'Your tutor is ready.',
  'Ready when you are!',
  'Time to shine today!',
];

export function StudentLoginView({ onLoggedIn, notice = '' }: { onLoggedIn: (session: StudentSession) => void; notice?: string }) {
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loginMessage] = useState(() => loginMessages[Math.floor(Math.random() * loginMessages.length)]);
  const familyCode = useMemo(() => new URLSearchParams(window.location.search).get('family')?.trim() || '', []);

  async function submit() {
    if (!username.trim() || !pin.trim()) {
      setError('Enter your Username and PIN.');
      return;
    }
    if (!familyCode) {
      setError('Please use your family classroom link to log in.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const session = await studentLogin(familyCode, username, pin);
      onLoggedIn(session);
    } catch (loginError) {
      const message = loginError instanceof Error ? loginError.message : '';
      if (message.includes('family classroom link')) setError(message);
      else setError(message.includes('There is something your parent needs to take care of') ? message : 'That username or PIN didn’t work. Please check it and try again.');
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
      <SectionHeader title="HEY THERE!" desc={loginMessage} />
      <div className="auth-form">
        {!familyCode && <p className="info-note">Please use your family classroom link to log in.</p>}
        <label>Username
          <input value={username} onChange={event => setUsername(event.target.value.toLowerCase())} onKeyDown={event => { if (event.key === 'Enter') submit(); }} />
        </label>
        <label>PIN
          <input type="password" value={pin} onChange={event => setPin(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submit(); }} />
        </label>
        {notice && <p className="success-note">{notice}</p>}
        {error && <p className="error-note">{error}</p>}
        <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Opening...' : "Let's Go!"}</button>
      </div>
    </div>
  </div>;
}
