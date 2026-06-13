import { useEffect, useRef, useState } from 'react';
import { ProblemReportButton } from '../components/ProblemReportButton';
import { SectionHeader } from '../components/SectionHeader';
import { apiPost } from '../lib/api';
import { getStudentHomeworkHistory, homeworkAcceptTypes, uploadStudentHomework } from '../lib/api/homework';
import { ChatMessage, ChildView, StudentProfile, Subject, TopicSource, TutoringState } from '../types';
import { HomeworkUpload } from '../types/homework';

const initialTutoringState: TutoringState = {
  active_problem: '',
  current_step: '',
  attempt_count: 0,
  answer_revealed: false,
  mode: 'homework',
  status: 'idle',
  memory_note: '',
};

export function HomeworkView({
  student,
  accessToken = '',
  childId = '',
  studentSession = false,
  setView,
}: {
  student: StudentProfile;
  accessToken?: string;
  childId?: string;
  studentSession?: boolean;
  setView?: (view: ChildView) => void;
}) {
  const [fileName, setFileName] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<HomeworkUpload | null>(null);
  const [history, setHistory] = useState<HomeworkUpload[]>([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [followUpInput, setFollowUpInput] = useState('');
  const [followUpMessages, setFollowUpMessages] = useState<ChatMessage[]>([]);
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const [followUpError, setFollowUpError] = useState('');
  const [tutoringState, setTutoringState] = useState<TutoringState>(initialTutoringState);
  const activeUploadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!accessToken || !childId) return;
    setUploadResult(null);
    setSelectedFile(null);
    setFileName('');
    setFollowUpInput('');
    setFollowUpMessages([]);
    setFollowUpError('');
    setTutoringState(initialTutoringState);
    setHistoryLoading(true);
    getStudentHomeworkHistory(accessToken, childId, studentSession)
      .then(data => setHistory(data.uploads || []))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [accessToken, childId, studentSession]);

  async function analyze() {
    if (!selectedFile) {
      setMessage('Pick a homework photo or PDF first, then Ms. Alisia can look before tutoring starts.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const data = await uploadStudentHomework(accessToken, childId, selectedFile, studentSession);
      setUploadResult(data);
      setHistory(items => [data, ...items.filter(item => item.id !== data.id)]);
      setSelectedFile(null);
      setFileName('');
      setFollowUpMessages(homeworkContextMessages(data));
      setFollowUpInput('');
      setFollowUpError('');
      setTutoringState(initialTutoringState);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The file could not be uploaded right now. Please try again.');
    } finally { setLoading(false); }
  }

  function openPreviousUpload(upload: HomeworkUpload) {
    setUploadResult(upload);
    setSelectedFile(null);
    setFileName('');
    setMessage('');
    setFollowUpMessages(homeworkContextMessages(upload));
    setFollowUpInput('');
    setFollowUpError('');
    setTutoringState(initialTutoringState);
    window.setTimeout(() => activeUploadRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }

  async function sendFollowUp() {
    const text = followUpInput.trim();
    if (!text || !uploadResult) return;
    const subject = subjectFromUpload(uploadResult);
    const topic = topicFromUpload(uploadResult);
    const userMessage: ChatMessage = { role: 'student', content: text, subject };
    const nextMessages = [...followUpMessages, userMessage];
    setFollowUpMessages(nextMessages);
    setFollowUpInput('');
    setFollowUpError('');
    setFollowUpLoading(true);
    try {
      const headers = accessToken ? { Authorization: `Bearer ${accessToken}`, ...(studentSession ? {} : { 'x-access-mode': 'child' }) } : undefined;
      const data = await apiPost<{
        reply: string;
        provider: string;
        tutoring_state: TutoringState;
        resolved_topic?: string | null;
        topic_source?: TopicSource | null;
      }>('/api/chat', {
        student,
        child_id: childId || undefined,
        subject,
        topic,
        topic_source: 'manual',
        message: text,
        history: nextMessages.slice(-5),
        tutoring_state: tutoringState,
      }, headers);
      setTutoringState(data.tutoring_state);
      setFollowUpMessages(current => [...current, { role: 'msalisia', content: data.reply, provider: data.provider, subject }]);
    } catch (error) {
      setFollowUpError(childFriendlyFollowUpError(error));
    } finally {
      setFollowUpLoading(false);
    }
  }

  return <div className="page-stack narrow">
    {studentSession && setView && <div className="student-view-actions">
      <button className="secondary-button compact" type="button" onClick={() => setView('home')}>Back to Home</button>
    </div>}
    <SectionHeader eyebrow="Homework" title={`${student.name}'s homework helper`} desc="Upload a clear photo or PDF. Ms. Alisia checks what she can see before helping one step at a time." />
    <p className="muted-copy ai-disclosure-inline">Ms. Alisia is an AI tutor - here to help you learn!</p>
    <div className="form-card" ref={activeUploadRef}>
      <div className="field-group">
        <strong>Homework photo or file</strong>
        <label className="file-upload-button">Take a Photo or Upload
          <input type="file" accept={homeworkAcceptTypes()} capture="environment" onChange={e => {
            const file = e.target.files?.[0] || null;
            setSelectedFile(file);
            setFileName(file?.name || '');
            setUploadResult(null);
            setMessage('');
          }} />
        </label>
        <p className="muted-copy">JPG, PNG, HEIC, HEIF, and PDF are supported.</p>
      </div>
      {fileName && <p className="success-note">Selected file: {fileName}</p>}
      <button className="primary-button" onClick={analyze} disabled={loading || !childId || !accessToken}>{loading ? 'Uploading...' : 'Take a Photo or Upload'}</button>
      {message && <p className="error-note">{message}</p>}
      {uploadResult && <HomeworkResult upload={uploadResult} onStart={() => setView?.('learn')} />}
      {uploadResult && <HomeworkFollowUp
        messages={followUpMessages}
        input={followUpInput}
        loading={followUpLoading}
        error={followUpError}
        disabled={!accessToken || !childId || followUpLoading}
        onInput={setFollowUpInput}
        onSend={sendFollowUp}
      />}
      <ProblemReportButton
        accessToken={accessToken}
        childId={childId}
        source="homework"
        studentSession={studentSession}
        messageContext={uploadResult?.ai_validation_summary || message || null}
        disabled={!accessToken || !childId}
      />
    </div>
    <HomeworkHistory
      uploads={history}
      loading={historyLoading}
      activeUploadId={uploadResult?.id || ''}
      onOpenUpload={openPreviousUpload}
    />
  </div>;
}

function HomeworkResult({ upload, onStart }: { upload: HomeworkUpload; onStart: () => void }) {
  return <div className={`feedback-box homework-validation ${upload.is_unclear ? 'unclear' : 'clear'}`}>
    <strong>{upload.is_unclear ? 'Please try a clearer upload' : 'Ms. Alisia checked your homework'}</strong>
    <p>{upload.ai_validation_summary || 'Your homework was uploaded. Ms. Alisia will help one step at a time.'}</p>
    {upload.detected_subject && <p>Subject: {upload.detected_subject}</p>}
    {upload.suggested_next_step && <p>Up next: {upload.suggested_next_step}</p>}
    {!upload.is_unclear && <button className="secondary-button compact" onClick={onStart}>Start Homework Tutoring</button>}
  </div>;
}

function HomeworkFollowUp({
  messages,
  input,
  loading,
  error,
  disabled,
  onInput,
  onSend,
}: {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  error: string;
  disabled: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
}) {
  return <section className="homework-follow-up">
    <div>
      <strong>Let&apos;s work through it together.</strong>
      <p>Ask Ms. Alisia a question about this homework, or type your answer below.</p>
    </div>
    {!!messages.length && <div className="homework-follow-up-messages">
      {messages.map((item, index) => <div key={`${item.role}-${index}`} className={`homework-follow-up-message ${item.role === 'student' ? 'student' : 'assistant'}`}>
        <span>{item.role === 'student' ? 'You' : 'Ms. Alisia'}</span>
        <p>{item.content}</p>
      </div>)}
    </div>}
    <label>Type your answer or question here.
      <textarea
        value={input}
        disabled={disabled}
        onChange={event => onInput(event.target.value)}
        onKeyDown={event => {
          if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') onSend();
        }}
        placeholder="Example: I think the answer is 12, but I am not sure."
      />
    </label>
    <button className="secondary-button compact" type="button" onClick={onSend} disabled={disabled || !input.trim()}>
      {loading ? 'Sending...' : 'Send'}
    </button>
    {error && <p className="error-note">{error}</p>}
  </section>;
}

function homeworkContextMessages(upload: HomeworkUpload): ChatMessage[] {
  const subject = subjectFromUpload(upload);
  const lines = [
    'Ms. Alisia looked at your homework.',
    upload.ai_validation_summary || 'Your homework was uploaded. We can work through it one step at a time.',
    upload.suggested_next_step ? `Up next: ${upload.suggested_next_step}` : '',
  ].filter(Boolean);
  return [{ role: 'msalisia', content: lines.join('\n'), subject }];
}

function subjectFromUpload(upload: HomeworkUpload): Subject {
  if (upload.detected_subject === 'Math' || upload.detected_subject === 'ELA' || upload.detected_subject === 'Writing') return upload.detected_subject;
  return 'Math';
}

function topicFromUpload(upload: HomeworkUpload): string {
  if (upload.detected_subject === 'ELA') return 'homework reading help';
  if (upload.detected_subject === 'Writing') return 'homework writing help';
  return 'homework help';
}

function childFriendlyFollowUpError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message.toLowerCase().includes('parent needs to take care of')) return message;
  return 'That did not send yet. Please try again in a moment.';
}

function HomeworkHistory({
  uploads,
  loading,
  activeUploadId,
  onOpenUpload,
}: {
  uploads: HomeworkUpload[];
  loading: boolean;
  activeUploadId: string;
  onOpenUpload: (upload: HomeworkUpload) => void;
}) {
  return <section className="report-card">
    <div className="section-row">
      <h3>Upload History</h3>
      {loading && <span className="muted-note">Loading...</span>}
    </div>
    {uploads.length ? uploads.slice(0, 6).map(upload => <div className={`report-mini-card homework-history-card${activeUploadId && upload.id === activeUploadId ? ' active' : ''}`} key={upload.id || `${upload.file_name}-${upload.created_at}`}>
      <strong>{upload.file_name}</strong>
      <p>{formatDate(upload.created_at) || 'Just now'} · {upload.file_type.toUpperCase()} · {upload.detected_subject || 'Subject pending'}</p>
      <p>{upload.ai_validation_summary || statusLabel(upload.ai_validation_status)}</p>
      {upload.is_unclear && <p className="error-note inline-note">Ms. Alisia needs a clearer photo before tutoring from this upload.</p>}
      <button className="secondary-button compact" type="button" onClick={() => onOpenUpload(upload)}>
        {activeUploadId && upload.id === activeUploadId ? 'Currently viewing' : 'Continue with this upload'}
      </button>
    </div>) : <p className="muted-copy">No homework uploads yet.</p>}
  </section>;
}

function statusLabel(status: string): string {
  if (status === 'pending') return 'Validation is pending.';
  if (status === 'failed') return 'Validation could not finish yet.';
  if (status === 'skipped') return 'Uploaded with limited automatic review.';
  return 'Upload saved.';
}

function formatDate(value?: string | null): string {
  if (!value) return '';
  return new Date(value).toLocaleDateString();
}
