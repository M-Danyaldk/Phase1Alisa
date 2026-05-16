import { useMemo, useState } from 'react';
import { ChatThread } from '../lib/chatApi';
import { classNames } from '../lib/classNames';
import { Subject } from '../types';

type Props = {
  threads: ChatThread[];
  activeThreadId?: string;
  loading: boolean;
  error: string;
  notice?: string;
  onNewChat: () => void;
  onOpenThread: (thread: ChatThread) => void;
};

export function ChatThreadList({ threads, activeThreadId, loading, error, notice = '', onNewChat, onOpenThread }: Props) {
  const [search, setSearch] = useState('');

  const filteredThreads = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return threads;
    return threads.filter(thread => {
      const title = thread.title || thread.topic || `${thread.subject} chat`;
      return `${title} ${thread.subject} ${thread.topic || ''}`.toLowerCase().includes(needle);
    });
  }, [search, threads]);

  return <aside className="thread-sidebar" aria-label="Chat threads">
    <div className="thread-sidebar-header">
      <div>
        <span>Chats</span>
        <strong>Previous chats</strong>
      </div>
      <button className="secondary-button compact" onClick={onNewChat} disabled={loading} aria-label="Start a new chat">New Chat</button>
    </div>
    <label className="thread-search">Search
      <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Find a chat" aria-label="Search previous chats" />
    </label>
    {error && <p className="error-note">{error}</p>}
    {!error && notice && <p className="muted-note">{notice}</p>}
    {loading && <p className="muted-note">Loading chats...</p>}
    {!loading && threads.length === 0 && <p className="muted-note">No saved chats yet.</p>}
    {!loading && threads.length > 0 && filteredThreads.length === 0 && <p className="muted-note">No chats match that search.</p>}
    <div className="thread-list">
      {filteredThreads.map(thread => <button
        key={thread.id}
        className={classNames('thread-item', activeThreadId === thread.id ? 'active' : '')}
        onClick={() => onOpenThread(thread)}
        aria-label={`Open ${thread.subject} chat ${thread.title || thread.topic || ''}`.trim()}
      >
        <span className={classNames('subject-badge', subjectBadgeClass(thread.subject))}>{thread.subject}</span>
        <strong>{thread.title || thread.topic || `${thread.subject} chat`}</strong>
        <small>{thread.updated_at ? new Date(thread.updated_at).toLocaleString() : 'New chat'}</small>
      </button>)}
    </div>
  </aside>;
}

function subjectBadgeClass(subject: Subject): string {
  if (subject === 'ELA') return 'ela';
  if (subject === 'Writing') return 'writing';
  return 'math';
}
