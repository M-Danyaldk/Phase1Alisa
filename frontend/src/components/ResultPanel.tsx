import { AlertCircle, Brain, CheckCircle2, CircleHelp, Sparkles, ThumbsUp, XCircle } from 'lucide-react';
import { subjectLabel } from '../constants';
import { AssessmentQuestionResult, ChildAssessmentResult } from '../types';

export function ResultPanel({
  result,
  onContinueLearning,
  onBackToDashboard,
}: {
  result: ChildAssessmentResult | null;
  onContinueLearning?: (result: ChildAssessmentResult) => void;
  onBackToDashboard?: () => void;
}) {
  if (!result) return <div className="result-card empty"><Brain /><h3>Your results will appear here</h3><p>Ms. Alisia will use this to choose a helpful next step.</p></div>;
  const displaySubject = subjectLabel(result.subject);
  const title = result.celebration_title || 'Great work!';
  const message = result.celebration_message || result.child_message || `You just finished your ${displaySubject} check-in!`;
  const performance = result.performance_label || result.score_label || 'Learning Path Ready';
  const scoreSummary = result.score_summary || `Next focus: ${performance}`;
  const strengths = (result.strengths_for_child?.length ? result.strengths_for_child : result.strengths).slice(0, 5);
  const nextStep = result.next_step_message || result.practice_next || result.recommended_progression[0] || 'Ms. Alisia will help you practice one step at a time.';
  const questionResults = (result.question_results || []).slice().sort((left, right) => left.position - right.position);
  return <div className="result-card assessment-celebration-card">
    <div className="celebration-icon" aria-hidden="true"><Sparkles /></div>
    <span className="badge">{result.badge_label || 'All Done!'}</span>
    <h3>{title}</h3>
    <p className="parent-summary">{message}</p>
    <div className="performance-pill"><ThumbsUp />{scoreSummary}</div>
    <div className="report-mini-card">
      <strong>You just finished your {displaySubject} check-in!</strong>
      <p>{result.encouragement || 'Nice work. Ms. Alisia will choose a helpful next step.'}</p>
    </div>
    <div className="assessment-result-section">
      <h4>Here&apos;s what you did great:</h4>
      <ul>
        {(strengths.length ? strengths : ['You finished the check-in.']).map(item => <li key={item}><CheckCircle2 />{item}</li>)}
      </ul>
    </div>
    {questionResults.length > 0 && <div className="assessment-result-section">
      <h4>Your answers:</h4>
      <div className="assessment-question-results">
        {questionResults.map(item => <QuestionResultRow key={item.question_id || `${item.position}-${item.question}`} item={item} />)}
      </div>
    </div>}
    <div className="assessment-result-section">
      <h4>Up next for you:</h4>
      <p>{nextStep}</p>
    </div>
    <div className="assessment-result-actions">
      {onContinueLearning && <button className="primary-button" type="button" onClick={() => onContinueLearning(result)}>Keep Going!</button>}
      {onBackToDashboard && <button className="secondary-button" type="button" onClick={onBackToDashboard}>Back to Home</button>}
    </div>
  </div>;
}

function QuestionResultRow({ item }: { item: AssessmentQuestionResult }) {
  const status = normalizedStatus(item.status);
  const Icon = statusIcon(status);
  const statusText = statusLabel(status);
  const showExpected = Boolean(item.expected_answer)
    && item.validation_type !== 'writing_rubric'
    && status !== 'needs_review';
  return <div className={`assessment-question-result ${status}`}>
    <div className="assessment-question-result-header">
      <span className="assessment-question-number">Q{item.position}</span>
      <span className="assessment-question-status"><Icon />{statusText}</span>
    </div>
    <p className="assessment-question-text">{item.question}</p>
    <dl className="assessment-answer-lines">
      <div>
        <dt>Your answer</dt>
        <dd>{item.student_answer || 'No answer entered'}</dd>
      </div>
      {showExpected && <div>
        <dt>Answer</dt>
        <dd>{item.expected_answer}</dd>
      </div>}
    </dl>
    {item.child_feedback && <p className="assessment-question-feedback">{item.child_feedback}</p>}
  </div>;
}

function normalizedStatus(status: string): 'correct' | 'incorrect' | 'partially_correct' | 'needs_review' {
  if (status === 'correct') return 'correct';
  if (status === 'incorrect') return 'incorrect';
  if (status === 'partially_correct') return 'partially_correct';
  return 'needs_review';
}

function statusLabel(status: ReturnType<typeof normalizedStatus>): string {
  if (status === 'correct') return 'Correct';
  if (status === 'incorrect') return 'Practice';
  if (status === 'partially_correct') return 'Almost';
  return 'Look Again';
}

function statusIcon(status: ReturnType<typeof normalizedStatus>) {
  if (status === 'correct') return CheckCircle2;
  if (status === 'incorrect') return XCircle;
  if (status === 'partially_correct') return AlertCircle;
  return CircleHelp;
}
