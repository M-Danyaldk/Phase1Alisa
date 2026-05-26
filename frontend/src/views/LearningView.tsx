import { useEffect, useRef, useState } from 'react';
import { ChatThreadList } from '../components/ChatThreadList';
import { ChatWorkspace } from '../components/ChatWorkspace';
import { LearningContextPanel } from '../components/LearningContextPanel';
import { SectionHeader } from '../components/SectionHeader';
import { apiPost } from '../lib/api';
import { getSessionStatus, pauseInactiveSession, recordInactivityNudge, recordSessionActivity, resumeSession } from '../lib/api/sessionActivity';
import { ChatThread, getChatHistory, getChatThreads, getChildChatThreads } from '../lib/chatApi';
import { ChatMessage, StudentProfile, Subject, TopicSource, TutoringState } from '../types';
import { SessionStatusResponse } from '../types/sessionActivity';

const INACTIVITY_NUDGE_MS = 2 * 60 * 1000;
const INACTIVITY_PAUSE_MS = 3 * 60 * 1000;
const SESSION_ACTIVITY_PING_MS = 10 * 1000;
const SESSION_STATUS_POLL_MS = 30 * 1000;
const INACTIVE_PAUSE_SECONDS = 180;
const INACTIVE_PAUSE_MESSAGE = 'Looks like you stepped away — your session is saved. Come back whenever you are ready!';
const DEFAULT_BRAIN_BREAK_MESSAGE = 'Great work today! Your brain needs a short rest to absorb everything you have learned. Take a 30-minute break and come back ready to learn even more!';

const subjectDefaults: Record<Subject, string> = {
  Math: 'fractions',
  ELA: 'reading comprehension',
  Writing: 'sentence structure'
};

function subjectGreeting(studentName: string, subject: Subject): string {
  const labels: Record<Subject, string> = {
    Math: 'math',
    ELA: 'reading and ELA',
    Writing: 'writing'
  };
  return `Hi ${studentName}! I am Ms Alisia. We are working on ${labels[subject]} now, and I will help with one small step at a time.`;
}

function subjectSwitchMessage(subject: Subject): string {
  const labels: Record<Subject, string> = {
    Math: 'math',
    ELA: 'reading and ELA',
    Writing: 'writing'
  };
  return `We are working on ${labels[subject]} now. Let us do one small step at a time.`;
}

function detectSubjectFromMessage(message: string): Subject | null {
  const text = message.toLowerCase();

  const mathHints = ['math', 'fraction', 'fractions', 'decimal', 'divide', 'division', 'multiply', 'multiplication', 'subtract', 'addition', 'equation', 'ratio', 'lcm', 'gcf', 'area', 'perimeter'];
  const elaHints = ['reading', 'read', 'passage', 'main idea', 'inference', 'context clue', 'context clues', 'theme', 'character', 'setting', 'summary', 'vocabulary', 'author', 'evidence', 'grammar', 'verb', 'noun', 'adjective', 'sentence meaning'];
  const writingHints = ['writing', 'paragraph', 'essay', 'topic sentence', 'transition', 'rewrite', 'fix this sentence', 'sentence structure', 'clarity', 'handwriting', 'spacing', 'legibility', 'punctuation'];

  if (mathHints.some(hint => text.includes(hint))) return 'Math';
  if (writingHints.some(hint => text.includes(hint))) return 'Writing';
  if (elaHints.some(hint => text.includes(hint))) return 'ELA';
  return null;
}

export function LearningView({ student, accessToken = '', childId = '', initialSubject = 'Math', studentSession = false, onInactivePause }: { student: StudentProfile; accessToken?: string; childId?: string; initialSubject?: Subject; studentSession?: boolean; onInactivePause?: (message: string) => void }) {
  const initialTutoringState: TutoringState = { active_problem: '', current_step: '', attempt_count: 0, answer_revealed: false, mode: 'solve', status: 'idle', memory_note: '' };
  const chatSetupNotice = 'Chat worked, but history was not saved. Please check Supabase setup.';
  const [subject, setSubject] = useState<Subject>(initialSubject);
  const [topic, setTopic] = useState(subjectDefaults[initialSubject]);
  const [topicSource, setTopicSource] = useState<TopicSource>('default');
  const [input, setInput] = useState('I need help understanding this.');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'msalisia', content: subjectGreeting(student.name, initialSubject), subject: initialSubject }
  ]);
  const [loading, setLoading] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [threadError, setThreadError] = useState('');
  const [historySetupPending, setHistorySetupPending] = useState(false);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThread, setActiveThread] = useState<ChatThread | null>(null);
  const [lastAnnouncedSubject, setLastAnnouncedSubject] = useState<Subject>(initialSubject);
  const [tutoringState, setTutoringState] = useState<TutoringState>(initialTutoringState);
  const [sessionStatus, setSessionStatus] = useState<SessionStatusResponse | null>(null);
  const [nudgeVisible, setNudgeVisible] = useState(false);
  const [sessionNotice, setSessionNotice] = useState('');
  const [brainBreakWarning, setBrainBreakWarning] = useState('');
  const [lastActivityAt, setLastActivityAt] = useState(() => Date.now());
  const lastActivityPingRef = useRef(0);
  const nudgeRecordedRef = useRef(false);
  const pauseRecordedRef = useRef(false);
  const trackingEnabled = Boolean(studentSession && accessToken && childId);
  const sessionId = sessionStatus?.session_id || null;
  const brainBreakActive = Boolean(sessionStatus?.brain_break_active);
  const tutorDisabled = brainBreakActive || sessionStatus?.brain_break_required || sessionStatus?.session_status === 'paused_inactive';

  function greetingFor(nextSubject: Subject) {
    return [{ role: 'msalisia' as const, content: subjectGreeting(student.name, nextSubject), subject: nextSubject }];
  }

  async function refreshThreads() {
    if (!accessToken) return;
    try {
      const records = childId ? await getChildChatThreads(accessToken, childId, undefined, studentSession) : await getChatThreads(accessToken);
      setThreads(records);
      setHistorySetupPending(false);
    } catch (error) {
      if (isChatSetupPending(error)) {
        setHistorySetupPending(true);
        setThreadError('');
        setThreads([]);
        return;
      }
      setThreadError(error instanceof Error ? error.message : 'Could not load previous chats.');
    }
  }

  useEffect(() => {
    setThreadError('');
    setActiveThread(null);
    setTutoringState(initialTutoringState);
    setSubject(initialSubject);
    setTopic(subjectDefaults[initialSubject]);
    setTopicSource('default');
    setLastAnnouncedSubject(initialSubject);
    setMessages(greetingFor(initialSubject));
    refreshThreads();
    setSessionStatus(null);
    setNudgeVisible(false);
    setSessionNotice('');
    setBrainBreakWarning('');
    setLastActivityAt(Date.now());
    lastActivityPingRef.current = 0;
    nudgeRecordedRef.current = false;
    pauseRecordedRef.current = false;
  }, [accessToken, childId, initialSubject]);

  useEffect(() => {
    if (!trackingEnabled) return;
    let cancelled = false;

    getSessionStatus(accessToken, childId)
      .then(async status => {
        if (cancelled) return;
        if (status.session_status === 'paused' && status.session_id) {
          const resumed = await resumeSession(accessToken, childId, status.session_id);
          if (cancelled) return;
          setLastActivityAt(Date.now());
          applySessionStatus(resumed);
          return;
        }
        if (!status.session_id) {
          const started = await recordSessionActivity(accessToken, childId, subject, topic, null, 'activity');
          if (cancelled) return;
          setLastActivityAt(Date.now());
          applySessionStatus(started);
          return;
        }
        setLastActivityAt(Date.now());
        applySessionStatus(status);
      })
      .catch(error => {
        if (!cancelled) setSessionNotice(childFriendlySessionMessage(error));
      });

    const intervalId = window.setInterval(() => {
      getSessionStatus(accessToken, childId)
        .then(status => {
          if (!cancelled) applySessionStatus(status);
        })
        .catch(error => {
          if (!cancelled) setSessionNotice(childFriendlySessionMessage(error));
        });
    }, SESSION_STATUS_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [accessToken, childId, subject, topic, trackingEnabled]);

  useEffect(() => {
    if (!trackingEnabled || brainBreakActive || loading || sessionStatus?.session_status === 'paused_inactive') return;

    nudgeRecordedRef.current = false;
    pauseRecordedRef.current = false;

    const nudgeDelay = Math.max(0, INACTIVITY_NUDGE_MS - (Date.now() - lastActivityAt));
    const pauseDelay = Math.max(0, INACTIVITY_PAUSE_MS - (Date.now() - lastActivityAt));
    const nudgeTimer = window.setTimeout(() => {
      setNudgeVisible(true);
      if (nudgeRecordedRef.current) return;
      nudgeRecordedRef.current = true;
      recordInactivityNudge(accessToken, childId, sessionId)
        .then(applySessionStatus)
        .catch(error => setSessionNotice(childFriendlySessionMessage(error)));
    }, nudgeDelay);
    const pauseTimer = window.setTimeout(() => {
      if (pauseRecordedRef.current) return;
      pauseRecordedRef.current = true;
      pauseInactiveSession(accessToken, childId, sessionId, INACTIVE_PAUSE_SECONDS)
        .then(status => {
          applySessionStatus(status);
          setNudgeVisible(false);
          setSessionNotice(INACTIVE_PAUSE_MESSAGE);
          onInactivePause?.(INACTIVE_PAUSE_MESSAGE);
        })
        .catch(error => setSessionNotice(childFriendlySessionMessage(error)));
    }, pauseDelay);

    return () => {
      window.clearTimeout(nudgeTimer);
      window.clearTimeout(pauseTimer);
    };
  }, [accessToken, brainBreakActive, childId, lastActivityAt, loading, onInactivePause, sessionId, sessionStatus?.session_status, trackingEnabled]);

  useEffect(() => {
    setTopic(prev => prev === subjectDefaults.Math || prev === subjectDefaults.ELA || prev === subjectDefaults.Writing ? subjectDefaults[subject] : prev);
    setMessages(prev => {
      if (prev.length === 1 && prev[0].role === 'msalisia') {
        return [{ role: 'msalisia', content: subjectGreeting(student.name, subject), subject }];
      }
      return prev;
    });
  }, [student.name, subject]);

  useEffect(() => {
    if (subject === lastAnnouncedSubject) return;
    setMessages(prev => [...prev, { role: 'msalisia', content: subjectSwitchMessage(subject), subject }]);
    setLastAnnouncedSubject(subject);
  }, [lastAnnouncedSubject, subject]);

  function applySubjectChange(nextSubject: Subject) {
    setSubject(nextSubject);
    setTopic(subjectDefaults[nextSubject]);
    setTopicSource('default');
  }

  async function startNewChat(nextSubject = subject) {
    setThreadError('');
    setActiveThread(null);
    setTutoringState(initialTutoringState);
    setMessages(greetingFor(nextSubject));
    setLastAnnouncedSubject(nextSubject);
    setSubject(nextSubject);
    setTopic(subjectDefaults[nextSubject]);
    setTopicSource('default');
  }

  async function openThread(thread: ChatThread) {
    if (!accessToken) return;
    setHistoryLoading(true);
    setThreadError('');
    try {
      const history = await getChatHistory(accessToken, thread.id, childId || undefined, studentSession);
      const nextSubject = thread.subject;
      setActiveThread(thread);
      setLastAnnouncedSubject(nextSubject);
      setSubject(nextSubject);
      setTopic(thread.topic || subjectDefaults[nextSubject]);
      setTopicSource('manual');
      setMessages(history.length ? history.map(message => ({
        role: message.role,
        content: message.content,
        provider: message.provider || undefined,
        subject: message.subject || nextSubject,
      })) : greetingFor(nextSubject));
      const latestState = [...history].reverse().find(message => message.tutoring_state)?.tutoring_state;
      setTutoringState(latestState || initialTutoringState);
    } catch (error) {
      if (isChatSetupPending(error)) {
        setHistorySetupPending(true);
        setThreadError('');
      } else {
        setThreadError(error instanceof Error ? error.message : 'Could not open this chat.');
      }
    } finally {
      setHistoryLoading(false);
    }
  }

  async function send() {
    if (!input.trim()) return;
    if (tutorDisabled) {
      setSessionNotice(sessionStatus?.message || DEFAULT_BRAIN_BREAK_MESSAGE);
      return;
    }
    const detectedSubject = detectSubjectFromMessage(input);
    const activeSubject = detectedSubject || subject;
    if (detectedSubject && detectedSubject !== subject) {
      applySubjectChange(detectedSubject);
    }

    const userMsg: ChatMessage = { role: 'student', content: input, subject: activeSubject };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    try {
      let thread = activeThread;
      if (thread && thread.subject !== activeSubject) {
        thread = null;
        setActiveThread(null);
      }
      const headers = accessToken ? { Authorization: `Bearer ${accessToken}`, ...(studentSession ? {} : { 'x-access-mode': 'child' }) } : undefined;
      const outgoingTopic = detectedSubject ? subjectDefaults[activeSubject] : topic;
      const outgoingTopicSource: TopicSource = detectedSubject ? 'default' : topicSource;
      await markStudentActivity('message_sent', activeSubject, outgoingTopic);
      const data = await apiPost<{ reply: string; provider: string; tutoring_state: TutoringState; thread_id?: string | null; history_saved?: boolean; history_error?: string | null; resolved_topic?: string | null; topic_source?: TopicSource | null; assessed_level?: string | null }>('/api/chat', { student, child_id: childId || undefined, subject: activeSubject, topic: outgoingTopic, topic_source: outgoingTopicSource, message: input, history: messages.slice(-4), tutoring_state: tutoringState, thread_id: thread?.id }, headers);
      setTutoringState(data.tutoring_state);
      if (accessToken && data.history_saved === false) {
        setHistorySetupPending(true);
        setThreadError('');
      } else {
        setHistorySetupPending(false);
        setThreadError('');
      }
      if (data.thread_id && (!thread || thread.id !== data.thread_id)) {
        const nextTopic = data.resolved_topic || outgoingTopic;
        setActiveThread({
          id: data.thread_id,
          user_id: '',
          child_id: childId || null,
          subject: activeSubject,
          topic: nextTopic,
          title: input.trim().slice(0, 48),
        });
        setTopic(nextTopic);
        setTopicSource('manual');
      }
      setMessages(prev => [...prev, { role: 'msalisia', content: data.reply, provider: data.provider, subject: activeSubject }]);
      if (data.history_saved !== false) {
        await refreshThreads();
      }
      if (trackingEnabled) {
        getSessionStatus(accessToken, childId).then(applySessionStatus).catch(error => setSessionNotice(childFriendlySessionMessage(error)));
      }
    } catch (error) {
      setThreadError(error instanceof Error ? error.message : 'The tutor request failed.');
      setMessages(prev => [...prev, { role: 'msalisia', content: 'Let us take one small step. Tell me what part feels confusing, and I will guide you with a quick example.', subject: activeSubject }]);
    } finally { setLoading(false); }
  }

  function applyQuickAction(prompt: string) {
    handleLocalActivity();
    onInputFromAction(prompt);
  }

  function onInputFromAction(prompt: string) {
    setInput(prompt);
  }

  function applySessionStatus(status: SessionStatusResponse) {
    setSessionStatus(status);
    setBrainBreakWarning(warningMessage(status.warnings_due));
    if (status.brain_break_active || status.brain_break_required) {
      setNudgeVisible(false);
      setSessionNotice(status.message || DEFAULT_BRAIN_BREAK_MESSAGE);
    } else if (status.session_status !== 'paused_inactive') {
      setSessionNotice('');
    }
  }

  function handleLocalActivity() {
    if (!trackingEnabled || brainBreakActive) return;
    setLastActivityAt(Date.now());
    setNudgeVisible(false);
    pauseRecordedRef.current = false;
    nudgeRecordedRef.current = false;
    const now = Date.now();
    if (now - lastActivityPingRef.current < SESSION_ACTIVITY_PING_MS) return;
    lastActivityPingRef.current = now;
    recordSessionActivity(accessToken, childId, subject, topic, sessionId, 'activity')
      .then(applySessionStatus)
      .catch(error => setSessionNotice(childFriendlySessionMessage(error)));
  }

  async function markStudentActivity(eventType: string, activeSubject = subject, activeTopic = topic) {
    handleLocalActivity();
    if (!trackingEnabled) return;
    try {
      const status = await recordSessionActivity(accessToken, childId, activeSubject, activeTopic, sessionId, eventType);
      applySessionStatus(status);
    } catch (error) {
      setSessionNotice(childFriendlySessionMessage(error));
    }
  }

  async function handleBackFromNudge() {
    setNudgeVisible(false);
    setLastActivityAt(Date.now());
    pauseRecordedRef.current = false;
    nudgeRecordedRef.current = false;
    if (!trackingEnabled) return;
    try {
      const status = await resumeSession(accessToken, childId, sessionId);
      applySessionStatus(status);
    } catch (error) {
      setSessionNotice(childFriendlySessionMessage(error));
    }
  }

  return <div className="page-stack">
    <SectionHeader eyebrow="Learning with Ms Alisia" title="Short, guided tutoring by subject" desc="The LLM prompt keeps answers course-related, age-appropriate, brief, encouraging, and focused on one validation question." />
    <div className="learning-layout">
      <ChatThreadList
        threads={threads}
        activeThreadId={activeThread?.id}
        loading={threadLoading}
        error={threadError}
        notice={historySetupPending ? chatSetupNotice : ''}
        onNewChat={() => startNewChat()}
        onOpenThread={openThread}
      />
      <ChatWorkspace
        messages={messages}
        input={input}
        loading={loading}
        historyLoading={historyLoading}
        tutoringState={tutoringState}
        disabled={tutorDisabled}
        disabledMessage={sessionNotice}
        inactivityNudge={nudgeVisible ? { message: `Still there, ${student.name}? Ms. Alisia is waiting for you!`, onBack: handleBackFromNudge } : null}
        brainBreak={brainBreakActive ? {
          active: true,
          message: sessionStatus?.message || DEFAULT_BRAIN_BREAK_MESSAGE,
          secondsUntilResume: sessionStatus?.seconds_until_resume || 0,
        } : null}
        brainBreakWarning={brainBreakWarning}
        onActivity={handleLocalActivity}
        onInputChange={setInput}
        onSend={send}
        onQuickAction={applyQuickAction}
      />
      <LearningContextPanel
        student={student}
        subject={subject}
        topic={topic}
        onSubjectChange={applySubjectChange}
        onTopicChange={(nextTopic) => {
          setTopic(nextTopic);
          setTopicSource('manual');
        }}
      />
    </div>
  </div>;
}

function warningMessage(warnings: string[]): string {
  if (warnings.includes('30_minute_warning')) return 'You have about 30 minutes before Brain Break time.';
  if (warnings.includes('10_minute_warning')) return 'You have about 10 minutes before Brain Break time.';
  if (warnings.includes('5_minute_warning')) return 'You have about 5 minutes before Brain Break time.';
  return '';
}

function childFriendlySessionMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const lower = message.toLowerCase();
  if (lower.includes('brain break')) return DEFAULT_BRAIN_BREAK_MESSAGE;
  if (lower.includes('payment') || lower.includes('billing') || lower.includes('subscription') || lower.includes('access')) {
    return 'There is something your parent needs to take care of before learning can continue.';
  }
  if (lower.includes('student session') || lower.includes('not allowed') || lower.includes('unauthorized')) {
    return 'Please log in again from your student account to keep learning.';
  }
  return message || 'Something got stuck. Please try again in a moment.';
}

function isChatSetupPending(error: unknown): boolean {
  const message = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
  return message.includes('chat history is not set up')
    || message.includes('chat_threads.child_id')
    || message.includes('chat_messages.child_id')
    || (message.includes('child_id') && (message.includes('does not exist') || message.includes('schema cache')));
}
