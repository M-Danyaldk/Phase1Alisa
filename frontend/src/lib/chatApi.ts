import { apiGet, apiPost } from './api';
import { Subject, TutoringState } from '../types';

export type ChatThread = {
  id: string;
  user_id: string;
  child_id?: string | null;
  subject: Subject;
  topic?: string | null;
  title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type StoredChatMessage = {
  id: string;
  thread_id: string;
  user_id: string;
  child_id?: string | null;
  role: 'student' | 'msalisia';
  content: string;
  subject?: Subject | string | null;
  topic?: string | null;
  provider?: string | null;
  model?: string | null;
  tutoring_state?: TutoringState | null;
  created_at?: string | null;
};

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getChatThreads(accessToken: string, subject?: Subject): Promise<ChatThread[]> {
  const params = new URLSearchParams();
  if (subject) params.set('subject', subject);
  const query = params.toString() ? `?${params.toString()}` : '';
  const data = await apiGet<{ threads: ChatThread[] }>(`/chat/threads${query}`, authHeaders(accessToken));
  return data.threads;
}

export async function getChildChatThreads(accessToken: string, childId: string, subject?: Subject): Promise<ChatThread[]> {
  const params = new URLSearchParams({ child_id: childId });
  if (subject) params.set('subject', subject);
  const data = await apiGet<{ threads: ChatThread[] }>(`/chat/threads?${params.toString()}`, authHeaders(accessToken));
  return data.threads;
}

export async function createChatThread(accessToken: string, payload: { subject: Subject; topic: string; title?: string; child_id?: string }): Promise<ChatThread> {
  return apiPost<ChatThread>('/chat/threads', payload, authHeaders(accessToken));
}

export async function getChatHistory(accessToken: string, threadId: string, childId?: string): Promise<StoredChatMessage[]> {
  const params = new URLSearchParams({ thread_id: threadId });
  if (childId) params.set('child_id', childId);
  const data = await apiGet<{ messages: StoredChatMessage[] }>(`/chat/history?${params.toString()}`, authHeaders(accessToken));
  return data.messages;
}
