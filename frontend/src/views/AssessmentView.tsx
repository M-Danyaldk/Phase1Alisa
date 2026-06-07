import { useEffect, useRef, useState } from 'react';
import { ProblemReportButton } from '../components/ProblemReportButton';
import { SectionHeader } from '../components/SectionHeader';
import { ResultPanel } from '../components/ResultPanel';
import { assessmentQuestions, launchSubjects, subjectLabel } from '../constants';
import { apiPost } from '../lib/api';
import { ChildAssessmentResult, StudentProfile, Subject } from '../types';

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
  const [attemptNumber, setAttemptNumber] = useState(0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChildAssessmentResult | null>(null);
  const [error, setError] = useState('');
  const resultRef = useRef<HTMLDivElement | null>(null);
  const questions = questionsForAttempt(subject, attemptNumber);
  const assessmentComplete = Boolean(result);

  useEffect(() => {
    if (!result) return;
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, [result]);

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
      const data = await apiPost<ChildAssessmentResult>('/api/assessments/evaluate', { student, child_id: childId, subject, grade: student.grade, answers, questions }, { Authorization: `Bearer ${accessToken}` });
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
    <SectionHeader eyebrow="Assessment center" title="Learning check-in" desc="Complete a short check-in so MsAlisia can choose helpful next steps." />
    <p className="muted-copy ai-disclosure-inline">You are interacting with an AI tutor, not a human tutor.</p>
    <div className="tabs">
      {launchSubjects.map(s => <button key={s} className={subject === s ? 'selected' : ''} onClick={() => { setSubject(s); setAnswers(['', '', '']); setAttemptNumber(0); setResult(null); setError(''); }}>{subjectLabel(s)}</button>)}
    </div>
    {!studentSession && <p className="error-note">Assessments are only available from the student classroom.</p>}
    {error && <p className="error-note">{error}</p>}
    <div className="assessment-grid">
      <div className="form-card">
        <h3>{subjectLabel(subject)} quick check</h3>
        {questions.map((q, idx) => <label key={q}>{q}<textarea value={answers[idx]} onChange={e => setAnswers(answers.map((a, i) => i === idx ? e.target.value : a))} placeholder="Student answer..." disabled={assessmentComplete} /></label>)}
        <button className="primary-button" onClick={submit} disabled={loading || !studentSession || assessmentComplete}>{loading ? 'Evaluating...' : assessmentComplete ? 'Assessment Complete' : studentSession ? 'Evaluate Assessment' : 'Login Required'}</button>
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

const assessmentQuestionVariants: Record<Subject, string[][]> = {
  Math: [
    [
      'What is 8 x 6?',
      'Which is larger: 5/6 or 3/4? Explain briefly.',
      'A box has 36 pencils. If 6 pencils go in each cup, how many cups are needed?'
    ],
    [
      'What is 9 x 4?',
      'Put these fractions in order from smallest to largest: 1/2, 1/4, 3/4.',
      'Lena has 56 stickers and shares them equally with 7 friends. How many stickers does each friend get?'
    ]
  ],
  ELA: [
    [
      'Read this sentence: The kitten leaped onto the chair. What does leaped mean?',
      'What detail helps you find the main idea of a paragraph?',
      'Fix this sentence: he doesnt want to go'
    ],
    [
      'Read this sentence: The crowd cheered loudly. What does cheered mean?',
      'What is one clue that helps you understand a character?',
      'Fix this sentence: they was late for school'
    ]
  ],
  Writing: [
    [
      'Write one clear sentence about a place you like.',
      'Write 3 sentences that explain why practice is helpful.',
      'How can you make this sentence stronger: The game was fun?'
    ],
    [
      'Write one clear sentence about something you learned.',
      'Write 3 sentences that explain how to be a good friend.',
      'How can you make this sentence stronger: The lunch was good?'
    ]
  ]
};

function questionsForAttempt(subject: Subject, attemptNumber: number): string[] {
  if (attemptNumber === 0) return assessmentQuestions[subject];
  const variants = assessmentQuestionVariants[subject];
  return variants[(attemptNumber - 1) % variants.length];
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
