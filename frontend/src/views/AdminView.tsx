import { useEffect, useState } from 'react';
import { Brain, ShieldCheck, Users } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { apiGet } from '../lib/api';
import { AdminOverview } from '../types';

const ADMIN_SESSION_KEY = 'msalisia-admin-access-token';

export function AdminView() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [token, setToken] = useState(() => sessionStorage.getItem(ADMIN_SESSION_KEY) || '');
  const [tokenInput, setTokenInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const data = await apiGet<AdminOverview>('/api/admin/overview', { 'x-admin-token': token });
        if (!cancelled) {
          setOverview(data);
          setError('');
        }
      } catch (fetchError) {
        if (!cancelled) {
          setOverview(null);
          setError('Admin access is separate and protected. The access code was not accepted.');
          sessionStorage.removeItem(ADMIN_SESSION_KEY);
          setToken('');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [token]);

  function submitToken() {
    const nextToken = tokenInput.trim();
    if (!nextToken) {
      setError('Enter the admin access code to continue.');
      return;
    }
    sessionStorage.setItem(ADMIN_SESSION_KEY, nextToken);
    setToken(nextToken);
    setTokenInput('');
  }

  function clearToken() {
    sessionStorage.removeItem(ADMIN_SESSION_KEY);
    setToken('');
    setOverview(null);
    setError('');
  }

  if (!token) {
    return <div className="page-stack narrow">
      <SectionHeader eyebrow="Admin Access" title="Protected back office" desc="Admin tools are separate from parent and student areas." />
      <section className="form-card admin-access-card">
        <h3>Enter admin access code</h3>
        <p className="muted-copy">Admin access is separate and protected.</p>
        <label>Admin access code
          <input type="password" value={tokenInput} onChange={event => setTokenInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submitToken(); }} />
        </label>
        {error && <p className="error-note">{error}</p>}
        <button className="primary-button" onClick={submitToken}>Open Admin</button>
      </section>
    </div>;
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Admin visibility" title="Simple monitoring for non-technical operators" desc="Admin screens show the important information without requiring technical knowledge." />
    <div className="card-grid three">
      <InfoCard icon={<Users />} title="Recent students" desc={loading ? 'Loading student records...' : `${overview?.students.length || 0} student records visible in the latest admin snapshot.`} />
      <InfoCard icon={<Brain />} title="AI usage" desc={loading ? 'Loading provider activity...' : `${overview?.llm_events.length || 0} recent LLM events and fallback signals are available.`} />
      <InfoCard icon={<ShieldCheck />} title="Assessment history" desc={loading ? 'Loading assessment results...' : `${overview?.assessments.length || 0} recent assessment results are visible for review.`} />
    </div>
    {error && <div className="report-card"><h3>Admin access</h3><p>{error}</p></div>}
    {!error && <div className="admin-grid">
      <div className="report-card">
        <h3>Recent students</h3>
        {loading && <p>Loading recent students...</p>}
        {!loading && !(overview?.students.length) && <p>No student profiles yet.</p>}
        {!loading && !!overview?.students.length && <ul>{overview.students.map(student => <li key={`${student.id ?? student.name}-${student.created_at ?? ''}`}>{student.name} - Grade {student.grade} - Math: {student.math_level} - ELA: {student.ela_level} - Writing: {student.writing_level}</li>)}</ul>}
      </div>
      <div className="report-card">
        <h3>Recent assessments</h3>
        {loading && <p>Loading assessments...</p>}
        {!loading && !(overview?.assessments.length) && <p>No assessment results yet.</p>}
        {!loading && !!overview?.assessments.length && <ul>{overview.assessments.map(assessment => <li key={`${assessment.id ?? assessment.student_name}-${assessment.created_at ?? ''}`}>{assessment.student_name || 'Student'} - {assessment.subject} - {assessment.estimated_level}</li>)}</ul>}
      </div>
      <div className="report-card">
        <h3>Recent AI events</h3>
        {loading && <p>Loading provider events...</p>}
        {!loading && !(overview?.llm_events.length) && <p>No AI events yet.</p>}
        {!loading && !!overview?.llm_events.length && <ul>{overview.llm_events.map(event => <li key={`${event.id ?? event.provider}-${event.created_at ?? ''}`}>{event.provider} - {event.model} - {event.purpose}{event.fallback_used ? ' - fallback used' : ''}</li>)}</ul>}
      </div>
    </div>}
    <div className="report-card"><h3>Launch priorities</h3><ul><li>Assessment engine stability</li><li>Course-aware LLM responses</li><li>Simple parent/student UI</li><li>Basic admin safety and usage visibility</li></ul></div>
    <button className="secondary-button" onClick={clearToken}>Lock Admin</button>
  </div>;
}
