import { Brain } from 'lucide-react';
import { AssessmentResult } from '../types';

export function ResultPanel({ result }: { result: AssessmentResult | null }) {
  if (!result) return <div className="result-card empty"><Brain /><h3>Assessment result will appear here</h3><p>Ms Alisia will identify strengths, gaps, competency level, and next progression.</p></div>;
  return <div className="result-card">
    <span className="badge">{result.subject}</span>
    <h3>{result.estimated_level}</h3>
    <p className="score-label">{result.score_label}</p>
    <h4>Strengths</h4><ul>{result.strengths.map(x => <li key={x}>{x}</li>)}</ul>
    <h4>Learning gaps</h4><ul>{result.learning_gaps.map(x => <li key={x}>{x}</li>)}</ul>
    <h4>Recommended progression</h4><ul>{result.recommended_progression.map(x => <li key={x}>{x}</li>)}</ul>
    <p className="parent-summary">{result.parent_summary}</p>
  </div>;
}
