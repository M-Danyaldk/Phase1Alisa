import { SignupForm } from '../components/auth/SignupForm';
import { startSignup } from '../lib/api/auth';
import { PendingVerification, SignupFormValues } from '../types/auth';

const REFERRAL_CODE_KEY = 'msalisia-referral-code';

export function Signup({
  onPendingVerification,
  onLogin
}: {
  onPendingVerification: (pending: PendingVerification) => void;
  onLogin: () => void;
}) {
  async function submit(values: SignupFormValues) {
    const referralCode = localStorage.getItem(REFERRAL_CODE_KEY) || '';
    const result = await startSignup({ ...values, referral_code: referralCode || values.referral_code });
    onPendingVerification({
      email: result.email,
      expires_in_minutes: result.expires_in_minutes,
      message: result.message
    });
  }

  return <SignupForm onSubmit={submit} onLogin={onLogin} />;
}
