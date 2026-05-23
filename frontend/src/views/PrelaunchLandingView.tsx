import { FormEvent, useState } from 'react';
import { ArrowRight, CheckCircle2, Mail, Sparkles } from 'lucide-react';
import { joinWaitlist } from '../lib/api/waitlist';

const successMessage = 'Thank you — we will be in touch soon!';

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
            <span>Your tutor, anytime your child needs help</span>
          </div>
        </div>
        <button className="prelaunch-login" type="button" onClick={onLogin}>Login</button>
      </header>

      <div className="prelaunch-content">
        <div className="prelaunch-copy">
          <span className="prelaunch-eyebrow"><Sparkles /> Pre-launch access</span>
          <h1 id="prelaunch-title">Be the first to access MsAlisia — sign up now and receive a free 7-day trial when we launch</h1>
          <p>
            A warm AI-powered learning companion for guided tutoring, assessments, and parent-supervised progress.
          </p>
          <form className="prelaunch-form" onSubmit={submit}>
            <label>Email address
              <div className="prelaunch-input-row">
                <Mail aria-hidden="true" />
                <input
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  value={email}
                  onChange={event => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  disabled={loading}
                  required
                />
              </div>
            </label>
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? 'Joining...' : <>Join Waitlist <ArrowRight aria-hidden="true" /></>}
            </button>
          </form>
          {message && <p className="prelaunch-success"><CheckCircle2 aria-hidden="true" />{message}</p>}
          {error && <p className="prelaunch-error">{error}</p>}
          <div className="prelaunch-trust">
            <span>No payment required.</span>
            <span>Free 7-day trial when we launch.</span>
          </div>
        </div>

        <aside className="prelaunch-card" aria-label="MsAlisia launch preview">
          <div className="prelaunch-card-icon">A</div>
          <h2>Learning support that meets each child where they are.</h2>
          <ul>
            <li>Guided tutoring for Grades 3-6</li>
            <li>Assessment-informed practice</li>
            <li>Parent-supervised learning progress</li>
          </ul>
        </aside>
      </div>
    </section>
  </main>;
}
