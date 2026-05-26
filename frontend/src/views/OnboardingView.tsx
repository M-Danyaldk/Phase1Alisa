import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { supportedGrades } from '../constants';
import { apiPost } from '../lib/api';
import { StudentProfile } from '../types';

export function OnboardingView({ student, setStudent }: { student: StudentProfile; setStudent: (student: StudentProfile) => void }) {
  const [form, setForm] = useState<StudentProfile>(student);
  const [saved, setSaved] = useState(false);

  async function save() {
    setStudent(form);
    setSaved(true);
    try { await apiPost('/api/students', form); } catch { /* local only */ }
  }

  return <div className="page-stack narrow">
    <SectionHeader eyebrow="Parent setup" title="Tell Ms Alisia about the learner" desc="This lightweight profile helps personalize pacing, encouragement, and subject progression." />
    <div className="form-card">
      <label>Student first name<input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
      <label>Enrolled grade<select value={form.grade} onChange={e => setForm({ ...form, grade: Number(e.target.value) })}>{supportedGrades.map(grade => <option key={grade} value={grade}>Grade {grade}</option>)}</select></label>
      <label>Confidence style<select value={form.confidence} onChange={e => setForm({ ...form, confidence: e.target.value })}><option>Needs frequent encouragement</option><option>Sometimes needs encouragement</option><option>Enjoys challenge</option><option>Unsure yet</option></select></label>
      <label>Focus notes<textarea value={form.focus_notes} onChange={e => setForm({ ...form, focus_notes: e.target.value })} /></label>
      <label>Parent notes<textarea value={form.parent_notes} onChange={e => setForm({ ...form, parent_notes: e.target.value })} /></label>
      <button className="primary-button" onClick={save}>Save Profile</button>
      {saved && <p className="success-note">Profile saved. Ms Alisia will use this context during learning.</p>}
    </div>
  </div>;
}
