import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { ResultPanel } from '../components/ResultPanel';
import { assessmentQuestions } from '../constants';
import { apiPost } from '../lib/api';
import { AssessmentResult, StudentProfile, Subject } from '../types';

export function AssessmentView({ student, setStudent, childId = '' }: { student: StudentProfile; setStudent: (student: StudentProfile) => void; childId?: string }) {
  const [subject, setSubject] = useState<Subject>('Math');
  const [answers, setAnswers] = useState<string[]>(['', '', '']);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AssessmentResult | null>(null);

  async function submit() {
    setLoading(true);
    setResult(null);
    try {
      const data = await apiPost<AssessmentResult>('/api/assessments/evaluate', { student, child_id: childId || undefined, subject, grade: student.grade, answers, questions: assessmentQuestions[subject] });
      setResult(data);
      const updated = { ...student };
      if (subject === 'Math') updated.math_level = data.estimated_level;
      if (subject === 'ELA') updated.ela_level = data.estimated_level;
      if (subject === 'Writing') updated.writing_level = data.estimated_level;
      setStudent(updated);
    } catch {
      setResult({
        subject,
        enrolled_grade: student.grade,
        estimated_level: `Grade ${student.grade} - needs review`,
        score_label: 'Demo result',
        strengths: ['Attempted the assessment'],
        learning_gaps: ['Backend unavailable. Connect FastAPI to generate a full evaluation.'],
        recommended_progression: ['Review one skill at a time with Ms Alisia'],
        parent_summary: 'This is a local fallback result.'
      });
    } finally { setLoading(false); }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Assessment center" title="Find current level by subject" desc="MVP assessments cover Math, ELA, and Writing for Grades 3-6 with adaptive progression by subject." />
    <div className="tabs">
      {(['Math', 'ELA', 'Writing'] as Subject[]).map(s => <button key={s} className={subject === s ? 'selected' : ''} onClick={() => { setSubject(s); setAnswers(['', '', '']); setResult(null); }}>{s}</button>)}
    </div>
    <div className="assessment-grid">
      <div className="form-card">
        <h3>{subject} quick check</h3>
        {assessmentQuestions[subject].map((q, idx) => <label key={q}>{q}<textarea value={answers[idx]} onChange={e => setAnswers(answers.map((a, i) => i === idx ? e.target.value : a))} placeholder="Student answer..." /></label>)}
        <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Evaluating...' : 'Evaluate Assessment'}</button>
      </div>
      <ResultPanel result={result} />
    </div>
  </div>;
}
