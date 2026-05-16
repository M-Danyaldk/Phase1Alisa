import { useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { apiPostForm } from '../lib/api';
import { StudentProfile, Subject } from '../types';

export function HomeworkView({ student }: { student: StudentProfile }) {
  const [note, setNote] = useState('Please check this worksheet for handwriting and guide me on the first problem.');
  const [subject, setSubject] = useState<Subject>('Writing');
  const [fileName, setFileName] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);

  async function analyze() {
    if (!selectedFile) {
      setFeedback('Please choose a file first. Phase 1 supports real uploads, while detailed file analysis will come in the next phase.');
      return;
    }
    setLoading(true);
    try {
      const payload = new FormData();
      payload.append('student_json', JSON.stringify(student));
      payload.append('subject', subject);
      payload.append('note', note);
      payload.append('file', selectedFile);
      const data = await apiPostForm<{ feedback: string; provider: string }>('/api/homework/lightweight-feedback', payload);
      setFeedback(data.feedback);
    } catch {
      setFeedback('The file could not be uploaded right now. Once uploaded successfully, Phase 1 will confirm receipt and detailed file analysis will be added in the next phase.');
    } finally { setLoading(false); }
  }

  return <div className="page-stack narrow">
    <SectionHeader eyebrow="Homework and handwriting" title="Lightweight upload workflow for MVP" desc="Phase 1 accepts real worksheet and writing uploads. Detailed worksheet reading and handwriting analysis are planned for the next phase." />
    <div className="form-card">
      <label>Subject<select value={subject} onChange={e => setSubject(e.target.value as Subject)}><option>Math</option><option>ELA</option><option>Writing</option></select></label>
      <label>Upload worksheet or writing sample<input type="file" accept="image/*,.pdf" onChange={e => {
        const file = e.target.files?.[0] || null;
        setSelectedFile(file);
        setFileName(file?.name || '');
      }} /></label>
      {fileName && <p className="success-note">Selected file: {fileName}</p>}
      <label>What should Ms Alisia help with?<textarea value={note} onChange={e => setNote(e.target.value)} /></label>
      <button className="primary-button" onClick={analyze} disabled={loading}>{loading ? 'Uploading...' : 'Upload File'}</button>
      {feedback && <pre className="feedback-box">{feedback}</pre>}
    </div>
  </div>;
}
