import { apiDelete, apiGet, apiPost } from '../api';
import { Subject } from '../../types';
import { WorkingLevelOverridesResponse } from '../../types/workingLevelOverrides';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getWorkingLevelOverrides(accessToken: string, childId: string): Promise<WorkingLevelOverridesResponse> {
  return apiGet<WorkingLevelOverridesResponse>(`/children/${childId}/working-level-overrides`, authHeaders(accessToken));
}

export async function setWorkingLevelOverride(accessToken: string, childId: string, subject: Subject, unlockedGradeLevel: string): Promise<WorkingLevelOverridesResponse> {
  return apiPost<WorkingLevelOverridesResponse>(`/children/${childId}/working-level-overrides`, {
    subject,
    unlocked_grade_level: unlockedGradeLevel,
  }, authHeaders(accessToken));
}

export async function resetWorkingLevelOverride(accessToken: string, childId: string, subject: Subject): Promise<WorkingLevelOverridesResponse> {
  return apiDelete<WorkingLevelOverridesResponse>(`/children/${childId}/working-level-overrides/${encodeURIComponent(subject)}`, authHeaders(accessToken));
}
