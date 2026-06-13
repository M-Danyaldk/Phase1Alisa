import { initialStudent } from '../constants';
import { ProfileResponse } from '../types/auth';
import { ChildProfile } from '../types/childProfile';
import { StudentProfile, Subject } from '../types';

function gradeNumberFromLabel(gradeLevel: string | null | undefined): number {
  const gradeMatch = (gradeLevel || '').match(/\d+/);
  return gradeMatch ? Number(gradeMatch[0]) : initialStudent.grade;
}

export function profileToStudent(profile: ProfileResponse): StudentProfile {
  return {
    ...initialStudent,
    id: Number.isFinite(Number(profile.id)) ? Number(profile.id) : undefined,
    name: profile.full_name,
    created_at: profile.created_at || undefined
  };
}

export function childToStudent(child: ChildProfile): StudentProfile {
  const levels = child.learning_levels || {};
  const learningGoals = child.learning_goals || '';
  const difficultyLevel = child.difficulty_level || '';
  return {
    ...initialStudent,
    name: child.name,
    grade: gradeNumberFromLabel(child.grade_level),
    subjects: subjectList(child.subjects),
    math_level: levels.Math || initialStudent.math_level,
    ela_level: levels.ELA || initialStudent.ela_level,
    writing_level: levels.Writing || initialStudent.writing_level,
    confidence: difficultyLevel || initialStudent.confidence,
    learning_goals: learningGoals,
    difficulty_level: difficultyLevel,
    focus_notes: learningGoals || initialStudent.focus_notes,
    parent_notes: child.parent_notes || initialStudent.parent_notes,
    created_at: child.created_at || undefined
  };
}

function subjectList(subjects: unknown): Subject[] {
  if (!Array.isArray(subjects)) return initialStudent.subjects;
  const allowed: Subject[] = ['Math', 'ELA', 'Writing'];
  const filtered = subjects.filter((subject): subject is Subject => allowed.includes(subject as Subject));
  return filtered.length ? filtered : initialStudent.subjects;
}
