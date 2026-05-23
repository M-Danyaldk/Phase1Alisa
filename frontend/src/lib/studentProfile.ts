import { initialStudent } from '../constants';
import { ProfileResponse } from '../types/auth';
import { ChildProfile } from '../types/childProfile';
import { StudentProfile } from '../types';

function gradeNumberFromLabel(gradeLevel: string | null | undefined): number {
  const gradeMatch = (gradeLevel || '').match(/\d+/);
  return gradeMatch ? Number(gradeMatch[0]) : initialStudent.grade;
}

export function profileToStudent(profile: ProfileResponse): StudentProfile {
  return {
    ...initialStudent,
    id: Number.isFinite(Number(profile.id)) ? Number(profile.id) : undefined,
    name: profile.full_name,
    grade: gradeNumberFromLabel(profile.grade_level),
    parent_notes: profile.parent_guardian_email ? `Parent/Guardian email: ${profile.parent_guardian_email}` : initialStudent.parent_notes,
    created_at: profile.created_at || undefined
  };
}

export function childToStudent(child: ChildProfile): StudentProfile {
  const levels = child.learning_levels || {};
  return {
    ...initialStudent,
    name: child.name,
    grade: gradeNumberFromLabel(child.grade_level),
    math_level: levels.Math || initialStudent.math_level,
    ela_level: levels.ELA || initialStudent.ela_level,
    writing_level: levels.Writing || initialStudent.writing_level,
    focus_notes: child.learning_goals || initialStudent.focus_notes,
    parent_notes: child.parent_notes || initialStudent.parent_notes,
    created_at: child.created_at || undefined
  };
}
