import { apiDelete, apiGet, apiPatch, apiPost } from '../api';
import { ChildProfile, ChildProfileFormValues } from '../../types/childProfile';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

function payloadFromForm(values: ChildProfileFormValues) {
  return {
    ...values,
    date_of_birth: values.date_of_birth || null,
  };
}

export async function listChildren(accessToken: string): Promise<ChildProfile[]> {
  const data = await apiGet<{ children: ChildProfile[] }>('/children', authHeaders(accessToken));
  return data.children;
}

export async function createChild(accessToken: string, values: ChildProfileFormValues): Promise<ChildProfile> {
  return apiPost<ChildProfile>('/children', payloadFromForm(values), authHeaders(accessToken));
}

export async function updateChild(accessToken: string, childId: string, values: ChildProfileFormValues & { status?: ChildProfile['status'] }): Promise<ChildProfile> {
  return apiPatch<ChildProfile>(`/children/${childId}`, { ...payloadFromForm(values), status: values.status || 'active' }, authHeaders(accessToken));
}

export async function deactivateChild(accessToken: string, childId: string): Promise<ChildProfile> {
  return apiDelete<ChildProfile>(`/children/${childId}`, authHeaders(accessToken));
}

export async function reactivateChild(accessToken: string, childId: string): Promise<ChildProfile> {
  return apiPost<ChildProfile>(`/children/${childId}/reactivate`, {}, authHeaders(accessToken));
}
