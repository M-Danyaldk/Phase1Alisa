import { useState } from 'react';
import { ProblemReportButton } from '../components/ProblemReportButton';
import { SectionHeader } from '../components/SectionHeader';
import { ResultPanel } from '../components/ResultPanel';
import { assessmentQuestions } from '../constants';
import { apiPost } from '../lib/api';
import { ChildAssessmentResult, StudentProfile, Subject } from '../types';

export function AssessmentView({ student, setStudent, childId = '', accessToken = '', studentSession = false }: { student: StudentProfile; setStudent: (student: StudentProfile) => void; childId?: string; accessToken?: string; studentSession?: boolean }) {
  const [subject, setSubject] = useState<Subject>('Math');
  const [answers, setAnswers] = useState<string[]>(['', '', '']);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChildAssessmentResult | null>(null);
  const [error, setError] = useState('');

  async function submit() {
    if (!studentSession) {
      setError('Assessments open from the student classroom. Please log in with a Username and PIN.');
      setResult(null);
      return;
    }
    if (!accessToken || !childId) {
      setError('We could not open this check-in yet. Please log in again.');
      setResult(null);
      return;
    }
    setLoading(true);
    setResult(null);
    setError('');
    try {
      const data = await apiPost<ChildAssessmentResult>('/api/assessments/evaluate', { student, child_id: childId, subject, grade: student.grade, answers, questions: assessmentQuestions[subject] }, { Authorization: `Bearer ${accessToken}` });
      setResult(data);
      setStudent({ ...student });
    } catch (submitError) {
      setError(friendlyAssessmentError(submitError));
    } finally { setLoading(false); }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Assessment center" title="Learning check-in" desc="Complete a short check-in so MsAlisia can choose helpful next steps." />
    <p className="muted-copy ai-disclosure-inline">You are interacting with an AI tutor, not a human tutor.</p>
    <div className="tabs">
      {(['Math', 'ELA', 'Writing'] as Subject[]).map(s => <button key={s} className={subject === s ? 'selected' : ''} onClick={() => { setSubject(s); setAnswers(['', '', '']); setResult(null); setError(''); }}>{s}</button>)}
    </div>
    {!studentSession && <p className="error-note">Assessments are only available from the student classroom.</p>}
    {error && <p className="error-note">{error}</p>}
    <div className="assessment-grid">
      <div className="form-card">
        <h3>{subject} quick check</h3>
        {assessmentQuestions[subject].map((q, idx) => <label key={q}>{q}<textarea value={answers[idx]} onChange={e => setAnswers(answers.map((a, i) => i === idx ? e.target.value : a))} placeholder="Student answer..." /></label>)}
        <button className="primary-button" onClick={submit} disabled={loading || !studentSession}>{loading ? 'Evaluating...' : studentSession ? 'Evaluate Assessment' : 'Login Required'}</button>
        <ProblemReportButton
          accessToken={accessToken}
          childId={childId}
          source="assessment"
          subject={subject}
          studentSession={studentSession}
          messageContext={result?.parent_summary || error || null}
          disabled={!studentSession || !accessToken || !childId}
        />
      </div>
      <ResultPanel result={result} />
    </div>
  </div>;
}

function friendlyAssessmentError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  const lower = message.toLowerCase();
  if (lower.includes('parent') || lower.includes('student session') || lower.includes('another child') || lower.includes('invalid or expired')) {
    return 'Please log in again from the student classroom to start this check-in.';
  }
  if (lower.includes('billing') || lower.includes('paused') || lower.includes('payment') || lower.includes('trial') || lower.includes('parent needs')) {
    return 'There is something your parent needs to take care of before this check-in can start.';
  }
  if (lower.includes('subject')) {
    return 'This check-in is only for Math, ELA, or Writing.';
  }
  return message || 'Ms. Alisia could not finish this check-in right now. Please try again soon.';
}
