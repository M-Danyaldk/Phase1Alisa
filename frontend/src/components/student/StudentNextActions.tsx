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
      <h3>What to try next</h3>
    </div>
    <div className="form-actions">
      <button className="secondary-button compact" type="button" onClick={() => setView('learn')}>Start Learning</button>
      <button className="secondary-button compact" type="button" onClick={() => setView('assessments')}>Quick Check-In</button>
      <button className="secondary-button compact" type="button" onClick={() => setView('homework')}>Homework Help</button>
    </div>
  </section>;
}
