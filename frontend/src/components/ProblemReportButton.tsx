import { useState } from 'react';
import { sendProblemReport } from '../lib/api/problemReports';
import { ProblemReportCategory, ProblemReportSource } from '../types/problemReports';
import { Subject } from '../types';

type Props = {
  accessToken: string;
  childId: string;
  source: ProblemReportSource;
  subject?: Subject;
  studentSession?: boolean;
  sessionId?: string | null;
  threadId?: string | null;
  messageId?: string | null;
  messageContext?: string | null;
  disabled?: boolean;
};

const categories: { value: ProblemReportCategory; label: string }[] = [
  { value: 'something_wrong', label: 'Something looks wrong' },
  { value: 'unsafe_or_uncomfortable', label: 'Something felt unsafe or uncomfortable' },
  { value: 'confusing_answer', label: 'The answer was confusing' },
  { value: 'technical_issue', label: 'A button or page did not work' },
  { value: 'other', label: 'Something else' },
];

export function ProblemReportButton({
  accessToken,
  childId,
  source,
  subject,
  studentSession = true,
  sessionId = null,
  threadId = null,
  messageId = null,
  messageContext = null,
  disabled = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ProblemReportCategory>('something_wrong');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function submit() {
    if (!accessToken || !childId) return;
    setSubmitting(true);
    setError('');
    setNotice('');
    try {
      const result = await sendProblemReport(accessToken, {
        reporter_type: studentSession ? 'child' : 'parent',
        child_id: childId,
        source,
        category,
        description,
        subject,
        session_id: sessionId,
        thread_id: threadId,
        message_id: messageId,
        message_context: messageContext,
      }, studentSession);
      setNotice(result.message || 'Thanks — your report has been sent.');
      setDescription('');
      setOpen(false);
    } catch {
      setError('We could not send the report right now. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return <>
    <button type="button" onClick={() => { setOpen(true); setError(''); setNotice(''); }} disabled={disabled || !accessToken || !childId}>Report a Problem</button>
    {notice && <span className="muted-note report-status">{notice}</span>}
    {error && <span className="muted-note report-status error">{error}</span>}
    {open && <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Report a problem">
      <div className="confirm-modal problem-report-modal">
        <span className="modal-eyebrow">Report a Problem</span>
        <h3>Tell us what happened</h3>
        <p>We will review this with care. Do not include private information.</p>
        <label>
          What kind of problem was it?
          <select value={category} onChange={event => setCategory(event.target.value as ProblemReportCategory)} disabled={submitting}>
            {categories.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          What should we know?
          <textarea value={description} onChange={event => setDescription(event.target.value)} maxLength={1000} disabled={submitting} placeholder="Write a short note for the MsAlisia team." />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={() => setOpen(false)} disabled={submitting}>Cancel</button>
          <button type="button" className="primary-button" onClick={submit} disabled={submitting}>{submitting ? 'Sending...' : 'Send Report'}</button>
        </div>
      </div>
    </div>}
  </>;
}
