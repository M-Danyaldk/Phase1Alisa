import { useState } from 'react';
import { ForgotPasswordForm } from '../components/auth/ForgotPasswordForm';
import { LoginForm } from '../components/auth/LoginForm';
import { ResetCodeForm } from '../components/auth/ResetCodeForm';
import { ResetPasswordForm } from '../components/auth/ResetPasswordForm';
import { forgotPassword, login, resetPassword, verifyResetCode } from '../lib/api/auth';
import { AuthSessionResponse } from '../types/auth';

export function Login({ onLoggedIn, onSignup }: { onLoggedIn: (session: AuthSessionResponse) => Promise<void> | void; onSignup: () => void }) {
  const [mode, setMode] = useState<'login' | 'forgot' | 'code' | 'reset'>('login');
  const [resetEmail, setResetEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [notice, setNotice] = useState('');

  async function submit(email: string, password: string) {
    const result = await login(email, password);
    await onLoggedIn(result);
  }

  async function submitForgot(email: string) {
    const result = await forgotPassword(email);
    setResetEmail(email);
    setNotice(result.message);
    setMode('code');
  }

  async function submitCode(code: string) {
    await verifyResetCode(resetEmail, code);
    setResetCode(code);
    setMode('reset');
  }

  async function submitReset(password: string, confirmPassword: string) {
    const result = await resetPassword(resetEmail, resetCode, password, confirmPassword);
    setNotice(result.message);
    setResetEmail('');
    setResetCode('');
    setMode('login');
  }

  function backToLogin() {
    setMode('login');
    setResetEmail('');
    setResetCode('');
  }

  if (mode === 'forgot') {
    return <ForgotPasswordForm onSubmit={submitForgot} onBack={backToLogin} />;
  }

  if (mode === 'code') {
    return <ResetCodeForm email={resetEmail} message={notice} onSubmit={submitCode} onBack={() => setMode('forgot')} />;
  }

  if (mode === 'reset') {
    return <ResetPasswordForm onSubmit={submitReset} onBack={backToLogin} />;
  }

  return <LoginForm onSubmit={submit} onSignup={onSignup} onForgotPassword={() => {
    setNotice('');
    setMode('forgot');
  }} notice={notice} />;
}
