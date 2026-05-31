import { apiPost } from '../api';
import { ProblemReportPayload, ProblemReportResponse } from '../../types/problemReports';

function authHeaders(accessToken: string, studentSession: boolean): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}`, ...(studentSession ? {} : {}) };
}

export function sendProblemReport(
  accessToken: string,
  payload: ProblemReportPayload,
  studentSession = true,
): Promise<ProblemReportResponse> {
  return apiPost<ProblemReportResponse>('/api/problem-reports', payload, authHeaders(accessToken, studentSession));
}
