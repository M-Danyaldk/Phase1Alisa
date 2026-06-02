import { apiGet, apiPost } from '../api';
import { FamilyClassroomLink, StudentMe, StudentSession } from '../../types/studentSession';

function studentHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export function getFamilyClassroomLink(accessToken: string): Promise<FamilyClassroomLink> {
  return apiGet<FamilyClassroomLink>('/student/family-classroom-link', studentHeaders(accessToken));
}

export function studentLogin(familyCode: string, username: string, pin: string): Promise<StudentSession> {
  return apiPost<StudentSession>('/student/login', {
    family_code: familyCode,
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
