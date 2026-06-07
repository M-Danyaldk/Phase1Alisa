import { View } from '../../types';

export function StudentNextActions({
  actions,
  setView,
}: {
  actions: string[];
  setView: (view: View) => void;
}) {
  void actions;

  return <section className="report-card">
    <div className="section-row">
      <h3>Recommended Next Actions</h3>
    </div>
    <div className="form-actions">
      <button className="secondary-button compact" type="button" onClick={() => setView('learn')}>Start Practice</button>
      <button className="secondary-button compact" type="button" onClick={() => setView('assessments')}>Take your assessment</button>
      <button className="secondary-button compact" type="button" onClick={() => setView('homework')}>Upload Homework</button>
    </div>
  </section>;
}
