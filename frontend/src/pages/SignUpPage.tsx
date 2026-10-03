import { ArrowRight, Home } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent, type JSX } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client.ts';
import { authApi } from '../api/platform.ts';
import { Brand } from '../components/layout/Brand.tsx';
import { AuthFeatureList } from '../features/auth/AuthFeatureList.tsx';
import { AuthNotice, type AuthNoticeKind } from '../features/auth/AuthNotice.tsx';
import { SignUpAccountStep } from '../features/auth/SignUpAccountStep.tsx';
import { hasValidationErrors, validateAccountStep, type AccountErrors, type SignUpValues } from '../features/auth/authValidation.ts';
import { useAuth } from '../features/auth/useAuth.ts';
import './AuthPages.css';
import './SignUpPage.css';

const INITIAL_VALUES: SignUpValues = {
  fullName: '',
  email: '',
  password: '',
  confirmPassword: '',
  termsAccepted: false,
};

export function SignUpPage(): JSX.Element {
  const navigate = useNavigate();
  const { status, setUser } = useAuth();
  const [values, setValues] = useState<SignUpValues>(INITIAL_VALUES);
  const valuesRef = useRef(values);
  const [errors, setErrors] = useState<AccountErrors>({});
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [notice, setNotice] = useState<AuthNoticeKind | null>(null);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { valuesRef.current = values; }, [values]);
  useEffect(() => () => { valuesRef.current.password = ''; valuesRef.current.confirmPassword = ''; }, []);

  const updateField = (field: keyof SignUpValues, value: string | boolean): void => {
    setValues((previous) => ({ ...previous, [field]: value }));
    if (field in errors) setErrors((previous) => ({ ...previous, [field]: undefined }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setFormError('');
    const nextErrors = validateAccountStep(values);
    setErrors(nextErrors);
    if (hasValidationErrors(nextErrors)) {
      document.querySelector<HTMLElement>('.auth-signup-card [aria-invalid="true"], .auth-signup-card .auth-field-error')?.scrollIntoView({ block: 'center' });
      return;
    }
    setSubmitting(true);
    try {
      const user = await authApi.signup({
        full_name: values.fullName.trim(),
        email: values.email.trim(),
        password: values.password,
      });
      setValues(INITIAL_VALUES);
      setUser(user);
      navigate('/app', { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setErrors({ email: error.message });
      else setFormError(error instanceof ApiError && error.status !== 0 ? error.message : 'The server could not be reached. Check that the ElderCare Vision API is running.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page signup-reference-page">
      <header className="public-header">
        <Link className="public-brand" to="/" aria-label="ElderCare Vision home"><Brand /></Link>
        <Link className="auth-home-link" to="/"><Home aria-hidden="true" /> <span>Back to home</span></Link>
      </header>
      <main className="auth-main auth-signup-main">
        <section className="auth-signup-visual" aria-labelledby="signup-art-title">
          <div className="auth-feature-card">
            <p className="auth-feature-eyebrow">AI for safer, more independent living</p>
            <h2 id="signup-art-title" className="auth-feature-heading">Get started<br /> for a <span>safer tomorrow</span></h2>
            <p>Turn everyday video into real-time care insights with on-device AI and intelligent agents.</p>
            <AuthFeatureList />
          </div>
        </section>
        <section className="auth-card auth-signup-card" aria-labelledby="signup-title">
          <div className="auth-card-brand"><Brand /></div>
          <h1 id="signup-title" className="auth-card-heading">
            Create your account
          </h1>
          <p className="auth-card-subtitle">Set up your care dashboard in minutes</p>

          {status === 'signed-in' ? <div className="auth-form-info" role="note">You are already signed in. <Link to="/app">Open the dashboard</Link></div> : null}
          {formError ? <div className="auth-form-error" role="alert">{formError}</div> : null}
          <form className="auth-form" onSubmit={(event) => void submit(event)} noValidate>
            <SignUpAccountStep
              values={values}
              errors={errors}
              showPassword={showPassword}
              showConfirmPassword={showConfirmPassword}
              onFieldChange={updateField}
              onTogglePassword={() => setShowPassword((current) => !current)}
              onToggleConfirmPassword={() => setShowConfirmPassword((current) => !current)}
              onNotice={setNotice}
            />
            <button className="button primary auth-submit" type="submit" disabled={submitting}>{submitting ? 'Creating account…' : 'Create account'} <ArrowRight aria-hidden="true" /></button>
          </form>
          <p className="auth-create-copy">Already have an account? <Link className="auth-inline-link" to="/signin">Sign in</Link></p>
        </section>
      </main>
      {notice ? <AuthNotice kind={notice} onClose={() => setNotice(null)} /> : null}
    </div>
  );
}
