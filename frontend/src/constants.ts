import { StudentProfile, Subject } from './types';

export const launchGrades = [3, 4, 5, 6];
export const futureGrades = [7, 8, 9, 10, 11, 12];
export const internalSupportedGrades = [...launchGrades, ...futureGrades];
export const supportedGrades = launchGrades;
export const gradeLevelOptions = launchGrades.map(grade => `Grade ${grade}`);
export const futureGradeLevelOptions = futureGrades.map(grade => `Grade ${grade}`);
export const internalGradeLevelOptions = internalSupportedGrades.map(grade => `Grade ${grade}`);
export const launchSubjects: Subject[] = ['Math', 'ELA', 'Writing'];
export const futureSubjects = ['Science', 'Social Studies'];

export function subjectLabel(subject: Subject | string): string {
  return subject === 'ELA' ? 'Reading' : subject;
}

export function isLaunchGradeLevel(gradeLevel: string): boolean {
  return gradeLevelOptions.includes(gradeLevel);
}

export const initialStudent: StudentProfile = {
  name: 'Ava',
  grade: 4,
  math_level: 'Not assessed yet',
  ela_level: 'Not assessed yet',
  writing_level: 'Not assessed yet',
  confidence: 'Sometimes needs encouragement',
  focus_notes: 'Prefers short lessons and quick check-ins',
  parent_notes: 'Keep explanations short and supportive.'
};

export const assessmentQuestions: Record<Subject, string[]> = {
  Math: [
    'What is 6 x 7?',
    'Which is larger: 3/4 or 2/3? Explain briefly.',
    'A book has 48 pages. Mia reads 8 pages each day. How many days will it take?'
  ],
  ELA: [
    'Read this sentence: The puppy sprinted across the yard. What does sprinted mean?',
    'What is the main idea of a paragraph?',
    'Fix this sentence: she dont like apples'
  ],
  Writing: [
    'Write one clear sentence about your favorite school subject.',
    'Write 3 sentences that explain why reading is helpful.',
    'How can you make this sentence better: The dog was nice?'
  ]
};

export const futureModules = [
  { title: 'Mobile App', desc: 'Future iOS/Android experience.' },
  { title: 'Teacher Portal', desc: 'Classroom and educator workflows.' },
  { title: 'School/LMS Integrations', desc: 'School platform integrations in later phases.' },
  { title: 'Advanced Analytics', desc: 'Deeper learning trends and visual analytics.' },
  { title: 'Advanced Handwriting AI', desc: 'Detailed handwriting scoring beyond lightweight feedback.' },
  { title: 'Science & Social Studies', desc: 'Additional subject support after MVP.' }
];
