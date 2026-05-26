import { SignupForm } from '../components/auth/SignupForm';
import { startSignup } from '../lib/api/auth';
import { PendingVerification, SignupFormValues } from '../types/auth';

export function Signup({
  onPendingVerification,
  onLogin
}: {
  onPendingVerification: (pending: PendingVerification) => void;
  onLogin: () => void;
}) {
  async function submit(values: SignupFormValues) {
    const result = await startSignup(values);
    onPendingVerification({
      email: result.email,
      expires_in_minutes: result.expires_in_minutes,
      message: result.message
    });
  }

  return <SignupForm onSubmit={submit} onLogin={onLogin} />;
}
