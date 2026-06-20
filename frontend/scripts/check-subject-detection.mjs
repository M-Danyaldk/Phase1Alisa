import assert from 'node:assert/strict';
import { detectSubjectFromMessage, prepareSubjectTurn } from '../src/lib/subjectDetection.ts';
import { hasActionableTutorTask } from '../src/lib/quickActions.ts';

const cases = [
  ['switch to ELA', 'ELA'],
  ['switch subjects to English language arts', 'ELA'],
  ['go back to reading', 'ELA'],
  ['change back to maths', 'Math'],
  ['move over to writing', 'Writing'],
  ['reading', 'ELA'],
  ['Reading', 'ELA'],
  ['READING', 'ELA'],
  ['writing', 'Writing'],
  ['Writing', 'Writing'],
  ['WRITING', 'Writing'],
  ['math', 'Math'],
  ['Math', 'Math'],
  ['MATH', 'Math'],
  ['maths', 'Math'],
  ['Maths', 'Math'],
  ['MATHS', 'Math'],
  ['start reading', 'ELA'],
  ['Start Reading', 'ELA'],
  ['START READING', 'ELA'],
  ['start writing', 'Writing'],
  ['Start Writing', 'Writing'],
  ['start math', 'Math'],
  ['start maths', 'Math'],
  ['Start Maths', 'Math'],
  ['write reading', 'ELA'],
  ['write writing', 'Writing'],
  ['write maths', 'Math'],
  ['I need help with grammar', 'ELA'],
  ['Can we practice fractions?', 'Math'],
  ['lets practice decimals', 'Math'],
  ["I'd like reading help", 'ELA'],
  ['I want to work on an essay', 'Writing'],
  ['practice writing about a reading passage', 'Writing'],
  ['write a paragraph about fractions', 'Writing'],
  ['What is a numerator?', null],
  ['This reading passage mentions fractions.', null],
  ['switch to science', null],
  ['explain this again', null],
];

for (const [message, expected] of cases) {
  assert.equal(detectSubjectFromMessage(message), expected, message);
}

console.log(`Subject detection check passed (${cases.length} cases).`);

const oldHistory = [{ subject: 'Math', content: 'Try 3/4 + 1/4' }];
const oldState = { current_subject: 'Math', active_task_id: 'math-task', attempt_count: 2 };
const freshState = { current_subject: 'ELA', active_task_id: '', attempt_count: 0 };
const changed = prepareSubjectTurn('Math', 'ELA', oldHistory, oldState, freshState, 'math-thread');
assert.equal(changed.activeSubject, 'ELA');
assert.equal(changed.subjectChanged, true);
assert.deepEqual(changed.history, []);
assert.equal(changed.tutoringState, freshState);
assert.equal(changed.threadId, undefined);

const unchanged = prepareSubjectTurn('Math', 'Math', oldHistory, oldState, freshState, 'math-thread');
assert.equal(unchanged.subjectChanged, false);
assert.equal(unchanged.history, oldHistory);
assert.equal(unchanged.tutoringState, oldState);
assert.equal(unchanged.threadId, 'math-thread');

const safetyLocked = prepareSubjectTurn('Math', 'ELA', oldHistory, oldState, freshState, 'math-thread', false);
assert.equal(safetyLocked.activeSubject, 'Math');
assert.equal(safetyLocked.subjectChanged, false);
assert.equal(safetyLocked.history, oldHistory);
assert.equal(safetyLocked.tutoringState, oldState);
assert.equal(safetyLocked.threadId, 'math-thread');

console.log('Subject transition isolation check passed.');

assert.equal(hasActionableTutorTask({}), false);
assert.equal(hasActionableTutorTask({ current_question: 'What is 3 + 4?' }), true);
assert.equal(hasActionableTutorTask({ active_task_id: 'task-1' }), true);
assert.equal(hasActionableTutorTask({ active_problem: 'Write one paragraph.' }), true);
console.log('Quick-action availability check passed.');
