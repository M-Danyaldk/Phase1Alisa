import { useEffect, useState } from 'react';
import { ProblemReportButton } from '../components/ProblemReportButton';
import { SectionHeader } from '../components/SectionHeader';
import { getStudentHomeworkHistory, homeworkAcceptTypes, uploadStudentHomework } from '../lib/api/homework';
import { ChildView, StudentProfile } from '../types';
import { HomeworkUpload } from '../types/homework';

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

  useEffect(() => {
    if (!accessToken || !childId) return;
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
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The file could not be uploaded right now. Please try again.');
    } finally { setLoading(false); }
  }

  return <div className="page-stack narrow">
    <SectionHeader eyebrow="Homework" title={`${student.name}'s homework helper`} desc="Upload a clear photo or PDF. Ms. Alisia checks what she can see before helping one step at a time." />
    <p className="muted-copy ai-disclosure-inline">You are interacting with an AI tutor, not a human tutor.</p>
    <div className="form-card">
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
      <ProblemReportButton
        accessToken={accessToken}
        childId={childId}
        source="homework"
        studentSession={studentSession}
        messageContext={uploadResult?.ai_validation_summary || message || null}
        disabled={!accessToken || !childId}
      />
    </div>
    <HomeworkHistory uploads={history} loading={historyLoading} />
  </div>;
}

function HomeworkResult({ upload, onStart }: { upload: HomeworkUpload; onStart: () => void }) {
  return <div className={`feedback-box homework-validation ${upload.is_unclear ? 'unclear' : 'clear'}`}>
    <strong>{upload.is_unclear ? 'Please try a clearer upload' : 'Ms. Alisia checked your homework'}</strong>
    <p>{upload.ai_validation_summary || 'Your homework was uploaded. Ms. Alisia will help one step at a time.'}</p>
    {upload.detected_subject && <p>Subject: {upload.detected_subject}</p>}
    {upload.suggested_next_step && <p>Next step: {upload.suggested_next_step}</p>}
    {!upload.is_unclear && <button className="secondary-button compact" onClick={onStart}>Start Homework Tutoring</button>}
  </div>;
}

function HomeworkHistory({ uploads, loading }: { uploads: HomeworkUpload[]; loading: boolean }) {
  return <section className="report-card">
    <div className="section-row">
      <h3>Upload History</h3>
      {loading && <span className="muted-note">Loading...</span>}
    </div>
    {uploads.length ? uploads.slice(0, 6).map(upload => <div className="report-mini-card" key={upload.id || `${upload.file_name}-${upload.created_at}`}>
      <strong>{upload.file_name}</strong>
      <p>{formatDate(upload.created_at) || 'Just now'} · {upload.file_type.toUpperCase()} · {upload.detected_subject || 'Subject pending'}</p>
      <p>{upload.ai_validation_summary || statusLabel(upload.ai_validation_status)}</p>
      {upload.is_unclear && <p className="error-note inline-note">Ms. Alisia needs a clearer photo before tutoring from this upload.</p>}
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
