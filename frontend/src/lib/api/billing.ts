import { apiGet, apiPatch, apiPost } from '../api';
import { BillingPlan, BillingPlanKey, ChildAccess, ChildAccessStatus } from '../../types/billing';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function listChildAccess(accessToken: string): Promise<ChildAccess[]> {
  const data = await apiGet<{ children: ChildAccess[] }>('/billing/children', authHeaders(accessToken));
  return data.children;
}

export async function listBillingPlans(): Promise<BillingPlan[]> {
  const data = await apiGet<{ plans: BillingPlan[] }>('/billing/plans');
  return data.plans;
}

export async function updateChildAccess(accessToken: string, childId: string, accessStatus: ChildAccessStatus): Promise<ChildAccess> {
  return apiPatch<ChildAccess>(`/billing/children/${childId}`, {
    access_status: accessStatus,
    plan_name: 'Phase 1 MVP',
  }, authHeaders(accessToken));
}

export async function createCheckoutSession(accessToken: string, childId: string, planKey: BillingPlanKey): Promise<string> {
  const data = await apiPost<{ checkout_url: string; session_id: string }>('/billing/checkout/session', {
    child_id: childId,
    plan_key: planKey,
  }, authHeaders(accessToken));
  return data.checkout_url;
}

export async function createCustomerPortalSession(accessToken: string, childId?: string): Promise<string> {
  const data = await apiPost<{ portal_url: string; session_id: string }>('/billing/portal/session', {
    child_id: childId || null,
  }, authHeaders(accessToken));
  return data.portal_url;
}
