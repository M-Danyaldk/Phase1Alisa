import { apiPost } from '../api';

export type WaitlistSignupResponse = {
  success: boolean;
  message: string;
};

export type WaitlistSignupPayload = {
  parent_name?: string;
  email: string;
  child_grade?: string;
  interest_note?: string;
};

export function joinWaitlist(payload: WaitlistSignupPayload): Promise<WaitlistSignupResponse> {
  return apiPost<WaitlistSignupResponse>('/api/waitlist/signup', payload);
}
