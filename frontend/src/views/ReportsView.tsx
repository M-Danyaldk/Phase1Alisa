import { useEffect, useState } from 'react';
import { BarChart3, BookOpen, CheckCircle2, ClipboardCheck, Clock, FileUp, PenTool, Target, TrendingUp } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { homeworkAcceptTypes, uploadParentHomework } from '../lib/api/homework';
import { getFilteredChildReport, getWeeklyEmailPreview } from '../lib/api/reports';
import { getWorkingLevelOverrides, resetWorkingLevelOverride, setWorkingLevelOverride } from '../lib/api/workingLevelOverrides';
import { AssessmentSummary, ChildReport, LearningMemorySummary, SubjectProgress, TutorSessionSummary, WeeklyReportEmailPreview } from '../types/childReport';
import { StudentProfile, Subject, View } from '../types';
import { HomeworkUpload } from '../types/homework';
import { WorkingLevelOverrideItem, WorkingLevelOverridesResponse } from '../types/workingLevelOverrides';
import { launchGrades } from '../constants';

type Period = 'week' | 'month' | 'all';
type SubjectFilter = 'All' | Subject;

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

  useEffect(() => {
    if (!accessToken || !childId) {
      setReport(null);
      setWorkingLevels(null);
      return;
    }
    setLoading(true);
    setError('');
    getFilteredChildReport(accessToken, childId, period, subjectFilter)
      .then(setReport)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load this child report.'))
      .finally(() => setLoading(false));
    getWeeklyEmailPreview(accessToken, childId)
      .then(setEmailPreview)
      .catch(() => setEmailPreview(null));
    getWorkingLevelOverrides(accessToken, childId)
      .then(records => {
        setWorkingLevels(records);
        setWorkingLevelSelections(Object.fromEntries(records.subjects.map(item => [item.subject, item.effective_working_level])));
      })
      .catch(() => setWorkingLevels(null));
  }, [accessToken, childId, period, subjectFilter]);

  const subjectProgress = report?.subject_progress || fallbackSubjectProgress(student);
  const childName = report?.child_name || student.name;

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
      setWorkingLevelMessage(`${subject} working level saved.`);
      getFilteredChildReport(accessToken, childId, period, subjectFilter).then(setReport).catch(() => undefined);
    } catch (error) {
      const detail = error instanceof Error ? error.message : '';
      setWorkingLevelMessage(detail ? `Could not save the working level right now. ${detail}` : 'Could not save the working level right now.');
    } finally {
      setWorkingLevelSaving('');
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
      setWorkingLevelMessage(`${subject} working level reset to the assessment or enrolled grade.`);
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
          <option value="ELA">ELA</option>
          <option value="Writing">Writing</option>
        </select>
      </label>
    </div>

    {loading && <p className="muted-note">Loading report...</p>}
    {error && <p className="error-note">{error}</p>}
    {!childId && <p className="error-note">Select or create a child profile to view reports.</p>}

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

    <HomeworkReportSection uploads={report?.homework_uploads || []} />

    <div className="report-grid">
      <ReportList title="Strengths" items={report?.strengths || ['Complete an assessment to identify strong areas.']} />
      <ReportList title="Needs Review" items={report?.weak_areas || ['Start with a quick assessment to find learning gaps.']} />
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
        <p>{emailPreview?.email_note || 'Weekly email reports are not connected yet. This report structure is prepared so a future email service can send one separate summary per child.'}</p>
        {emailPreview && <div className="report-mini-card">
          <strong>{emailPreview.subject_line}</strong>
          <p>{emailPreview.greeting}</p>
          <p>{emailPreview.summary}</p>
          <p>Generated {formatDate(emailPreview.generated_at)} · Email connected: {emailPreview.email_connected ? 'Yes' : 'No'}</p>
        </div>}
      </div>
      <div className="report-card">
        <h3>Student-Safe View</h3>
        <p>Children can later see their own progress and achievements, but billing, sibling reports, grade changes, and parent controls should remain parent-only.</p>
      </div>
    </div>
  </div>;
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
            <strong>{item.subject}</strong>
            <span>{item.level}</span>
          </div>
        </div>
        <div className="progress-track" aria-label={`${item.subject} progress ${item.progress_percentage}%`}>
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
          <strong>{item.subject}</strong>
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
      <h3>Assessment Results</h3>
      <span className="muted-note">Parent details</span>
    </div>
    {assessments.length ? assessments.map(item => <div className="report-mini-card" key={`${item.subject}-${item.created_at}`}>
      <strong>{item.subject}: {item.estimated_level}</strong>
      <p>{formatDate(item.created_at) || 'Assessment date not available'}</p>
      {item.score_label && <p>Result summary: {item.score_label}</p>}
      <p>{item.parent_summary || 'Assessment saved for this child.'}</p>
      {!!(item.strengths || []).length && <p>Strengths: {(item.strengths || []).slice(0, 2).join(', ')}</p>}
      {!!(item.learning_gaps || []).length && <p>Areas for growth: {(item.learning_gaps || []).slice(0, 2).join(', ')}</p>}
      {!!(item.recommended_next_topics || []).length && <p>Recommended next topics: {(item.recommended_next_topics || []).slice(0, 3).join(', ')}</p>}
      {!!(item.recommended_progression || []).length && <p>Suggested learning path: {(item.recommended_progression || []).slice(0, 2).join(', ')}</p>}
    </div>) : <p className="muted-copy">No assessment completed yet. Start an assessment to create a personalized learning path.</p>}
  </div>;
}

function SessionHistorySection({ sessions }: { sessions: TutorSessionSummary[] }) {
  return <div className="report-card">
    <h3>Tutor Session History</h3>
    {sessions.length ? sessions.map(item => <div className="report-mini-card" key={item.thread_id}>
      <strong>{item.title || item.topic || `${item.subject} chat`}</strong>
      <p>{item.subject} · {item.topic || 'General practice'} · {formatDate(item.last_activity_at) || 'No date'}</p>
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
      <strong>{item.subject}{item.topic ? `: ${item.topic}` : ''}</strong>
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
  if (status === 'failed') return 'Validation failed';
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
