import { LoginForm } from '../components/auth/LoginForm';
import { login } from '../lib/api/auth';
import { AuthSessionResponse } from '../types/auth';

export function Login({ onLoggedIn, onSignup }: { onLoggedIn: (session: AuthSessionResponse) => void; onSignup: () => void }) {
  async function submit(email: string, password: string) {
    const result = await login(email, password);
    onLoggedIn(result);
  }

  return <LoginForm onSubmit={submit} onSignup={onSignup} />;
}
