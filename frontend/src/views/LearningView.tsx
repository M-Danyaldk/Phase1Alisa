import { useEffect, useState } from 'react';
import { ChatThreadList } from '../components/ChatThreadList';
import { ChatWorkspace } from '../components/ChatWorkspace';
import { LearningContextPanel } from '../components/LearningContextPanel';
import { SectionHeader } from '../components/SectionHeader';
import { apiPost } from '../lib/api';
import { ChatThread, getChatHistory, getChatThreads, getChildChatThreads } from '../lib/chatApi';
import { ChatMessage, StudentProfile, Subject, TutoringState } from '../types';

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

export function LearningView({ student, accessToken = '', childId = '', initialSubject = 'Math', studentSession = false }: { student: StudentProfile; accessToken?: string; childId?: string; initialSubject?: Subject; studentSession?: boolean }) {
  const initialTutoringState: TutoringState = { active_problem: '', current_step: '', attempt_count: 0, answer_revealed: false, mode: 'solve', status: 'idle', memory_note: '' };
  const chatSetupNotice = 'Chat worked, but history was not saved. Please check Supabase setup.';
  const [subject, setSubject] = useState<Subject>(initialSubject);
  const [topic, setTopic] = useState(subjectDefaults[initialSubject]);
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
    setLastAnnouncedSubject(initialSubject);
    setMessages(greetingFor(initialSubject));
    refreshThreads();
  }, [accessToken, childId, initialSubject]);

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
  }

  async function startNewChat(nextSubject = subject) {
    setThreadError('');
    setActiveThread(null);
    setTutoringState(initialTutoringState);
    setMessages(greetingFor(nextSubject));
    setLastAnnouncedSubject(nextSubject);
    setSubject(nextSubject);
    setTopic(subjectDefaults[nextSubject]);
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
      const data = await apiPost<{ reply: string; provider: string; tutoring_state: TutoringState; thread_id?: string | null; history_saved?: boolean; history_error?: string | null }>('/api/chat', { student, child_id: childId || undefined, subject: activeSubject, topic: detectedSubject ? subjectDefaults[activeSubject] : topic, message: input, history: messages.slice(-4), tutoring_state: tutoringState, thread_id: thread?.id }, headers);
      setTutoringState(data.tutoring_state);
      if (accessToken && data.history_saved === false) {
        setHistorySetupPending(true);
        setThreadError('');
      } else {
        setHistorySetupPending(false);
        setThreadError('');
      }
      if (data.thread_id && (!thread || thread.id !== data.thread_id)) {
        setActiveThread({
          id: data.thread_id,
          user_id: '',
          child_id: childId || null,
          subject: activeSubject,
          topic: detectedSubject ? subjectDefaults[activeSubject] : topic,
          title: input.trim().slice(0, 48),
        });
      }
      setMessages(prev => [...prev, { role: 'msalisia', content: data.reply, provider: data.provider, subject: activeSubject }]);
      if (data.history_saved !== false) {
        await refreshThreads();
      }
    } catch (error) {
      setThreadError(error instanceof Error ? error.message : 'The tutor request failed.');
      setMessages(prev => [...prev, { role: 'msalisia', content: 'Let us take one small step. Tell me what part feels confusing, and I will guide you with a quick example.', subject: activeSubject }]);
    } finally { setLoading(false); }
  }

  function applyQuickAction(prompt: string) {
    onInputFromAction(prompt);
  }

  function onInputFromAction(prompt: string) {
    setInput(prompt);
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
        onInputChange={setInput}
        onSend={send}
        onQuickAction={applyQuickAction}
      />
      <LearningContextPanel
        student={student}
        subject={subject}
        topic={topic}
        onSubjectChange={applySubjectChange}
        onTopicChange={setTopic}
      />
    </div>
  </div>;
}

function isChatSetupPending(error: unknown): boolean {
  const message = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
  return message.includes('chat history is not set up')
    || message.includes('chat_threads.child_id')
    || message.includes('chat_messages.child_id')
    || (message.includes('child_id') && (message.includes('does not exist') || message.includes('schema cache')));
}
