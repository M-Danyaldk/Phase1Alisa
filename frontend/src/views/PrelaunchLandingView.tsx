import { FormEvent, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { BookOpenText, CalendarCheck, ChartNoAxesColumnIncreasing, Check, CircleDollarSign, HeartHandshake, LockKeyhole, Mail, ShieldCheck, Sparkles, UserPlus, WandSparkles } from 'lucide-react';
import { submitDataDeletionRequest } from '../lib/api/dataDeletion';
import { joinWaitlist } from '../lib/api/waitlist';

type ComplianceType = 'privacy' | 'terms' | 'ai-disclosure' | 'data-deletion' | 'support';

function validEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function PrelaunchLandingView({ onNavigate }: { onNavigate?: (path: string) => void }) {
  const [waitlistEmail, setWaitlistEmail] = useState('');
  const [waitlistLoading, setWaitlistLoading] = useState(false);
  const [waitlistMessage, setWaitlistMessage] = useState('');
  const [waitlistError, setWaitlistError] = useState('');

  function go(path: string) {
    if (onNavigate) onNavigate(path);
    else window.location.assign(path);
  }

  async function submitWaitlist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = waitlistEmail.trim().toLowerCase();
    if (!validEmail(normalizedEmail)) {
      setWaitlistError('Please enter a valid email address.');
      setWaitlistMessage('');
      return;
    }
    setWaitlistLoading(true);
    setWaitlistError('');
    setWaitlistMessage('');
    try {
      const response = await joinWaitlist({ email: normalizedEmail });
      setWaitlistMessage(response.message || "You're on the waitlist. Access is scheduled to open on June 15.");
      setWaitlistEmail('');
    } catch {
      setWaitlistError('We could not join the waitlist right now. Please try again.');
    } finally {
      setWaitlistLoading(false);
    }
  }

  return <main className="prelaunch-page">
    <header className="prelaunch-header">
      <button className="prelaunch-brand" type="button" onClick={() => go('/')} aria-label="MsAlisia home">
        <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        <span>MsAlisia</span>
      </button>
      <nav className="prelaunch-nav" aria-label="Landing navigation">
        <a href="#how-it-works">See How It Works</a>
        <a className="prelaunch-nav-cta" href="/signup">Start Free 7-Day Trial</a>
      </nav>
    </header>

    <section className="prelaunch-hero" aria-labelledby="prelaunch-title">
      <div className="prelaunch-copy">
        <h1 id="prelaunch-title">“We tried 4 tutors in 2 weeks. They were expensive, unreliable, and our child was still struggling.”</h1>
        <p className="prelaunch-subheadline">“So we built Ms. Alisia — a patient, brilliant AI tutor available every day, for less than the cost of a few tutoring sessions a month. Named after a real mom who needed real help. Built from real frustration.”</p>
        <p>Your child gets personalized learning that adapts to how they think. You get weekly progress reports and peace of mind — without the scheduling, the cancellations, or the hourly bills.</p>
        <div className="prelaunch-cta-row">
          <a className="primary-button" href="/signup">Start Free 7-Day Trial</a>
          <a className="secondary-button" href="#how-it-works">See How It Works</a>
        </div>
        <p className="prelaunch-hero-note">No credit card required. Every family starts with a free 7-day trial. Cancel anytime.</p>
        <p className="prelaunch-proof">“Designed by an educator and a real parent — because every child deserves a brilliant tutor, and every parent deserves a break.”</p>
        <form className="landing-waitlist-form" onSubmit={submitWaitlist}>
          <div>
            <Mail aria-hidden="true" />
            <strong>Join the waitlist</strong>
            <span>Enter your email and we will keep you updated.</span>
          </div>
          <label className="sr-only" htmlFor="waitlist-email">Email address</label>
          <input id="waitlist-email" type="email" inputMode="email" autoComplete="email" value={waitlistEmail} onChange={event => setWaitlistEmail(event.target.value)} placeholder="Email address" disabled={waitlistLoading} required />
          <button className="secondary-button" type="submit" disabled={waitlistLoading}>{waitlistLoading ? 'Joining...' : 'Join Waitlist'}</button>
          {waitlistMessage && <p className="landing-waitlist-message success">{waitlistMessage}</p>}
          {waitlistError && <p className="landing-waitlist-message error">{waitlistError}</p>}
        </form>
      </div>

      <div className="prelaunch-visual" aria-label="A happy child learning at a screen">
        <img src="/landing-hero.png" alt="A happy child engaged at a screen" />
      </div>
    </section>

    <section className="landing-section" id="value" aria-label="Value proposition">
      <div className="landing-feature-grid four">
        <LandingFeature icon={<CircleDollarSign />} title="Affordable" text="For less than the cost of a few tutoring sessions, your child gets a full month of personalized, on-demand learning. Available every single day." />
        <LandingFeature icon={<CalendarCheck />} title="Always there" text="Ms. Alisia never cancels, never runs late, and never has a bad day. Homework help at 9pm. Test prep on Sunday morning. Always ready." />
        <LandingFeature icon={<WandSparkles />} title="Adapts to your child" text="Ms. Alisia learns how your child thinks, adjusts to their level, and builds on what they already know — every session, every time." />
        <LandingFeature icon={<ChartNoAxesColumnIncreasing />} title="Parents stay informed" text="Weekly progress reports delivered straight to you. You see everything without sitting beside every lesson. Peace of mind, not more work." />
      </div>
    </section>

    <section className="landing-section landing-split" id="how-it-works">
      <div className="landing-section-heading">
        <h2>How It Works</h2>
      </div>
      <div className="landing-steps">
        <Step number="1" icon={<UserPlus />} text="Create your free account — takes less than 2 minutes." />
        <Step number="2" icon={<BookOpenText />} text="Set up your child’s profile — grade, subjects, and learning goals." />
        <Step number="3" icon={<Sparkles />} text="Your child logs in and starts learning — Ms. Alisia takes it from there." />
      </div>
    </section>

    <section className="landing-section landing-origin">
      <div className="landing-origin-copy">
        <h2>Ms. Alisia is named after a real mom.</h2>
        <p>It started with a conversation between a grandmother, her daughter Alisia, and a friend who was exhausted. Four tutors in two weeks. Cancellations. No-shows. One fell asleep. The bills kept coming and the child was still struggling. They knew this wasn’t just one family’s problem. So a grandmother and her daughter built the tutor they wished existed. Patient. Brilliant. Always available. Never cancels. Ms. Alisia is real because the frustration was real — and every parent dealing with it deserves better.</p>
      </div>
    </section>

    <section className="landing-section landing-subjects">
      <p>Math, Reading, and Writing for Grades 3–6.</p>
      <p>Expanding to K–12 soon.</p>
    </section>

    <section className="landing-section" id="pricing">
      <div className="landing-section-heading">
        <h2>Simple, transparent pricing. No surprises.</h2>
      </div>
      <div className="landing-pricing-grid">
        <PricingCard title="Chat Plan" price="$129/month or $1,419/year — includes 1 month free" />
        <PricingCard title="Voice Plan" price="$159/month or $1,749/year — includes 1 month free" />
      </div>
      <p className="landing-inline-note">Family discount: 5% off for 2 or more children automatically applied at checkout.</p>
      <p className="landing-inline-note">Every new family starts with a free 7-day trial. No credit card required.</p>
    </section>

    <section className="landing-section landing-trust">
      <div className="landing-section-heading">
        <h2>Built around your child’s safety and your peace of mind.</h2>
      </div>
      <ul className="landing-safety-list">
        <li><ShieldCheck aria-hidden="true" /><span>Child-safe tutoring — age-appropriate content only, always.</span></li>
        <li><HeartHandshake aria-hidden="true" /><span>Parent visibility — weekly reports keep you informed without extra work.</span></li>
        <li><LockKeyhole aria-hidden="true" /><span>Privacy-first — your child’s data is never sold or shared.</span></li>
        <li><Sparkles aria-hidden="true" /><span>AI transparency — Ms. Alisia is an AI tutor, not a human tutor. Full disclosure available on our AI Disclosure page.</span></li>
      </ul>
    </section>

    <section className="landing-section" id="faq">
      <div className="landing-section-heading">
        <h2>FAQ</h2>
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
        <span>·</span>
        <button type="button" onClick={() => go('/terms')}>Terms of Service</button>
        <span>·</span>
        <button type="button" onClick={() => go('/ai-disclosure')}>AI Disclosure</button>
        <span>·</span>
        <button type="button" onClick={() => go('/support')}>Contact</button>
      </div>
      <a href="mailto:francesca@msalisia.com">francesca@msalisia.com</a>
    </footer>
  </main>;
}

export function CompliancePage({ type, onNavigate }: { type: ComplianceType; onNavigate: (path: string) => void }) {
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

function Step({ number, icon, text }: { number: string; icon: ReactNode; text: string }) {
  return <article className="landing-step">
    <span>{number}</span>
    <div>{icon}</div>
    <p>{text}</p>
  </article>;
}

function PricingCard({ title, price }: { title: string; price: string }) {
  return <article className="landing-price-card">
    <Check aria-hidden="true" />
    <h3>{title}</h3>
    <strong>{price}</strong>
  </article>;
}

const faqItems = [
  { question: 'What grades does MsAlisia support?', answer: 'MsAlisia currently supports Grades 3–6 across Math, Reading, and Writing.' },
  { question: 'Is there a free trial?', answer: 'Yes. Every new family starts with a free 7-day trial. No credit card required. The trial begins when your first child enters the classroom for the first time.' },
  { question: 'How does billing work?', answer: 'Choose a monthly or annual plan. Annual plans include one month free. Billing is handled securely through Stripe.' },
  { question: 'Is my child’s information safe?', answer: 'Yes. We never sell or share your child’s data. All information is stored securely and used only to personalize your child’s learning experience.' },
  { question: 'Can I cancel anytime?', answer: 'Yes. You can cancel at any time. Your access continues until the end of your current billing period.' },
  { question: 'How is Ms. Alisia different from other tutoring apps?', answer: 'Ms. Alisia was built by an educator and a real parent who experienced the tutoring struggle firsthand. It adapts to how your child thinks, keeps parents informed, and costs a fraction of private tutoring — with no scheduling, no cancellations, and no bad days.' },
];

const complianceContent: Record<ComplianceType, { eyebrow: string; title: string; sections: { title: string; text: string }[] }> = {
  privacy: {
    eyebrow: 'Privacy Policy',
    title: 'Privacy-first learning support',
    sections: [
      { title: 'What we collect', text: 'MsAlisia may collect parent account data, child profile data, tutoring/session data, assessment activity, homework uploads, and support messages needed to operate the service.' },
      { title: 'Service providers', text: 'Billing is handled by Stripe. Emails are handled by Resend. AI tutoring is powered by Anthropic. Voice responses are powered by OpenAI.' },
      { title: 'Advertising', text: 'We do not sell student data for advertising.' },
      { title: 'Deletion requests', text: 'Parents can request deletion of parent and child data by contacting privacy@msalisia.com.' },
    ],
  },
  terms: {
    eyebrow: 'Terms of Service',
    title: 'Terms of Service',
    sections: [
      { title: 'Use of MsAlisia', text: 'MsAlisia provides AI tutoring support for families. Parents are responsible for creating accounts, setting up child profiles, and managing subscriptions.' },
      { title: 'Billing', text: 'Billing is handled securely through Stripe. You can cancel at any time, and access continues until the end of your current billing period.' },
      { title: 'Contact', text: 'For questions about these terms, contact francesca@msalisia.com.' },
    ],
  },
  'ai-disclosure': {
    eyebrow: 'AI Disclosure',
    title: 'You are interacting with an AI, not a human tutor.',
    sections: [
      { title: 'What MsAlisia is', text: 'MsAlisia is an AI learning assistant designed to provide tutoring support, practice guidance, and parent-visible learning summaries.' },
      { title: 'What MsAlisia is not', text: 'MsAlisia is not a human tutor, therapist, or doctor. Parents should review important learning or wellbeing concerns with qualified professionals.' },
    ],
  },
  'data-deletion': {
    eyebrow: 'Data Deletion',
    title: 'Request deletion of parent or child data',
    sections: [
      { title: 'How to request deletion', text: 'Parents can request deletion by emailing privacy@msalisia.com from the parent account email address.' },
      { title: 'Review process', text: 'We review every deletion request carefully and will confirm once your data has been removed.' },
    ],
  },
  support: {
    eyebrow: 'Support',
    title: 'Contact MsAlisia',
    sections: [
      { title: 'Contact', text: 'For product or account help, email francesca@msalisia.com.' },
      { title: 'Privacy', text: 'For privacy or deletion requests, email privacy@msalisia.com.' },
    ],
  },
};
