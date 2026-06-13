import { useEffect, useRef, useState } from 'react';
import { ProblemReportButton } from '../components/ProblemReportButton';
import { SectionHeader } from '../components/SectionHeader';
import { ResultPanel } from '../components/ResultPanel';
import { launchSubjects, subjectLabel } from '../constants';
import { apiPost } from '../lib/api';
import { AssessmentSelection, ChildAssessmentResult, StudentProfile, Subject } from '../types';

export function AssessmentView({
  student,
  setStudent,
  childId = '',
  accessToken = '',
  studentSession = false,
  onContinueLearning,
  onBackToDashboard,
}: {
  student: StudentProfile;
  setStudent: (student: StudentProfile) => void;
  childId?: string;
  accessToken?: string;
  studentSession?: boolean;
  onContinueLearning?: (result: ChildAssessmentResult) => void;
  onBackToDashboard?: () => void;
}) {
  const [subject, setSubject] = useState<Subject>('Math');
  const [answers, setAnswers] = useState<string[]>(['', '', '']);
  const [selection, setSelection] = useState<AssessmentSelection | null>(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChildAssessmentResult | null>(null);
  const [error, setError] = useState('');
  const resultRef = useRef<HTMLDivElement | null>(null);
  const questions = selection?.questions.map(question => question.prompt) || [];
  const assessmentComplete = Boolean(result);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError('');
    if (!studentSession || !accessToken || !childId) {
      setSelection(null);
      setAnswers(['', '', '']);
      return () => { cancelled = true; };
    }
    setSelection(null);
    setAnswers([]);
    setLoadingQuestions(true);
    apiPost<AssessmentSelection>('/api/assessments/next', { child_id: childId, subject }, { Authorization: `Bearer ${accessToken}` })
      .then(data => {
        if (cancelled) return;
        setSelection(data);
        setAnswers(data.questions.map(() => ''));
      })
      .catch(() => {
        if (cancelled) return;
        setError('We could not load this check-in yet. Please try again soon.');
        setSelection(null);
        setAnswers(['', '', '']);
      })
      .finally(() => {
        if (!cancelled) setLoadingQuestions(false);
      });
    return () => { cancelled = true; };
  }, [studentSession, accessToken, childId, subject]);

  useEffect(() => {
    if (!result) return;
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, [result]);

  async function submit() {
    if (!studentSession) {
      setError('Quick Check-Ins open from the student classroom. Please log in with a Username and PIN.');
      setResult(null);
      return;
    }
    if (!accessToken || !childId) {
      setError('We could not open this check-in yet. Please log in again.');
      setResult(null);
      return;
    }
    if (!selection || !questions.length) {
      setError('We could not load this check-in yet. Please try again soon.');
      setResult(null);
      return;
    }
    setLoading(true);
    setResult(null);
    setError('');
    try {
      const data = await apiPost<ChildAssessmentResult>('/api/assessments/evaluate', {
        student,
        child_id: childId,
        subject,
        grade: selection.grade,
        answers,
        questions,
        question_ids: selection.question_ids,
        assessment_version: selection.assessment_version,
      }, { Authorization: `Bearer ${accessToken}` });
      setResult(data);
      setStudent({ ...student });
    } catch (submitError) {
      setError(friendlyAssessmentError(submitError));
    } finally { setLoading(false); }
  }

  return <div className="page-stack">
    {studentSession && onBackToDashboard && <div className="student-view-actions">
      <button className="secondary-button compact" type="button" onClick={onBackToDashboard}>Back to Home</button>
    </div>}
    <SectionHeader eyebrow="Check-In" title="Quick Check-In" desc="Answer a few quick questions so I know the best way to help you!" />
    <p className="muted-copy ai-disclosure-inline">Ms. Alisia is an AI tutor - here to help you learn!</p>
    <div className="tabs">
      {launchSubjects.map(s => <button key={s} className={subject === s ? 'selected' : ''} onClick={() => { setSubject(s); setResult(null); setError(''); }}>{subjectLabel(s)}</button>)}
    </div>
    {!studentSession && <p className="error-note">Quick Check-Ins are only available from the student classroom.</p>}
    {error && <p className="error-note">{error}</p>}
    <div className="assessment-grid">
      <div className="form-card">
        <h3>{subjectLabel(subject)} Quick Check-In</h3>
        {loadingQuestions && <p className="muted-copy">Loading check-in...</p>}
        {!loadingQuestions && questions.map((q, idx) => <label key={selection?.questions[idx]?.id || q}>{q}<textarea value={answers[idx] || ''} onChange={e => setAnswers(answers.map((a, i) => i === idx ? e.target.value : a))} placeholder="Type your answer..." disabled={assessmentComplete} /></label>)}
        <button className="primary-button" onClick={submit} disabled={loading || loadingQuestions || !studentSession || assessmentComplete || !questions.length}>{loading ? 'Getting results...' : assessmentComplete ? 'All Done!' : studentSession ? 'Show My Results' : 'Log In First'}</button>
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
      <div ref={resultRef}>
        <ResultPanel result={result} onContinueLearning={onContinueLearning} onBackToDashboard={onBackToDashboard} />
      </div>
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
    return 'This check-in is only for Math, Reading, or Writing.';
  }
  return 'Ms. Alisia could not finish this check-in right now. Please try again soon.';
}
