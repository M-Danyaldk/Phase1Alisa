import { useEffect, useState } from 'react';
import { BarChart3, BookOpen, CheckCircle2, ClipboardCheck, Clock, FileUp, PenTool, Target, TrendingUp } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { apiPost } from '../lib/api';
import { homeworkAcceptTypes, uploadParentHomework } from '../lib/api/homework';
import { getFilteredChildReport, getWeeklyEmailPreview } from '../lib/api/reports';
import { getWorkingLevelOverrides, resetWorkingLevelOverride, setWorkingLevelOverride } from '../lib/api/workingLevelOverrides';
import { AssessmentSummary, ChildReport, LearningMemorySummary, SubjectProgress, TutorSessionSummary, WeeklyReportEmailPreview } from '../types/childReport';
import { ChatMessage, StudentProfile, Subject, TopicSource, TutoringState, View } from '../types';
import { HomeworkUpload } from '../types/homework';
import { WorkingLevelOverrideItem, WorkingLevelOverridesResponse } from '../types/workingLevelOverrides';
import { launchGrades, subjectLabel } from '../constants';

type Period = 'week' | 'month' | 'all';
type SubjectFilter = 'All' | Subject;

const initialHomeworkTutoringState: TutoringState = {
  active_problem: '',
  current_step: '',
  attempt_count: 0,
  answer_revealed: false,
  mode: 'homework',
  status: 'idle',
  memory_note: '',
};

export function ReportsView({
  student,
  accessToken = '',
  childId = '',
  setView,
}: {
  student: StudentProfile;
  accessToken?: string;
  childId?: string;
  setView?: (view: View) => void;
}) {
  const [period, setPeriod] = useState<Period>('week');
  const [subjectFilter, setSubjectFilter] = useState<SubjectFilter>('All');
  const [report, setReport] = useState<ChildReport | null>(null);
  const [emailPreview, setEmailPreview] = useState<WeeklyReportEmailPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [parentFile, setParentFile] = useState<File | null>(null);
  const [parentFileName, setParentFileName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const [workingLevels, setWorkingLevels] = useState<WorkingLevelOverridesResponse | null>(null);
  const [workingLevelSelections, setWorkingLevelSelections] = useState<Record<string, string>>({});
  const [workingLevelMessage, setWorkingLevelMessage] = useState('');
  const [workingLevelSaving, setWorkingLevelSaving] = useState('');
  const [parentHomeworkUpload, setParentHomeworkUpload] = useState<HomeworkUpload | null>(null);
  const [parentFollowUpInput, setParentFollowUpInput] = useState('');
  const [parentFollowUpMessages, setParentFollowUpMessages] = useState<ChatMessage[]>([]);
  const [parentFollowUpLoading, setParentFollowUpLoading] = useState(false);
  const [parentFollowUpError, setParentFollowUpError] = useState('');
  const [parentTutoringState, setParentTutoringState] = useState<TutoringState>(initialHomeworkTutoringState);

  useEffect(() => {
    if (!accessToken || !childId) {
      setReport(null);
      setEmailPreview(null);
      setWorkingLevels(null);
      setWorkingLevelSelections({});
      setParentFile(null);
      setParentFileName('');
      setUploadMessage('');
      setWorkingLevelMessage('');
      resetParentHomeworkFollowUp();
      return;
    }
    let cancelled = false;
    setReport(null);
    setEmailPreview(null);
    setWorkingLevels(null);
    setWorkingLevelSelections({});
    setParentFile(null);
    setParentFileName('');
    setUploadMessage('');
    setWorkingLevelMessage('');
    resetParentHomeworkFollowUp();
    setLoading(true);
    setError('');
    getFilteredChildReport(accessToken, childId, period, subjectFilter)
      .then(data => { if (!cancelled) setReport(data); })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load this child report.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    getWeeklyEmailPreview(accessToken, childId)
      .then(data => { if (!cancelled) setEmailPreview(data); })
      .catch(() => { if (!cancelled) setEmailPreview(null); });
    getWorkingLevelOverrides(accessToken, childId)
      .then(records => {
        if (!cancelled) {
          setWorkingLevels(records);
          setWorkingLevelSelections(Object.fromEntries(records.subjects.map(item => [item.subject, item.effective_working_level])));
        }
      })
      .catch(() => { if (!cancelled) setWorkingLevels(null); });
    return () => { cancelled = true; };
  }, [accessToken, childId, period, subjectFilter]);

  const subjectProgress = report?.subject_progress || fallbackSubjectProgress(student);
  const childName = report?.child_name || student.name;
  const accessBlocked = isBillingAccessMessage(error);

  async function uploadForChild() {
    if (!parentFile) {
      setUploadMessage('Select a homework photo or PDF first.');
      return;
    }
    setUploading(true);
    setUploadMessage('');
    try {
      const upload = await uploadParentHomework(accessToken, childId, parentFile);
      setReport(current => current ? { ...current, homework_uploads: [upload, ...(current.homework_uploads || []).filter(item => item.id !== upload.id)] } : current);
      setParentFile(null);
      setParentFileName('');
      setUploadMessage(upload.is_unclear ? 'Uploaded. Ms. Alisia needs a clearer file before tutoring from it.' : 'Uploaded. Ms. Alisia added a validation summary.');
      setParentHomeworkUpload(upload);
      setParentFollowUpMessages(homeworkContextMessages(upload));
      setParentFollowUpInput('');
      setParentFollowUpError('');
      setParentTutoringState(initialHomeworkTutoringState);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'Could not upload homework right now.');
    } finally {
      setUploading(false);
    }
  }

  async function saveWorkingLevel(subject: Subject) {
    if (!accessToken || !childId) return;
    const nextLevel = workingLevelSelections[subject];
    if (!nextLevel) return;
    setWorkingLevelSaving(subject);
    setWorkingLevelMessage('');
    try {
      const records = await setWorkingLevelOverride(accessToken, childId, subject, nextLevel);
      setWorkingLevels(records);
      setWorkingLevelSelections(Object.fromEntries(records.subjects.map(item => [item.subject, item.effective_working_level])));
      setWorkingLevelMessage(`${subjectLabel(subject)} working level saved.`);
      getFilteredChildReport(accessToken, childId, period, subjectFilter).then(setReport).catch(() => undefined);
    } catch (error) {
      const detail = error instanceof Error ? error.message : '';
      setWorkingLevelMessage(detail ? `Could not save the working level right now. ${detail}` : 'Could not save the working level right now.');
    } finally {
      setWorkingLevelSaving('');
    }
  }

  function resetParentHomeworkFollowUp() {
    setParentHomeworkUpload(null);
    setParentFollowUpInput('');
    setParentFollowUpMessages([]);
    setParentFollowUpError('');
    setParentTutoringState(initialHomeworkTutoringState);
  }

  async function sendParentFollowUp() {
    const text = parentFollowUpInput.trim();
    if (!text || !parentHomeworkUpload) return;
    const subject = subjectFromUpload(parentHomeworkUpload);
    const topic = topicFromUpload(parentHomeworkUpload);
    const userMessage: ChatMessage = { role: 'student', content: text, subject };
    const nextMessages = [...parentFollowUpMessages, userMessage];
    setParentFollowUpMessages(nextMessages);
    setParentFollowUpInput('');
    setParentFollowUpError('');
    setParentFollowUpLoading(true);
    try {
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
        tutoring_state: parentTutoringState,
      }, { Authorization: `Bearer ${accessToken}`, 'x-access-mode': 'child' });
      setParentTutoringState(data.tutoring_state);
      setParentFollowUpMessages(current => [...current, { role: 'msalisia', content: data.reply, provider: data.provider, subject }]);
    } catch (error) {
      setParentFollowUpError(parentFriendlyFollowUpError(error));
    } finally {
      setParentFollowUpLoading(false);
    }
  }

  async function resetWorkingLevel(subject: Subject) {
    if (!accessToken || !childId) return;
    setWorkingLevelSaving(subject);
    setWorkingLevelMessage('');
    try {
      const records = await resetWorkingLevelOverride(accessToken, childId, subject);
      setWorkingLevels(records);
      setWorkingLevelSelections(Object.fromEntries(records.subjects.map(item => [item.subject, item.effective_working_level])));
      setWorkingLevelMessage(`${subjectLabel(subject)} working level reset to the assessment or enrolled grade.`);
      getFilteredChildReport(accessToken, childId, period, subjectFilter).then(setReport).catch(() => undefined);
    } catch (error) {
      const detail = error instanceof Error ? error.message : '';
      setWorkingLevelMessage(detail ? `Could not reset the working level right now. ${detail}` : 'Could not reset the working level right now.');
    } finally {
      setWorkingLevelSaving('');
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Parent reports" title={`${childName}'s learning report`} desc="A clear, child-specific view of progress, strengths, areas needing review, and recommended next steps." />

    <div className="report-toolbar report-filters">
        <small>{report?.grade_level || `Grade ${student.grade}`} · Last updated {formatDate(report?.last_updated_at) || 'not yet'}</small>
      <label>Period
        <select value={period} onChange={event => setPeriod(event.target.value as Period)}>
          <option value="week">This week</option>
          <option value="month">This month</option>
          <option value="all">All time</option>
        </select>
      </label>
      <label>Subject
        <select value={subjectFilter} onChange={event => setSubjectFilter(event.target.value as SubjectFilter)}>
          <option value="All">All subjects</option>
          <option value="Math">Math</option>
          <option value="ELA">Reading</option>
          <option value="Writing">Writing</option>
        </select>
      </label>
    </div>

    {error && <p className="error-note">{error}</p>}
    {!childId && <p className="error-note">Select or create a child profile to view reports.</p>}

    {accessBlocked ? <section className="report-card access-message">
      <h3>Choose a plan for {childName}</h3>
      <p>This child's learning report will open after an active trial or paid subscription is available.</p>
    </section> : loading ? <ReportLoadingState childName={childName} /> : <>
    <div className="card-grid three">
      <InfoCard icon={<Target />} title="Current Level" desc={report?.current_learning_level || 'No assessment completed yet.'} />
      <InfoCard icon={<TrendingUp />} title="Weekly Progress" desc={report?.weekly_progress || 'No learning activity recorded yet.'} />
      <InfoCard icon={<Clock />} title="Study Time" desc={report?.time_spent_learning || 'No tracked learning time yet.'} />
    </div>

    <div className="card-grid three">
      <InfoCard icon={<CheckCircle2 />} title="Lessons Completed" desc={`${report?.lessons_completed || 0} saved lesson thread(s) — each one belongs to this child only.`} />
      <InfoCard icon={<BarChart3 />} title="Questions Practiced" desc={`${report?.questions_practiced || 0} student practice message(s) recorded in this period.`} />
      <InfoCard icon={<ClipboardCheck />} title="Latest Assessment" desc={report?.assessment_status || 'No assessment completed yet.'} />
    </div>

    <div className="report-card">
      <h3>Overall Summary</h3>
      <p>{report?.overall_summary || `${student.name} should begin with a short assessment-led practice session.`}</p>
    </div>

    <ParentPersonalizationSection report={report} childName={childName} />

    <SubjectProgressSection progress={subjectProgress} />

    <WorkingLevelOverrideSection
      records={workingLevels?.subjects || []}
      selections={workingLevelSelections}
      saving={workingLevelSaving}
      message={workingLevelMessage}
      disabled={!accessToken || !childId}
      onSelect={(subject, level) => setWorkingLevelSelections(current => ({ ...current, [subject]: level }))}
      onSave={saveWorkingLevel}
      onReset={resetWorkingLevel}
    />

    <ParentHomeworkUpload
      childName={childName}
      fileName={parentFileName}
      uploading={uploading}
      message={uploadMessage}
      disabled={!accessToken || !childId}
      onFile={file => {
        setParentFile(file);
        setParentFileName(file?.name || '');
        setUploadMessage('');
      }}
      onUpload={uploadForChild}
    />

    {parentHomeworkUpload && <ParentHomeworkFollowUp
      messages={parentFollowUpMessages}
      input={parentFollowUpInput}
      loading={parentFollowUpLoading}
      error={parentFollowUpError}
      disabled={!accessToken || !childId || parentFollowUpLoading}
      onInput={setParentFollowUpInput}
      onSend={sendParentFollowUp}
    />}

    <HomeworkReportSection uploads={report?.homework_uploads || []} />

    <div className="report-grid">
      <ReportList title="Strengths" items={report?.strengths || ["Complete an assessment to identify this child's strong areas."]} />
      <ReportList title="Growth Areas" items={report?.weak_areas || ['Start with a quick assessment to find helpful review topics.']} />
      <ReportList title="Recommended Next Steps" items={report?.recommended_next_steps || ['Run a quick assessment.', 'Practice one skill at a time with Ms Alisia.']} />
    </div>

    <AssessmentSection assessments={report?.recent_assessments || []} />
    <LearningMemorySection memories={report?.recent_learning_memory || []} />
    <SessionHistorySection sessions={report?.recent_tutor_sessions || []} />

    <div className="report-grid">
      <div className="report-card">
        <h3>Brain Break & Healthy Learning</h3>
        <p>{report?.brain_break_summary || 'Ms. Alisia supports healthy learning with positive rest reminders during long tutoring sessions.'}</p>
      </div>
      <div className="report-card">
        <h3>Weekly Email Report</h3>
        {emailPreview?.email_note && <p>{emailPreview.email_note}</p>}
        {emailPreview && <div className="report-mini-card">
          <strong>{emailPreview.subject_line}</strong>
          <p>{emailPreview.greeting}</p>
          <p>{emailPreview.summary}</p>
          <p>Generated {formatDate(emailPreview.generated_at)}</p>
        </div>}
      </div>
      <div className="report-card">
        <h3>Student-Safe View</h3>
        <p>Children can later see their own progress and achievements, but billing, sibling reports, grade changes, and parent controls should remain parent-only.</p>
      </div>
    </div>
    </>}
  </div>;
}

function ReportLoadingState({ childName }: { childName: string }) {
  return <section className="report-loading-card" aria-live="polite">
    <div className="report-loading-copy">
      <span className="report-loading-spinner" aria-hidden="true" />
      <div>
        <h3>Loading {childName}&apos;s report...</h3>
        <p>Preparing this child&apos;s progress, homework, and assessment details.</p>
      </div>
    </div>
    <div className="report-loading-grid">
      {['Current Level', 'Weekly Progress', 'Study Time'].map(label => <div className="report-skeleton-card" key={label}>
        <span />
        <strong>{label}</strong>
        <p />
      </div>)}
    </div>
  </section>;
}

function ParentHomeworkUpload({
  childName,
  fileName,
  uploading,
  message,
  disabled,
  onFile,
  onUpload,
}: {
  childName: string;
  fileName: string;
  uploading: boolean;
  message: string;
  disabled: boolean;
  onFile: (file: File | null) => void;
  onUpload: () => void;
}) {
  return <section className="report-card">
    <div className="section-row">
      <h3>Upload Homework for {childName}</h3>
      <FileUp />
    </div>
    <div className="homework-parent-upload">
      <label className="file-upload-button">Take a Photo or Upload
        <input type="file" accept={homeworkAcceptTypes()} capture="environment" disabled={disabled || uploading} onChange={event => onFile(event.target.files?.[0] || null)} />
      </label>
      <button className="primary-button" onClick={onUpload} disabled={disabled || uploading}>{uploading ? 'Uploading...' : 'Upload for Child'}</button>
    </div>
    {fileName && <p className="success-note">Selected file: {fileName}</p>}
    <p className="muted-copy">JPG, PNG, HEIC, HEIF, and PDF uploads are saved to this child&apos;s homework history.</p>
    {message && <p className={message.startsWith('Could') || message.startsWith('Select') ? 'error-note' : 'success-note'}>{message}</p>}
  </section>;
}

function ParentHomeworkFollowUp({
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
  return <section className="report-card homework-follow-up">
    <div>
      <strong>Continue with Ms. Alisia</strong>
      <p>Type a question, a parent note, or the child&apos;s answer so Ms. Alisia can help with the next step.</p>
    </div>
    {!!messages.length && <div className="homework-follow-up-messages">
      {messages.map((item, index) => <div key={`${item.role}-${index}`} className={`homework-follow-up-message ${item.role === 'student' ? 'student' : 'assistant'}`}>
        <span>{item.role === 'student' ? 'You' : 'Ms. Alisia'}</span>
        <p>{item.content}</p>
      </div>)}
    </div>}
    <label>Response or question
      <textarea
        value={input}
        disabled={disabled}
        onChange={event => onInput(event.target.value)}
        onKeyDown={event => {
          if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') onSend();
        }}
        placeholder="Example: My child thinks the answer is 12, but they are not sure why."
      />
    </label>
    <button className="secondary-button compact" type="button" onClick={onSend} disabled={disabled || !input.trim()}>
      {loading ? 'Sending...' : 'Send to Ms. Alisia'}
    </button>
    {error && <p className="error-note">{error}</p>}
  </section>;
}

function homeworkContextMessages(upload: HomeworkUpload): ChatMessage[] {
  const subject = subjectFromUpload(upload);
  const lines = [
    'Ms. Alisia looked at this homework.',
    upload.ai_validation_summary || 'The homework was uploaded. We can work through it one step at a time.',
    upload.suggested_next_step ? `Next step: ${upload.suggested_next_step}` : '',
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

function parentFriendlyFollowUpError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message.toLowerCase().includes('parent needs to take care of')) return message;
  return 'That response did not send yet. Please try again in a moment.';
}

function HomeworkReportSection({ uploads }: { uploads: HomeworkUpload[] }) {
  return <div className="report-card">
    <div className="section-row">
      <h3>Homework Upload History</h3>
      <span className="muted-note">{uploads.length} saved</span>
    </div>
    {uploads.length ? uploads.map(upload => <div className="report-mini-card" key={upload.id || `${upload.file_name}-${upload.created_at}`}>
      <strong>{upload.file_name}</strong>
      <p>{formatDate(upload.created_at) || 'No date'} · {upload.file_type.toUpperCase()} · {upload.detected_subject || 'Subject pending'}</p>
      <div className="report-detail-list">
        <span>Status: {upload.is_unclear ? 'Needs clearer upload' : statusLabel(upload.ai_validation_status)}</span>
        <span>Summary: {upload.ai_validation_summary || 'Validation summary pending.'}</span>
        <span>Next step: {upload.suggested_next_step || 'Start with one guided tutoring step when ready.'}</span>
      </div>
    </div>) : <p className="muted-copy">No homework uploads are saved for this child yet.</p>}
  </div>;
}

function SubjectProgressSection({ progress }: { progress: SubjectProgress[] }) {
  return <div className="report-card">
    <h3>Subject Progress</h3>
    <div className="subject-progress-grid">
      {progress.map(item => <div key={item.subject} className="subject-progress-card">
        <div className="subject-progress-title">
          {iconForSubject(item.subject)}
          <div>
            <strong>{subjectLabel(item.subject)}</strong>
            <span>{item.level}</span>
          </div>
        </div>
        <div className="progress-track" aria-label={`${subjectLabel(item.subject)} progress ${item.progress_percentage}%`}>
          <span style={{ width: `${item.progress_percentage}%` }} />
        </div>
        <p>{item.progress_percentage}% complete — {item.recent_improvement || 'more activity will make this clearer.'}</p>
        <div className="report-detail-list">
          <span>Current topic: {item.current_topic || 'Not selected yet'}</span>
          <span>Strong area: {item.strong_area || 'More activity needed'}</span>
          <span>Needs review: {item.needs_review || 'No review topic recorded yet'}</span>
          <span>{item.completed_lessons} completed lesson thread(s)</span>
        </div>
      </div>)}
    </div>
  </div>;
}

function ParentPersonalizationSection({ report, childName }: { report: ChildReport | null; childName: string }) {
  return <section className="report-card parent-insight-card">
    <div className="section-row">
      <h3>What Ms. Alisia noticed</h3>
      <span className="muted-note">Personalized for {childName}</span>
    </div>
    <p>{report?.personalized_observation || `${childName} is ready to start a check-in so Ms. Alisia can build a more personalized plan.`}</p>
    {report?.exceptional_performance && <p className="success-note">{report.exceptional_performance}</p>}
    <div className="report-grid">
      <div className="report-mini-card">
        <strong>Strengths to celebrate</strong>
        <p>{report?.strength_recognition || `${childName} is ready to build confidence one skill at a time.`}</p>
      </div>
      <div className="report-mini-card">
        <strong>Next focus</strong>
        <p>{report?.next_focus || `${childName} can begin with one short check-in.`}</p>
      </div>
      <div className="report-mini-card">
        <strong>How Ms. Alisia will support the next session</strong>
        <p>{report?.support_plan || `Ms. Alisia will keep practice focused, encouraging, and paced for ${childName}.`}</p>
      </div>
    </div>
  </section>;
}

function WorkingLevelOverrideSection({
  records,
  selections,
  saving,
  message,
  disabled,
  onSelect,
  onSave,
  onReset,
}: {
  records: WorkingLevelOverrideItem[];
  selections: Record<string, string>;
  saving: string;
  message: string;
  disabled: boolean;
  onSelect: (subject: Subject, level: string) => void;
  onSave: (subject: Subject) => void;
  onReset: (subject: Subject) => void;
}) {
  if (!records.length) {
    return <div className="report-card">
      <h3>Subject Working Levels</h3>
      <p className="muted-copy">Select a child to manage subject challenge levels.</p>
    </div>;
  }
  return <div className="report-card">
    <div className="section-row">
      <h3>Subject Working Levels</h3>
      <span className="muted-note">Parent control</span>
    </div>
    <p className="muted-copy">This changes the learning challenge level for this subject only. It does not change your child's enrolled grade.</p>
    <div className="working-level-grid">
      {records.map(item => <div className="working-level-row" key={item.subject}>
        <div>
          <strong>{subjectLabel(item.subject)}</strong>
          <span>{item.display_text}</span>
          <small>{item.override_active ? 'Parent override active' : `Assessment level: ${item.assessed_level || 'not assessed yet'}`}</small>
        </div>
        <label>Working level
          <select
            value={selections[item.subject] || item.effective_working_level}
            disabled={disabled || saving === item.subject}
            onChange={event => onSelect(item.subject, event.target.value)}
          >
            {gradeOptionsFrom(item.enrolled_grade).map(grade => <option key={grade} value={grade}>{grade}</option>)}
          </select>
        </label>
        <div className="working-level-actions">
          <button className="secondary-button" disabled={disabled || saving === item.subject} onClick={() => onSave(item.subject)}>
            {saving === item.subject ? 'Saving...' : 'Save'}
          </button>
          <button className="ghost-button" disabled={disabled || saving === item.subject || !item.override_active} onClick={() => onReset(item.subject)}>
            Reset
          </button>
        </div>
      </div>)}
    </div>
    {message && <p className={message.startsWith('Could') ? 'error-note' : 'success-note'}>{message}</p>}
  </div>;
}

function gradeOptionsFrom(enrolledGrade: string): string[] {
  const start = Math.max(3, gradeNumber(enrolledGrade));
  return launchGrades.filter(grade => grade >= start).map(grade => `Grade ${grade}`);
}

function gradeNumber(value: string): number {
  const digits = value.replace(/\D/g, '');
  const parsed = Number(digits);
  return parsed >= 3 && parsed <= 6 ? parsed : 3;
}

function AssessmentSection({ assessments }: { assessments: AssessmentSummary[] }) {
  return <div className="report-card">
    <div className="section-row">
      <h3>Recent Assessment History</h3>
      <span className="muted-note">{assessments.length} saved</span>
    </div>
    {assessments.length ? assessments.map(item => {
      const strengths = (item.strengths || []).slice(0, 2);
      const growth = (item.learning_gaps || []).slice(0, 2);
      const nextStep = item.recommended_next_topics?.[0] || item.recommended_progression?.[0] || 'Continue with one short guided practice session.';
      return <div className="report-mini-card assessment-history-card" key={`${item.subject}-${item.created_at}`}>
        <div className="section-row">
          <strong>{subjectLabel(item.subject)} check-in</strong>
          <span className="muted-note">{formatDate(item.created_at) || 'Date not available'}</span>
        </div>
        <p><strong>Performance:</strong> {item.score_label || item.estimated_level || 'Learning path saved'}</p>
        <p>{item.parent_summary || 'Assessment saved for this child.'}</p>
        {!!strengths.length && <p><strong>Strengths to celebrate:</strong> {strengths.join(', ')}</p>}
        {!!growth.length && <p><strong>Growth areas:</strong> {growth.join(', ')}</p>}
        <p><strong>Next step:</strong> {nextStep}</p>
      </div>;
    }) : <p className="muted-copy">No assessment completed yet. Start an assessment to create a personalized learning path.</p>}
  </div>;
}

function SessionHistorySection({ sessions }: { sessions: TutorSessionSummary[] }) {
  return <div className="report-card">
    <h3>Tutor Session History</h3>
    {sessions.length ? sessions.map(item => <div className="report-mini-card" key={item.thread_id}>
      <strong>{item.title || item.topic || `${subjectLabel(item.subject)} chat`}</strong>
      <p>{subjectLabel(item.subject)} · {item.topic || 'General practice'} · {formatDate(item.last_activity_at) || 'No date'}</p>
      <div className="report-detail-list">
        <span>Time spent: {item.time_spent}</span>
        <span>Hints used: {item.hints_used}</span>
        <span>Practice attempts: {item.practice_attempts}</span>
        <span>Result: {item.improvement_status}</span>
        <span>Next step: {item.next_step}</span>
      </div>
    </div>) : <p className="muted-copy">No saved tutoring sessions for this child yet.</p>}
  </div>;
}

function LearningMemorySection({ memories }: { memories: LearningMemorySummary[] }) {
  return <div className="report-card">
    <h3>Recent Learning Memory</h3>
    {memories.length ? memories.map(item => <div className="report-mini-card" key={item.id || `${item.subject}-${item.updated_at}`}>
      <strong>{subjectLabel(item.subject)}{item.topic ? `: ${item.topic}` : ''}</strong>
      <p>{item.parent_facing_summary || item.child_facing_summary || 'Ms. Alisia saved a recent learning summary.'}</p>
      <div className="report-detail-list">
        <span>Worked on: {item.worked_on || 'Not recorded yet'}</span>
        <span>Needed support with: {item.struggled_with || 'No specific struggle recorded'}</span>
        <span>Getting stronger with: {item.mastered || 'More practice will make this clearer'}</span>
        <span>Next step: {item.next_step || 'Continue with one short guided practice session'}</span>
        <span>Updated: {formatDate(item.updated_at) || 'No date'}</span>
      </div>
    </div>) : <p className="muted-copy">No saved learning memory yet. Ms. Alisia will build this as tutoring sessions are completed.</p>}
  </div>;
}

function ReportList({ title, items }: { title: string; items: string[] }) {
  return <div className="report-card">
    <h3>{title}</h3>
    <ul>
      {items.map(item => <li key={item}>{item}</li>)}
    </ul>
  </div>;
}

function iconForSubject(subject: string) {
  if (subject === 'ELA') return <BookOpen />;
  if (subject === 'Writing') return <PenTool />;
  return <ClipboardCheck />;
}

function formatDate(value?: string | null): string {
  if (!value) return '';
  return new Date(value).toLocaleDateString();
}

function statusLabel(status: string): string {
  if (status === 'valid') return 'Validated';
  if (status === 'unclear') return 'Needs clearer upload';
  if (status === 'failed') return 'Needs another review';
  if (status === 'skipped') return 'Uploaded with limited review';
  return 'Pending validation';
}

function fallbackSubjectProgress(student: StudentProfile): SubjectProgress[] {
  return [
    fallbackProgress('Math', student.math_level),
    fallbackProgress('ELA', student.ela_level),
    fallbackProgress('Writing', student.writing_level),
  ];
}

function isBillingAccessMessage(message: string): boolean {
  const lower = message.toLowerCase();
  return lower.includes('parent needs to take care of')
    || lower.includes('billing')
    || lower.includes('payment')
    || lower.includes('trial')
    || lower.includes('subscription');
}

function fallbackProgress(subject: string, level: string): SubjectProgress {
  return {
    subject,
    level,
    progress_percentage: 0,
    current_topic: null,
    strong_area: null,
    needs_review: 'Start an assessment to find review topics.',
    recent_improvement: 'No recent activity yet.',
    completed_lessons: 0,
    assessment_count: 0,
    chat_count: 0,
    message_count: 0,
  };
}
