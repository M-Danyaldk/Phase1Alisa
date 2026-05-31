export type SignupFormValues = {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  referral_code?: string;
  coppa_parent_consent_accepted: boolean;
};

export type SignupStartResponse = {
  email: string;
  expires_in_minutes: number;
  message: string;
  trial_available?: boolean;
  paid_checkout_required?: boolean;
  trial_blocked_reason?: string | null;
};

export type AuthUser = {
  id: string;
  email?: string | null;
};

export type AuthSessionResponse = {
  access_token?: string | null;
  refresh_token?: string | null;
  expires_in?: number | null;
  token_type?: string | null;
  user?: AuthUser | null;
  message: string;
  trial_available?: boolean;
  paid_checkout_required?: boolean;
  trial_blocked_reason?: string | null;
};

export type ProfileResponse = {
  id: string;
  full_name: string;
  email: string;
  role?: 'parent' | 'student' | 'admin' | 'super_admin';
  status?: 'active' | 'suspended' | 'inactive';
  admin_permissions?: string[];
  admin_2fa_enabled?: boolean;
  avatar_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ProfileUpdateValues = {
  full_name: string;
};

export type PendingVerification = {
  email: string;
  expires_in_minutes: number;
  message?: string;
};

export type ForgotPasswordResponse = {
  message: string;
};

export type VerifyResetCodeResponse = {
  reset_allowed: boolean;
  message: string;
};

export type ResetPasswordResponse = {
  message: string;
};
