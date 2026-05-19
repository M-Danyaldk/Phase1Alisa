import { useEffect, useState } from 'react';
import { BarChart3, BookOpen, Brain, CheckCircle2, ClipboardCheck, Clock, PenTool, Target, TrendingUp } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { getFilteredChildReport, getWeeklyEmailPreview } from '../lib/api/reports';
import { AssessmentSummary, ChildReport, SubjectProgress, TutorSessionSummary, WeeklyReportEmailPreview } from '../types/childReport';
import { StudentProfile, Subject, View } from '../types';

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

  useEffect(() => {
    if (!accessToken || !childId) {
      setReport(null);
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
  }, [accessToken, childId, period, subjectFilter]);

  const subjectProgress = report?.subject_progress || fallbackSubjectProgress(student);
  const childName = report?.child_name || student.name;

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

    <div className="report-grid">
      <ReportList title="Strengths" items={report?.strengths || ['Complete an assessment to identify strong areas.']} />
      <ReportList title="Needs Review" items={report?.weak_areas || ['Start with a quick assessment to find learning gaps.']} />
      <ReportList title="Recommended Next Steps" items={report?.recommended_next_steps || ['Run a quick assessment.', 'Practice one skill at a time with Ms Alisia.']} />
    </div>

    <AssessmentSection assessments={report?.recent_assessments || []} />
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

function AssessmentSection({ assessments }: { assessments: AssessmentSummary[] }) {
  return <div className="report-card">
    <div className="section-row">
      <h3>Assessment Results</h3>
      <span className="muted-note">Results only</span>
    </div>
    {assessments.length ? assessments.map(item => <div className="report-mini-card" key={`${item.subject}-${item.created_at}`}>
      <strong>{item.subject}: {item.estimated_level}</strong>
      <p>{item.parent_summary || 'Assessment saved for this child.'}</p>
      {!!item.learning_gaps.length && <p>Practice recommended: {item.learning_gaps.slice(0, 2).join(', ')}</p>}
      {!!item.recommended_progression.length && <p>Learning path: {item.recommended_progression.slice(0, 2).join(', ')}</p>}
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
