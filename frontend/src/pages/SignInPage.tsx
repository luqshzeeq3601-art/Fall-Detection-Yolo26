import { Home, Lock, Mail, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent, type JSX } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client.ts';
import { useAuth } from '../features/auth/useAuth.ts';
import { Brand } from '../components/layout/Brand.tsx';
import signinArtUrl from '../assets/signin-reference-v2.png';
import googleMarkUrl from '../assets/google-mark.png';
import { AuthField, PasswordToggle } from '../features/auth/AuthField.tsx';
import { AuthNotice, type AuthNoticeKind } from '../features/auth/AuthNotice.tsx';
import { validateSignIn, type SignInErrors, type SignInValues } from '../features/auth/authValidation.ts';
import './AuthPages.css';
import './SignInPage.css';

const INITIAL_VALUES: SignInValues = { email: '', password: '' };

export function SignInPage(): JSX.Element {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { signIn, status, user } = useAuth();
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [values, setValues] = useState<SignInValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<SignInErrors>({});
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [notice, setNotice] = useState<AuthNoticeKind | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const nextErrors = validateSignIn(values);
    setErrors(nextErrors);
    setFormError('');
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitting(true);
    try {
      await signIn(values.email.trim(), values.password, rememberMe);
      const next = params.get('next');
      navigate(next && next.startsWith('/app') ? next : '/app', { replace: true });
    } catch (error) {
      setValues((previous) => ({ ...previous, password: '' }));
      setFormError(
        error instanceof ApiError && error.status !== 0
          ? error.message
          : 'The server could not be reached. Check that the API is running.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const update = (field: keyof SignInValues, value: string): void => {
    setValues((previous) => ({ ...previous, [field]: value }));
    setErrors((previous) => ({ ...previous, [field]: undefined }));
  };

  return (
    <div className="auth-page auth-page-signin">
      <img className="signin-scene" src={signinArtUrl} alt="" aria-hidden="true" fetchPriority="high" />
      <header className="public-header">
        <Link className="public-brand" to="/" aria-label="ElderCare Vision home">
          <Brand />
        </Link>
        <Link className="auth-home-link" to="/">
          <Home aria-hidden="true" size={18} /> <span>Back to home</span>
        </Link>
      </header>

      <main className="auth-main auth-signin-main">
        <section className="auth-art-panel" aria-labelledby="signin-art-title">
          <div className="signin-art-copy">
            <h2 id="signin-art-title">Safer care,<br /><span>seen</span> in real time</h2>
            <div className="signin-art-divider" aria-hidden="true" />
          </div>
        </section>

        {/* Right Form Card & Trust Panel */}
        <section className="auth-right-col">
          <div className="auth-card auth-signin-card" aria-labelledby="signin-title">
            <div className="auth-card-brand">
              <Brand />
            </div>
            <h1 id="signin-title" className="auth-card-heading">
              Welcome back
            </h1>
            <p className="auth-card-subtitle">Sign in to your care dashboard</p>

            {status === 'signed-in' ? (
              <div className="auth-form-info" role="note">
                Signed in as {user?.email}. <Link to="/app">Open the dashboard</Link>
              </div>
            ) : null}

            {formError ? (
              <div className="auth-form-error" role="alert">
                {formError}
              </div>
            ) : null}

            <form className="auth-form" onSubmit={(event) => void submit(event)} noValidate>
              <AuthField
                id="signin-email"
                label="Email"
                type="email"
                value={values.email}
                placeholder="you@example.com"
                autoComplete="email"
                onChange={(event) => update('email', event.target.value)}
                error={errors.email}
                leading={<Mail aria-hidden="true" size={18} />}
              />

              <AuthField
                id="signin-password"
                label="Password"
                type={showPassword ? 'text' : 'password'}
                value={values.password}
                placeholder="Your password"
                autoComplete="current-password"
                onChange={(event) => update('password', event.target.value)}
                error={errors.password}
                leading={<Lock aria-hidden="true" size={18} />}
                trailing={
                  <PasswordToggle
                    visible={showPassword}
                    onToggle={() => setShowPassword((current) => !current)}
                  />
                }
              />

              <div className="auth-form-row">
                <label className="auth-checkbox-row">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                  />
                  <span>Remember me</span>
                </label>
                <button
                  className="auth-text-link auth-forgot-link"
                  type="button"
                  onClick={() => setNotice('reset')}
                >
                  Forgot password?
                </button>
              </div>

              <button className="button primary auth-submit" type="submit" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <div className="signin-separator"><span>or</span></div>
            <button className="signin-google-button" type="button" onClick={() => setNotice('google')}>
              <img src={googleMarkUrl} alt="" width="24" height="24" />
              Continue with Google
            </button>

            <p className="auth-create-copy">
              New here? <Link className="auth-inline-link" to="/signup">Create an account</Link>
            </p>
          </div>

          {/* Privacy & on-device Trust Row */}
          <div className="auth-trust-banner" role="note">
            <ShieldCheck className="auth-trust-icon" aria-hidden="true" size={19} />
            <span>Video stays on-device. Only insights reach your care team.</span>
          </div>
        </section>
      </main>

      {notice ? <AuthNotice kind={notice} onClose={() => setNotice(null)} /> : null}
    </div>
  );
}
