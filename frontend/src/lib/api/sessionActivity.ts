import { apiGet, apiPost } from '../api';
import { Subject } from '../../types';
import { SessionStatusResponse } from '../../types/sessionActivity';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

function childQuery(childId: string): string {
  return encodeURIComponent(childId);
}

export async function getSessionStatus(accessToken: string, childId: string): Promise<SessionStatusResponse> {
  return apiGet<SessionStatusResponse>(`/api/session/status?child_id=${childQuery(childId)}`, authHeaders(accessToken));
}

export async function getBrainBreakStatus(accessToken: string, childId: string): Promise<SessionStatusResponse> {
  return apiGet<SessionStatusResponse>(`/api/session/brain-break/status?child_id=${childQuery(childId)}`, authHeaders(accessToken));
}

export async function recordSessionActivity(
  accessToken: string,
  childId: string,
  subject: Subject,
  topic: string,
  sessionId?: string | null,
  eventType = 'activity',
): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>('/api/session/activity', {
    child_id: childId,
    subject,
    topic,
    session_id: sessionId || undefined,
    event_type: eventType,
  }, authHeaders(accessToken));
}

export async function recordInactivityNudge(
  accessToken: string,
  childId: string,
  sessionId?: string | null,
): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>('/api/session/inactivity-nudge', {
    child_id: childId,
    session_id: sessionId || undefined,
  }, authHeaders(accessToken));
}

export async function pauseInactiveSession(
  accessToken: string,
  childId: string,
  sessionId?: string | null,
  inactiveSeconds = 180,
): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>('/api/session/pause-inactive', {
    child_id: childId,
    session_id: sessionId || undefined,
    inactive_seconds: inactiveSeconds,
  }, authHeaders(accessToken));
}

export async function resumeSession(
  accessToken: string,
  childId: string,
  sessionId?: string | null,
): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>('/api/session/resume', {
    child_id: childId,
    session_id: sessionId || undefined,
  }, authHeaders(accessToken));
}
