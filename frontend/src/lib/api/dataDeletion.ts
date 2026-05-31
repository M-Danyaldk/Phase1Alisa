import { apiPost } from '../api';

export type DataDeletionPayload = {
  parent_name: string;
  email: string;
  child_name?: string;
  request_details?: string;
  confirmation_accepted: boolean;
};

export type DataDeletionResponse = {
  success: boolean;
  message: string;
};

export function submitDataDeletionRequest(payload: DataDeletionPayload, accessToken?: string): Promise<DataDeletionResponse> {
  const headers = accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined;
  return apiPost<DataDeletionResponse>('/api/data-deletion/request', payload, headers);
}
