import { apiGet } from '../api';
import { ReferralSummary } from '../../types/referrals';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getMyReferrals(accessToken: string): Promise<ReferralSummary> {
  return apiGet<ReferralSummary>('/api/referrals/me', authHeaders(accessToken));
}
