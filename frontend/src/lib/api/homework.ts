import { apiGet, apiPostForm } from '../api';
import { HomeworkHistoryResponse, HomeworkUpload } from '../../types/homework';

const HOMEWORK_ACCEPT = 'image/jpeg,image/png,image/heic,image/heif,application/pdf';

function authHeaders(accessToken: string, childMode = false): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}`, ...(childMode ? {} : { 'x-access-mode': 'child' }) };
}

export function homeworkAcceptTypes(): string {
  return HOMEWORK_ACCEPT;
}

export async function uploadStudentHomework(accessToken: string, childId: string, file: File, studentSession = true): Promise<HomeworkUpload> {
  const payload = new FormData();
  payload.append('child_id', childId);
  payload.append('file', file);
  return apiPostForm<HomeworkUpload>('/api/homework/upload', payload, authHeaders(accessToken, studentSession));
}

export async function uploadParentHomework(accessToken: string, childId: string, file: File): Promise<HomeworkUpload> {
  const payload = new FormData();
  payload.append('child_id', childId);
  payload.append('file', file);
  return apiPostForm<HomeworkUpload>('/api/parent/homework/upload', payload, { Authorization: `Bearer ${accessToken}` });
}

export async function getStudentHomeworkHistory(accessToken: string, childId: string, studentSession = true): Promise<HomeworkHistoryResponse> {
  return apiGet<HomeworkHistoryResponse>(`/api/homework/history?child_id=${encodeURIComponent(childId)}`, authHeaders(accessToken, studentSession));
}

export async function getParentHomeworkHistory(accessToken: string, childId: string): Promise<HomeworkHistoryResponse> {
  return apiGet<HomeworkHistoryResponse>(`/api/homework/child/${encodeURIComponent(childId)}/history`, { Authorization: `Bearer ${accessToken}` });
}
