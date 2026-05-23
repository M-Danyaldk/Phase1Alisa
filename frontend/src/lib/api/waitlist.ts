import { apiPost } from '../api';

export type WaitlistSignupResponse = {
  success: boolean;
  message: string;
};

export function joinWaitlist(email: string): Promise<WaitlistSignupResponse> {
  return apiPost<WaitlistSignupResponse>('/api/waitlist/signup', { email });
}
