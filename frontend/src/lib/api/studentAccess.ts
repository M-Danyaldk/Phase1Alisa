import { apiGet, apiPut } from '../api';
import { StudentAccess, StudentAccessFormValues } from '../../types/studentAccess';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getStudentAccess(accessToken: string, childId: string): Promise<StudentAccess | null> {
  return apiGet<StudentAccess | null>(`/children/${childId}/student-access`, authHeaders(accessToken));
}

export async function saveStudentAccess(accessToken: string, childId: string, values: StudentAccessFormValues): Promise<StudentAccess> {
  return apiPut<StudentAccess>(`/children/${childId}/student-access`, values, authHeaders(accessToken));
}
