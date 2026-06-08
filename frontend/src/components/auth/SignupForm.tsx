import { useState } from 'react';
import { SignupFormValues } from '../../types/auth';

const initialValues: SignupFormValues = {
  full_name: '',
  email: '',
  password: '',
  confirm_password: '',
  coppa_parent_consent_accepted: false,
};

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function validate(values: SignupFormValues): string {
  if (!values.full_name.trim()) return 'Parent/guardian full name is required.';
  if (!values.email.trim()) return 'Parent email is required.';
  if (!isValidEmail(values.email)) return 'Please enter a valid email address.';
  if (!values.password) return 'Password is required.';
  if (values.password.length < 6) return 'Password must be at least 6 characters.';
  if (values.confirm_password !== values.password) return 'Confirm password must match password.';
  if (!values.coppa_parent_consent_accepted) return 'Please confirm parent/guardian consent before continuing.';
  return '';
}

export function SignupForm({ onSubmit, onLogin }: { onSubmit: (values: SignupFormValues) => Promise<void>; onLogin: () => void }) {
  const [values, setValues] = useState<SignupFormValues>(initialValues);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit() {
    const validationError = validate(values);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError('');
    setLoading(true);
    try {
      await onSubmit(values);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not start signup. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="auth-panel">
    <div className="auth-heading">
      <span>Create Account</span>
      <h2>Start learning with MsAlisia</h2>
      <p>Your child's brilliant tutor - patient, adaptive, available whenever they need one. MsAlisia learns how your child thinks, adapts to their level, and keeps you informed, so you can relax knowing they're in good hands.</p>
    </div>
    <div className="auth-form">
      <label>Parent/guardian full name<input value={values.full_name} onChange={e => setValues({ ...values, full_name: e.target.value })} /></label>
      <label>Parent email<input type="email" value={values.email} onChange={e => setValues({ ...values, email: e.target.value })} /></label>
      <label>Password<input type="password" value={values.password} onChange={e => setValues({ ...values, password: e.target.value })} /></label>
      <label>Confirm Password<input type="password" value={values.confirm_password} onChange={e => setValues({ ...values, confirm_password: e.target.value })} /></label>
      <label className="checkbox-row consent-row">
        <input
          type="checkbox"
          checked={values.coppa_parent_consent_accepted}
          onChange={e => setValues({ ...values, coppa_parent_consent_accepted: e.target.checked })}
        />
        <span>I confirm that I am the parent or legal guardian of the child or children I am enrolling and I consent to the collection and use of my child's information for MsAlisia learning services.</span>
      </label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Creating...' : 'Create Account'}</button>
      <button className="link-button" onClick={onLogin} type="button">Already have an account? Log in</button>
    </div>
  </div>;
}
