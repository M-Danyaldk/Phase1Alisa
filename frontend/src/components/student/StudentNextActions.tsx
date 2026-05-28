import { View } from '../../types';

export function StudentNextActions({
  actions,
  setView,
}: {
  actions: string[];
  setView: (view: View) => void;
}) {
  return <section className="report-card">
    <div className="section-row">
      <h3>Recommended Next Actions</h3>
      <div className="form-actions">
        <button className="secondary-button compact" onClick={() => setView('learn')}>Start Practice</button>
        <button className="primary-button" onClick={() => setView('assessments')}>Start Assessment</button>
      </div>
    </div>
    <ul>
      {actions.map(action => <li key={action}>{action}</li>)}
    </ul>
  </section>;
}
