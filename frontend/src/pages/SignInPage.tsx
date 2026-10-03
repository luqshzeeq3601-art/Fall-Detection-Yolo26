import { ArrowRight, Home, Lock, LockKeyhole, Mail } from 'lucide-react';
import { useState, type FormEvent, type JSX } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client.ts';
import { useAuth } from '../features/auth/useAuth.ts';
import { Brand } from '../components/layout/Brand.tsx';
import signinArtUrl from '../assets/signin-art.png';
import { AuthField, PasswordToggle } from '../features/auth/AuthField.tsx';
import { AuthNotice, type AuthNoticeKind } from '../features/auth/AuthNotice.tsx';
import { validateSignIn, type SignInErrors, type SignInValues } from '../features/auth/authValidation.ts';
import './AuthPages.css';

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
    <div className="auth-page">
      <header className="public-header">
        <Link className="public-brand" to="/" aria-label="ElderCare Vision home">
          <Brand />
        </Link>
        <Link className="auth-home-link" to="/">
          <Home aria-hidden="true" /> <span>Back to home</span>
        </Link>
      </header>

      <main className="auth-main auth-signin-main">
        {/* Left Art & Headline Panel (matching signpc.png) */}
        <section className="auth-art-panel" aria-labelledby="signin-art-title">
          <img
            className="auth-art-image"
            src={signinArtUrl}
            alt="On-device edge camera scanning room with posture evidence on mobile screen"
          />
          <div className="auth-art-copy">
            <h2 id="signin-art-title" className="auth-art-heading">
              See evidence between<br />
              <span>camera and caregiver.</span>
            </h2>
            <div className="auth-art-divider" aria-hidden="true" />
            <p className="auth-art-subtitle">
              Local temporal evidence from in-home video for research review.
            </p>
          </div>
        </section>

        {/* Right Form Card & Privacy Panel */}
        <section className="auth-right-col">
          <div className="auth-card auth-signin-card" aria-labelledby="signin-title">
            <div className="auth-card-brand">
              <Brand />
            </div>
            <h1 id="signin-title" className="auth-card-heading">
              Welcome back
            </h1>
            <p className="auth-card-subtitle">Sign in to review local temporal evidence.</p>

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
                trailing={<Mail aria-hidden="true" className="auth-field-leading-icon" />}
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
                trailing={
                  <>
                    <LockKeyhole aria-hidden="true" className="auth-field-leading-icon" />
                    <PasswordToggle
                      visible={showPassword}
                      onToggle={() => setShowPassword((current) => !current)}
                    />
                  </>
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
                  className="auth-text-link"
                  type="button"
                  onClick={() => setNotice('reset')}
                >
                  Forgot password unavailable for now
                </button>
              </div>

              <button className="button primary auth-submit" type="submit" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'} <ArrowRight aria-hidden="true" />
              </button>
            </form>

            <p className="auth-create-copy">
              New here? <Link className="auth-inline-link" to="/signup">Create an account</Link>
            </p>
          </div>

          {/* Qualified Privacy Box below the card (matching signpc.png and 02-sign-in.md) */}
          <div className="auth-privacy-banner" role="note">
            <span className="auth-privacy-badge-icon" aria-hidden="true">
              <Lock />
            </span>
            <p>
              Inference runs locally. Optional configured VLM enrichment may share incident evidence
              images. Uploaded videos stay on the configured server. Browser recording is manual.
            </p>
          </div>

          <div className="auth-legal-row">
            <button className="auth-text-link" type="button" onClick={() => setNotice('terms')}>
              Terms
            </button>{' '}
            ·{' '}
            <button className="auth-text-link" type="button" onClick={() => setNotice('privacy')}>
              Privacy Policy
            </button>
          </div>
        </section>
      </main>

      {notice ? <AuthNotice kind={notice} onClose={() => setNotice(null)} /> : null}
    </div>
  );
}
