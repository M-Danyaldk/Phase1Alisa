import { FormEvent, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { joinWaitlist } from '../lib/api/waitlist';

const successMessage = 'Thank you - we will be in touch soon!';

function validEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function PrelaunchLandingView({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!validEmail(normalizedEmail)) {
      setError('Please enter a valid email address.');
      setMessage('');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const response = await joinWaitlist(normalizedEmail);
      setMessage(response.message || successMessage);
      setEmail('');
    } catch {
      setError('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return <main className="prelaunch-page">
    <section className="prelaunch-shell" aria-labelledby="prelaunch-title">
      <header className="prelaunch-header">
        <div className="prelaunch-brand">
          <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
          <div>
            <strong>MsAlisia</strong>
            <span>Your child gets a patient, seasoned, brilliant educator - available whenever they need one.</span>
          </div>
        </div>
        <button className="prelaunch-login" type="button" onClick={onLogin}>Login</button>
      </header>

      <div className="prelaunch-content">
        <div className="prelaunch-copy">
          <span className="prelaunch-eyebrow">Launching Soon</span>
          <h1 id="prelaunch-title">Join the MsAlisia early access list.</h1>
          <p>
            Be the first to access MsAlisia - sign up now and receive a free 7-day trial when we launch.
          </p>
          <form className="prelaunch-form" onSubmit={submit}>
            <div className="prelaunch-input-row">
              <input
                aria-label="Email address"
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={event => setEmail(event.target.value)}
                placeholder="Enter your email address"
                disabled={loading}
                required
              />
            </div>
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? 'Joining...' : 'Join Waitlist'}
            </button>
            <p>No payment information required. We'll only email you about launch access.</p>
          </form>
          {message && <p className="prelaunch-success"><CheckCircle2 aria-hidden="true" />{message}</p>}
          {error && <p className="prelaunch-error">{error}</p>}
        </div>

        <aside className="prelaunch-card" aria-label="MsAlisia launch preview">
          <div className="prelaunch-feature-panel">
            <span className="prelaunch-trial-pill">Free 7-Day Trial</span>
            <h2>Built around how your child learns.</h2>
            <p>MsAlisia learns how your child thinks, adapts to their level, and keeps you informed, so you can relax knowing they are in good hands.</p>
            <ul>
              <li>Your child is always taught at the right level, not just their grade</li>
              <li>You get a weekly progress report - without asking for one</li>
              <li>Homework help that actually understands the assignment</li>
              <li>Tell MsAlisia what to focus on - no judgment, ever</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>
  </main>;
}
