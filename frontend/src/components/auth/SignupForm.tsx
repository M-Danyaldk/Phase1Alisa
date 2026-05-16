import { useState } from 'react';
import { SignupFormValues } from '../../types/auth';

const initialValues: SignupFormValues = {
  full_name: '',
  email: '',
  password: '',
  confirm_password: '',
  grade_level: '',
  date_of_birth: '',
  parent_guardian_email: ''
};

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function getAge(dateOfBirth: string): number | null {
  if (!dateOfBirth) return null;
  const birthDate = new Date(`${dateOfBirth}T00:00:00`);
  if (Number.isNaN(birthDate.getTime())) return null;
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const birthdayPassed = today.getMonth() > birthDate.getMonth() || (today.getMonth() === birthDate.getMonth() && today.getDate() >= birthDate.getDate());
  if (!birthdayPassed) age -= 1;
  return age;
}

function validate(values: SignupFormValues): string {
  if (!values.full_name.trim()) return 'Full name is required.';
  if (!values.email.trim()) return 'Email address is required.';
  if (!isValidEmail(values.email)) return 'Please enter a valid email address.';
  if (!values.password) return 'Password is required.';
  if (values.password.length < 6) return 'Password must be at least 6 characters.';
  if (values.confirm_password !== values.password) return 'Confirm password must match password.';
  if (!values.grade_level) return 'Student grade level is required.';
  if (!values.date_of_birth) return 'Date of birth is required.';
  const age = getAge(values.date_of_birth);
  if (age === null || age < 0) return 'Please enter a valid date of birth.';
  if (age < 13 && !values.parent_guardian_email.trim()) return 'Parent/Guardian email is required if the student is under 13.';
  if (values.parent_guardian_email && !isValidEmail(values.parent_guardian_email)) return 'Please enter a valid parent or guardian email.';
  if (values.parent_guardian_email.toLowerCase() === values.email.toLowerCase()) return 'Parent/Guardian email must be different from student email.';
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
      <p>Create a parent-supervised learner account. We will verify the email before opening the dashboard.</p>
    </div>
    <div className="auth-form">
      <label>Full Name<input value={values.full_name} onChange={e => setValues({ ...values, full_name: e.target.value })} /></label>
      <label>Email Address<input type="email" value={values.email} onChange={e => setValues({ ...values, email: e.target.value })} /></label>
      <label>Password<input type="password" value={values.password} onChange={e => setValues({ ...values, password: e.target.value })} /></label>
      <label>Confirm Password<input type="password" value={values.confirm_password} onChange={e => setValues({ ...values, confirm_password: e.target.value })} /></label>
      <label>Student Grade Level<select value={values.grade_level} onChange={e => setValues({ ...values, grade_level: e.target.value })}><option value="">Select grade</option><option>Grade 3</option><option>Grade 4</option><option>Grade 5</option><option>Grade 6</option></select></label>
      <label>Date of Birth<input type="date" value={values.date_of_birth} onChange={e => setValues({ ...values, date_of_birth: e.target.value })} /></label>
      <label>Parent/Guardian Email<input type="email" value={values.parent_guardian_email} onChange={e => setValues({ ...values, parent_guardian_email: e.target.value })} /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="primary-button" onClick={submit} disabled={loading}>{loading ? 'Creating...' : 'Create Account'}</button>
      <button className="link-button" onClick={onLogin} type="button">Already have an account? Log in</button>
    </div>
  </div>;
}
