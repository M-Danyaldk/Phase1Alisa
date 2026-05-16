import { apiGet, apiPatch } from '../api';
import { ChildAccess, ChildAccessStatus } from '../../types/billing';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function listChildAccess(accessToken: string): Promise<ChildAccess[]> {
  const data = await apiGet<{ children: ChildAccess[] }>('/billing/children', authHeaders(accessToken));
  return data.children;
}

export async function updateChildAccess(accessToken: string, childId: string, accessStatus: ChildAccessStatus): Promise<ChildAccess> {
  return apiPatch<ChildAccess>(`/billing/children/${childId}`, {
    access_status: accessStatus,
    plan_name: 'Phase 1 MVP',
  }, authHeaders(accessToken));
}
