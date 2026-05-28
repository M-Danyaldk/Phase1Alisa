import { AuthSessionResponse, ForgotPasswordResponse, ProfileResponse, ProfileUpdateValues, ResetPasswordResponse, SignupFormValues, SignupStartResponse, VerifyResetCodeResponse } from '../../types/auth';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function authPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    if (Array.isArray(detail)) {
      throw new Error(detail[0]?.msg || 'Request failed.');
    }
    throw new Error(detail || 'Request failed.');
  }
  return response.json();
}

async function authGet<T>(path: string, accessToken: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Request failed.');
  }
  return response.json();
}

async function authPatch<T>(path: string, accessToken: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    if (Array.isArray(detail)) {
      throw new Error(detail[0]?.msg || 'Request failed.');
    }
    throw new Error(detail || 'Request failed.');
  }
  return response.json();
}

export function startSignup(payload: SignupFormValues): Promise<SignupStartResponse> {
  return authPost<SignupStartResponse>('/auth/start-signup', payload);
}

export function verifySignup(email: string, code: string): Promise<AuthSessionResponse> {
  return authPost<AuthSessionResponse>('/auth/verify-signup', { email, code });
}

export function resendSignupCode(email: string): Promise<SignupStartResponse> {
  return authPost<SignupStartResponse>('/auth/resend-code', { email });
}

export function login(email: string, password: string): Promise<AuthSessionResponse> {
  return authPost<AuthSessionResponse>('/auth/login', { email, password });
}

export function forgotPassword(email: string): Promise<ForgotPasswordResponse> {
  return authPost<ForgotPasswordResponse>('/auth/forgot-password', { email: email.trim().toLowerCase() });
}

export function verifyResetCode(email: string, code: string): Promise<VerifyResetCodeResponse> {
  return authPost<VerifyResetCodeResponse>('/auth/verify-reset-code', { email: email.trim().toLowerCase(), code });
}

export function resetPassword(email: string, code: string, newPassword: string, confirmPassword: string): Promise<ResetPasswordResponse> {
  return authPost<ResetPasswordResponse>('/auth/reset-password', {
    email: email.trim().toLowerCase(),
    code,
    new_password: newPassword,
    confirm_password: confirmPassword,
  });
}

export function getCurrentProfile(accessToken: string): Promise<ProfileResponse> {
  return authGet<ProfileResponse>('/auth/me', accessToken);
}

export function updateCurrentProfile(accessToken: string, values: ProfileUpdateValues): Promise<ProfileResponse> {
  return authPatch<ProfileResponse>('/auth/me', accessToken, values);
}

export async function uploadProfileAvatar(accessToken: string, file: File): Promise<ProfileResponse> {
  const payload = new FormData();
  payload.append('file', file);
  const response = await fetch(`${API_BASE}/auth/me/avatar`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: payload
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Could not upload profile photo.');
  }
  return response.json();
}
