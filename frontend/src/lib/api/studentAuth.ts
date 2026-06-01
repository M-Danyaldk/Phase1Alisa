import { apiGet, apiPost } from '../api';
import { ClassroomContext, StudentMe, StudentSession } from '../../types/studentSession';

function studentHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export function createClassroomContext(accessToken: string, childId: string): Promise<ClassroomContext> {
  return apiPost<ClassroomContext>(`/children/${encodeURIComponent(childId)}/classroom-context`, {}, studentHeaders(accessToken));
}

export function studentLogin(classroomContextToken: string, username: string, pin: string): Promise<StudentSession> {
  return apiPost<StudentSession>('/student/login', {
    classroom_context_token: classroomContextToken,
    username: username.trim().toLowerCase(),
    pin,
  });
}

export function getStudentMe(token: string): Promise<StudentMe> {
  return apiGet<StudentMe>('/student/me', studentHeaders(token));
}

export function studentLogout(token: string): Promise<{ message: string }> {
  return apiPost<{ message: string }>('/student/logout', {}, studentHeaders(token));
}
