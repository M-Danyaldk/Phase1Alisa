import { Brain } from 'lucide-react';
import { ChildAssessmentResult } from '../types';

export function ResultPanel({ result }: { result: ChildAssessmentResult | null }) {
  if (!result) return <div className="result-card empty"><Brain /><h3>Check-in result will appear here</h3><p>Ms Alisia will use this to choose a helpful next step.</p></div>;
  const message = result.child_message || result.parent_summary || 'Great job! Ms. Alisia found some fun things to practice with you. Let us get started!';
  return <div className="result-card">
    <span className="badge">{result.subject}</span>
    <h3>{result.score_label || 'Great job'}</h3>
    <p className="parent-summary">{message}</p>
  </div>;
}
