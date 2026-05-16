import { useEffect, useState } from 'react';
import { Brain, ShieldCheck, Users } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { ADMIN_TOKEN, apiGet } from '../lib/api';
import { AdminOverview } from '../types';

export function AdminView() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!ADMIN_TOKEN) {
        setError('Admin access token is missing in the frontend environment.');
        setLoading(false);
        return;
      }
      try {
        const data = await apiGet<AdminOverview>('/api/admin/overview', { 'x-admin-token': ADMIN_TOKEN });
        if (!cancelled) {
          setOverview(data);
          setError('');
        }
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError.message : 'Could not load admin overview.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

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
  </div>;
}
