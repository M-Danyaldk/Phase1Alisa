import { FormEvent, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Brain, CheckCircle2, ClipboardList, FileText, Headphones, HeartHandshake, LockKeyhole, Mail, Mic, ShieldCheck, Sparkles, UploadCloud } from 'lucide-react';
import { submitDataDeletionRequest } from '../lib/api/dataDeletion';
import { joinWaitlist } from '../lib/api/waitlist';

const waitlistOpenDate = import.meta.env.VITE_WAITLIST_OPEN_DATE || '2026-06-14';
const waitlistOpenDateLabel = new Date(`${waitlistOpenDate}T00:00:00`).toLocaleDateString(undefined, {
  month: 'long',
  day: 'numeric',
});
const successMessage = `You're on the waitlist. Access is scheduled to open on ${waitlistOpenDateLabel}.`;

function validEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function PrelaunchLandingView({ onLogin, onNavigate }: { onLogin: () => void; onNavigate?: (path: string) => void }) {
  const [parentName, setParentName] = useState('');
  const [email, setEmail] = useState('');
  const [childGrade, setChildGrade] = useState('');
  const [interestNote, setInterestNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const accessOpen = Number.isFinite(new Date(`${waitlistOpenDate}T00:00:00`).getTime())
    && new Date() >= new Date(`${waitlistOpenDate}T00:00:00`);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!parentName.trim()) {
      setError('Please enter your name.');
      setMessage('');
      return;
    }
    if (!validEmail(normalizedEmail)) {
      setError('Please enter a valid email address.');
      setMessage('');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const response = await joinWaitlist({
        parent_name: parentName.trim(),
        email: normalizedEmail,
        child_grade: childGrade.trim() || undefined,
        interest_note: interestNote.trim() || undefined,
      });
      setMessage(response.message || successMessage);
      setParentName('');
      setEmail('');
      setChildGrade('');
      setInterestNote('');
    } catch {
      setError('We could not join the waitlist right now. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  function go(path: string) {
    if (onNavigate) onNavigate(path);
    else window.location.assign(path);
  }

  return <main className="prelaunch-page">
    <header className="prelaunch-header">
      <button className="prelaunch-brand" type="button" onClick={() => go('/')} aria-label="MsAlisia home">
        <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        <span>MsAlisia</span>
      </button>
      <nav className="prelaunch-nav" aria-label="Landing navigation">
        <a href="#features">Features</a>
        <a href="#faq">FAQ</a>
      </nav>
      <button className="prelaunch-login" type="button" onClick={onLogin}>Login</button>
    </header>

    <section className="prelaunch-hero" aria-labelledby="prelaunch-title">
      <div className="prelaunch-copy">
        <span className="prelaunch-eyebrow">{accessOpen ? 'Access is open' : `Controlled launch access opens ${waitlistOpenDateLabel}`}</span>
        <h1 id="prelaunch-title">Best Teacher. Best Mentor. Best Future.</h1>
        <p>MsAlisia is an AI tutor for Grades 3-6 that adapts to your child, supports Math, English Language Arts, and Writing, and keeps parents informed without adding more work to the day.</p>
        <div className="prelaunch-cta-row">
          <a className="primary-button" href={accessOpen ? '/signup' : '#waitlist'}>{accessOpen ? 'Create Parent Account' : 'Join Waitlist'}</a>
          <a className="secondary-button" href="#how-it-works">See How It Works</a>
        </div>
      </div>

      <form className="prelaunch-form" id="waitlist" onSubmit={submit}>
        <h2>{accessOpen ? 'Access is open' : 'Join the waitlist'}</h2>
        <p>{accessOpen ? 'Create your parent account when you are ready to begin.' : `Access is opening carefully on ${waitlistOpenDateLabel} so every family gets a strong start.`}</p>
        <label>Parent name
          <input value={parentName} onChange={event => setParentName(event.target.value)} autoComplete="name" disabled={loading} required />
        </label>
        <label>Email
          <input type="email" inputMode="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" disabled={loading} required />
        </label>
        <label>Child grade <span>Optional</span>
          <input value={childGrade} onChange={event => setChildGrade(event.target.value)} placeholder="Example: Grade 5" disabled={loading} />
        </label>
        <label>Interest note <span>Optional</span>
          <textarea value={interestNote} onChange={event => setInterestNote(event.target.value)} placeholder="Tell us what support would help most." disabled={loading} />
        </label>
        <button className="primary-button" type="submit" disabled={loading}>{loading ? 'Joining...' : 'Join Waitlist'}</button>
        {accessOpen && <button className="secondary-button" type="button" onClick={() => go('/signup')}>Create Parent Account</button>}
        <p className="prelaunch-form-note">No payment information required. {accessOpen ? 'You can also create a parent account now.' : `Access is scheduled to open on ${waitlistOpenDateLabel}.`}</p>
        {message && <p className="prelaunch-success"><CheckCircle2 aria-hidden="true" />{message}</p>}
        {error && <p className="prelaunch-error">{error}</p>}
      </form>
    </section>

    <section className="landing-section" id="features">
      <div className="landing-section-heading">
        <span>Launch features</span>
        <h2>Focused tutoring with parent visibility.</h2>
      </div>
      <div className="landing-feature-grid">
        <LandingFeature icon={<Sparkles />} title="AI tutoring" text="Step-by-step help that adapts to each child's current level." />
        <LandingFeature icon={<ClipboardList />} title="Assessment engine" text="Learning checks help MsAlisia understand strengths and gaps." />
        <LandingFeature icon={<FileText />} title="Parent reports" text="Parents can see progress without needing to sit beside every lesson." />
        <LandingFeature icon={<Mic />} title="Voice learning" text="Voice support is planned for Chat + Audio access." />
        <LandingFeature icon={<Brain />} title="Brain Break" text="Healthy rest reminders support long learning sessions." />
        <LandingFeature icon={<UploadCloud />} title="Homework upload" text="Students can upload work for guided support." />
      </div>
      <p className="landing-inline-note">Launch scope: Grades 3-6, Math, English Language Arts, and Writing. Grades 7-12, Science, and Social Studies are planned post-launch.</p>
    </section>

    <section className="landing-section landing-split" id="how-it-works">
      <div className="landing-section-heading">
        <span>How it works</span>
        <h2>Three simple steps.</h2>
      </div>
      <div className="landing-steps">
        <Step number="1" title="Join the waitlist" text="Tell us where to send access details." />
        <Step number="2" title="Create profiles" text="When access opens, create the parent account and child profile." />
        <Step number="3" title="Start learning" text="Your child logs in separately and learns with Ms. Alisia." />
      </div>
    </section>

    <section className="landing-section landing-trust">
      <div className="landing-section-heading">
        <span>Trust and safety</span>
        <h2>Built for parent-supervised learning.</h2>
      </div>
      <div className="landing-feature-grid">
        <LandingFeature icon={<ShieldCheck />} title="Child-safe tutoring" text="Student-facing guidance stays encouraging and age-aware." />
        <LandingFeature icon={<HeartHandshake />} title="Parent visibility" text="Parents can review progress, reports, and access status." />
        <LandingFeature icon={<LockKeyhole />} title="Privacy-first data handling" text="Child data is not sold for advertising, and parents can request deletion." />
        <LandingFeature icon={<Headphones />} title="AI disclosure" text="MsAlisia is an AI tutor, not a human tutor or clinical evaluator." />
      </div>
      <p className="landing-inline-note">Children see supportive learning messages. Clinical-style scores are kept out of child-facing screens.</p>
    </section>

    <section className="landing-section" id="faq">
      <div className="landing-section-heading">
        <span>FAQ</span>
        <h2>Questions parents ask first.</h2>
      </div>
      <div className="landing-faq-grid">
        {faqItems.map(item => <details key={item.question}>
          <summary>{item.question}</summary>
          <p>{item.answer}</p>
        </details>)}
      </div>
    </section>

    <footer className="prelaunch-footer">
      <strong>MsAlisia</strong>
      <div>
        <button type="button" onClick={() => go('/privacy')}>Privacy Policy</button>
        <button type="button" onClick={() => go('/ai-disclosure')}>AI Disclosure</button>
        <button type="button" onClick={() => go('/data-deletion')}>Data Deletion Request</button>
        <button type="button" onClick={() => go('/support')}>Contact / Support</button>
      </div>
    </footer>
  </main>;
}

export function CompliancePage({ type, onNavigate }: { type: 'privacy' | 'ai-disclosure' | 'data-deletion' | 'support'; onNavigate: (path: string) => void }) {
  const content = useMemo(() => complianceContent[type], [type]);
  return <main className="legal-page">
    <section className="legal-card">
      <button className="secondary-button compact" type="button" onClick={() => onNavigate('/')}>Back to MsAlisia</button>
      <span>{content.eyebrow}</span>
      <h1>{content.title}</h1>
      {content.sections.map(section => <div key={section.title}>
        <h2>{section.title}</h2>
        <p>{section.text}</p>
      </div>)}
      {type === 'data-deletion' && <DataDeletionRequestForm />}
    </section>
  </main>;
}

function DataDeletionRequestForm() {
  const [parentName, setParentName] = useState('');
  const [email, setEmail] = useState('');
  const [childName, setChildName] = useState('');
  const [requestDetails, setRequestDetails] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage('');
    setError('');
    if (!confirmed) {
      setError('Please confirm that this request will be reviewed before deletion.');
      return;
    }
    setLoading(true);
    try {
      const result = await submitDataDeletionRequest({
        parent_name: parentName.trim(),
        email: email.trim().toLowerCase(),
        child_name: childName.trim() || undefined,
        request_details: requestDetails.trim() || undefined,
        confirmation_accepted: confirmed,
      });
      setMessage(result.message || 'Your deletion request has been received. We will review it and contact you if needed.');
      setParentName('');
      setEmail('');
      setChildName('');
      setRequestDetails('');
      setConfirmed(false);
    } catch {
      setError('We could not submit your request right now. Please try again or contact privacy@msalisia.com.');
    } finally {
      setLoading(false);
    }
  }

  return <form className="legal-form" onSubmit={submit}>
    <h2>Submit a deletion request</h2>
    <label>Parent name
      <input value={parentName} onChange={event => setParentName(event.target.value)} autoComplete="name" disabled={loading} required />
    </label>
    <label>Email
      <input type="email" inputMode="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" disabled={loading} required />
    </label>
    <label>Child name <span>Optional</span>
      <input value={childName} onChange={event => setChildName(event.target.value)} disabled={loading} />
    </label>
    <label>Request details <span>Optional</span>
      <textarea value={requestDetails} onChange={event => setRequestDetails(event.target.value)} disabled={loading} placeholder="Tell us what account or child data this request is about." />
    </label>
    <label className="checkbox-row">
      <input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={loading} />
      <span>I understand this request will be reviewed before deletion.</span>
    </label>
    <button className="primary-button" type="submit" disabled={loading}>{loading ? 'Submitting...' : 'Submit Request'}</button>
    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}
  </form>;
}

function LandingFeature({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <article className="landing-feature-card">
    <div>{icon}</div>
    <h3>{title}</h3>
    <p>{text}</p>
  </article>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) {
  return <article className="landing-step">
    <span>{number}</span>
    <h3>{title}</h3>
    <p>{text}</p>
  </article>;
}

const faqItems = [
  { question: 'What grades are supported?', answer: 'MsAlisia launch access is focused on Grades 3-6. Grades 7-12 are prepared for future release.' },
  { question: 'What subjects are available?', answer: 'Launch subjects are Math, English Language Arts, and Writing.' },
  { question: 'How does the waitlist work?', answer: 'Join the waitlist and we will contact you when access is ready for your family.' },
  { question: 'Is MsAlisia an AI tutor?', answer: 'Yes. MsAlisia is an AI tutor, not a human tutor.' },
  { question: 'Can parents see progress?', answer: 'Yes. Parents can view reports, assessment summaries, and child profile progress.' },
  { question: 'How does billing work after launch?', answer: 'Billing is handled securely through Stripe when a family chooses access.' },
  { question: 'What is the difference between Text Plan and Voice Plan?', answer: 'Text Plan supports chat tutoring. Voice Plan adds audio learning features.' },
  { question: 'Is homework upload supported?', answer: 'Yes. Homework upload is part of the planned launch feature set.' },
  { question: 'What happens during Brain Break?', answer: 'Brain Break gives children a positive rest reminder after long tutoring sessions. It supports healthy learning habits.' },
];

const complianceContent = {
  privacy: {
    eyebrow: 'Privacy Policy',
    title: 'Privacy-first learning support',
    sections: [
      { title: 'What we collect', text: 'MsAlisia may collect parent account data, child profile data, tutoring/session data, assessment activity, homework uploads, and support messages needed to operate the service.' },
      { title: 'Service providers', text: 'Billing is handled by Stripe. Emails are handled by Resend. AI tutoring uses configured AI providers through the backend.' },
      { title: 'Advertising', text: 'We do not sell student data for advertising.' },
      { title: 'Deletion requests', text: 'Parents can request deletion of parent and child data by contacting privacy@msalisia.com.' },
    ],
  },
  'ai-disclosure': {
    eyebrow: 'AI Disclosure',
    title: 'You are interacting with an AI, not a human tutor.',
    sections: [
      { title: 'What MsAlisia is', text: 'MsAlisia is an AI learning assistant designed to provide tutoring support, practice guidance, and parent-visible learning summaries.' },
      { title: 'What MsAlisia is not', text: 'MsAlisia is not a human tutor, therapist, doctor, or clinical evaluator. Parents should review important learning or wellbeing concerns with qualified professionals.' },
    ],
  },
  'data-deletion': {
    eyebrow: 'Data Deletion',
    title: 'Request deletion of parent or child data',
    sections: [
      { title: 'How to request deletion', text: 'Parents can request deletion by emailing privacy@msalisia.com from the parent account email address.' },
      { title: 'Review process', text: 'Deletion requests are reviewed and handled according to account, billing, legal, and operational requirements.' },
    ],
  },
  support: {
    eyebrow: 'Support',
    title: 'Contact MsAlisia',
    sections: [
      { title: 'Support', text: 'For product or account help, email support@msalisia.com.' },
      { title: 'Privacy', text: 'For privacy or deletion requests, email privacy@msalisia.com.' },
    ],
  },
};
