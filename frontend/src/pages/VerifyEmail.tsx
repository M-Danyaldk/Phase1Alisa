import { VerificationCodeForm } from '../components/auth/VerificationCodeForm';
import { resendSignupCode, verifySignup } from '../lib/api/auth';
import { AuthSessionResponse, PendingVerification } from '../types/auth';

export function VerifyEmail({
  pending,
  onPendingChange,
  onVerified,
  onBack
}: {
  pending: PendingVerification;
  onPendingChange: (pending: PendingVerification) => void;
  onVerified: (session: AuthSessionResponse) => void;
  onBack: () => void;
}) {
  async function submit(code: string) {
    const result = await verifySignup(pending.email, code);
    onVerified(result);
  }

  async function resend() {
    const result = await resendSignupCode(pending.email);
    onPendingChange({
      email: result.email,
      demo_code: result.demo_code,
      expires_in_minutes: result.expires_in_minutes
    });
  }

  return <VerificationCodeForm pending={pending} onSubmit={submit} onResend={resend} onBack={onBack} />;
}
