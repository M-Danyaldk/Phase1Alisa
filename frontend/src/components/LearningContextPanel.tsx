import { StudentProfile, Subject } from '../types';

type Props = {
  student: StudentProfile;
  subject: Subject;
  topic: string;
  onSubjectChange: (subject: Subject) => void;
  onTopicChange: (topic: string) => void;
};

export function LearningContextPanel({ student, subject, topic, onSubjectChange, onTopicChange }: Props) {
  const currentLevel = subject === 'Math' ? student.math_level : subject === 'ELA' ? student.ela_level : student.writing_level;

  return <aside className="learning-context-panel" aria-label="Learning context">
    <label>Subject
      <select value={subject} onChange={event => onSubjectChange(event.target.value as Subject)}>
        <option>Math</option>
        <option>ELA</option>
        <option>Writing</option>
      </select>
    </label>
    <label>Topic
      <input value={topic} onChange={event => onTopicChange(event.target.value)} />
    </label>
    <div className="mini-summary context-summary">
      <strong>{student.name}</strong>
      <span>Grade {student.grade}</span>
      <span>{currentLevel}</span>
    </div>
    <div className="context-subjects">
      <span>Math: {student.math_level}</span>
      <span>ELA: {student.ela_level}</span>
      <span>Writing: {student.writing_level}</span>
    </div>
  </aside>;
}
