import { Brain, CheckCircle2, Sparkles, ThumbsUp } from 'lucide-react';
import { subjectLabel } from '../constants';
import { ChildAssessmentResult } from '../types';

export function ResultPanel({
  result,
  onContinueLearning,
  onBackToDashboard,
}: {
  result: ChildAssessmentResult | null;
  onContinueLearning?: (result: ChildAssessmentResult) => void;
  onBackToDashboard?: () => void;
}) {
  if (!result) return <div className="result-card empty"><Brain /><h3>Check-in result will appear here</h3><p>Ms Alisia will use this to choose a helpful next step.</p></div>;
  const displaySubject = subjectLabel(result.subject);
  const title = result.celebration_title || 'Check-in complete';
  const message = result.celebration_message || result.child_message || `You completed your ${displaySubject} check-in.`;
  const performance = result.performance_label || result.score_label || 'Learning Path Ready';
  const scoreSummary = result.score_summary || `Next focus: ${performance}`;
  const strengths = (result.strengths_for_child?.length ? result.strengths_for_child : result.strengths).slice(0, 2);
  const nextStep = result.next_step_message || result.practice_next || result.recommended_progression[0] || 'Ms. Alisia will help you practice one step at a time.';
  return <div className="result-card assessment-celebration-card">
    <div className="celebration-icon" aria-hidden="true"><Sparkles /></div>
    <span className="badge">{result.badge_label || 'Check-in Complete'}</span>
    <h3>{title}</h3>
    <p className="parent-summary">{message}</p>
    <div className="performance-pill"><ThumbsUp />{scoreSummary}</div>
    <div className="report-mini-card">
      <strong>You completed your {displaySubject} check-in.</strong>
      <p>{result.encouragement || "Glad you completed it. We'll work on this together one step at a time."}</p>
    </div>
    <div className="assessment-result-section">
      <h4>What we noticed:</h4>
      <ul>
        {(strengths.length ? strengths : ['You finished the check-in.']).map(item => <li key={item}><CheckCircle2 />{item}</li>)}
      </ul>
    </div>
    <div className="assessment-result-section">
      <h4>Next step:</h4>
      <p>{nextStep}</p>
    </div>
    <div className="assessment-result-actions">
      {onContinueLearning && <button className="primary-button" type="button" onClick={() => onContinueLearning(result)}>Continue Learning</button>}
      {onBackToDashboard && <button className="secondary-button" type="button" onClick={onBackToDashboard}>Back to Home</button>}
    </div>
  </div>;
}
