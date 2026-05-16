import { apiGet } from '../api';
import { ChildReport, WeeklyReportEmailPreview } from '../../types/childReport';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export async function getChildReport(accessToken: string, childId: string): Promise<ChildReport> {
  return apiGet<ChildReport>(`/children/${childId}/report`, authHeaders(accessToken));
}

export async function getFilteredChildReport(accessToken: string, childId: string, period: string, subject: string): Promise<ChildReport> {
  const params = new URLSearchParams({ period, subject });
  return apiGet<ChildReport>(`/children/${childId}/report?${params.toString()}`, authHeaders(accessToken));
}

export async function getWeeklyEmailPreview(accessToken: string, childId: string): Promise<WeeklyReportEmailPreview> {
  return apiGet<WeeklyReportEmailPreview>(`/children/${childId}/weekly-email-preview`, authHeaders(accessToken));
}
