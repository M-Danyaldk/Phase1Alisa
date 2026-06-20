export type DetectedSubject = 'Math' | 'ELA' | 'Writing';

const directSwitchPattern = /\b(?:switch|change|move|go)(?:\s+(?:subjects?|over))?\s+(?:to|back\s+to)\s+(maths?|mathematics|arithmetic|ela|english(?:\s+language\s+arts)?|language\s+arts|reading|writing)\b/i;

const simpleSubjectCommandPattern = /^(?:(?:start|switch\s+to|go\s+to|change\s+to|practice|study|learn|do|try|open|begin|help\s+me\s+with|work\s+on|teach\s+me)\s+)?(maths?|mathematics|arithmetic|ela|english(?:\s+language\s+arts)?|language\s+arts|reading|writing)\s*(?:please|now)?[.!?]*$/i;

const commandedSubjectPattern = /^(?:start|practice|study|learn|do|try|help\s+me\s+with|work\s+on|teach\s+me|write)\s+(maths?|mathematics|arithmetic|ela|english(?:\s+language\s+arts)?|language\s+arts|reading|writing)\b/i;

const requestPattern = /\b(?:can\s+we|could\s+we|please|let(?:(?:'|\u2019)s|s)|i\s+(?:want|need)(?:\s+to)?|i(?:'|\u2019)d\s+like(?:\s+to)?|start|practice|study|learn|do|try|help\s+me\s+with|work\s+on|teach\s+me|write)\b/i;

const subjectCues: Array<{ subject: DetectedSubject; pattern: RegExp }> = [
  {
    subject: 'Math',
    pattern: /\b(?:maths?|mathematics|arithmetic|fractions?|decimals?|division|divide|multiplication|multiply|subtraction|subtract|addition|add|equations?|ratios?|lcm|gcf|area|perimeter)\b/i,
  },
  {
    subject: 'ELA',
    pattern: /\b(?:ela|english(?:\s+language\s+arts)?|language\s+arts|reading|read|passages?|main\s+idea|inferences?|context\s+clues?|theme|characters?|setting|summary|vocabulary|author|evidence|grammar|verbs?|nouns?|adjectives?|sentence\s+meaning)\b/i,
  },
  {
    subject: 'Writing',
    pattern: /\b(?:writing|write|paragraphs?|essays?|topic\s+sentence|transitions?|rewrite|fix\s+this\s+sentence|sentence\s+structure|clarity|handwriting|spacing|legibility|punctuation)\b/i,
  },
];

function subjectFromDirectAlias(alias: string): DetectedSubject {
  if (/^(?:maths?|mathematics|arithmetic)$/i.test(alias)) return 'Math';
  if (/^(?:writing)$/i.test(alias)) return 'Writing';
  return 'ELA';
}

export function detectSubjectFromMessage(message: string): DetectedSubject | null {
  const trimmedMessage = message.trim();
  const directSwitch = directSwitchPattern.exec(trimmedMessage);
  if (directSwitch) return subjectFromDirectAlias(directSwitch[1]);
  const simpleSubjectCommand = simpleSubjectCommandPattern.exec(trimmedMessage);
  if (simpleSubjectCommand) return subjectFromDirectAlias(simpleSubjectCommand[1]);
  const commandedSubject = commandedSubjectPattern.exec(trimmedMessage);
  if (commandedSubject) return subjectFromDirectAlias(commandedSubject[1]);
  if (!requestPattern.test(message)) return null;

  const matches = subjectCues
    .map(({ subject, pattern }) => ({ subject, index: message.search(pattern) }))
    .filter(match => match.index >= 0)
    .sort((left, right) => left.index - right.index);

  return matches[0]?.subject || null;
}

export function prepareSubjectTurn<TState, THistory>(
  currentSubject: DetectedSubject,
  detectedSubject: DetectedSubject | null,
  recentHistory: THistory[],
  currentState: TState,
  freshState: TState,
  threadId?: string,
  transitionAllowed = true,
) {
  const effectiveSubject = transitionAllowed ? detectedSubject : null;
  const activeSubject = effectiveSubject || currentSubject;
  const subjectChanged = Boolean(effectiveSubject && effectiveSubject !== currentSubject);
  return {
    activeSubject,
    subjectChanged,
    history: subjectChanged ? [] : recentHistory,
    tutoringState: subjectChanged ? freshState : currentState,
    threadId: subjectChanged ? undefined : threadId,
  };
}
