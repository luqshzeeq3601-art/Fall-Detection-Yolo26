import { CheckCircle2 } from 'lucide-react';
import type { ChangeEvent, JSX } from 'react';
import { AuthField, PasswordToggle } from './AuthField.tsx';
import { passwordStrength, validateEmail, type AccountErrors, type SignUpValues } from './authValidation.ts';

type SignUpAccountStepProps = {
  values: SignUpValues;
  errors: AccountErrors;
  showPassword: boolean;
  showConfirmPassword: boolean;
  onFieldChange: (field: keyof SignUpValues, value: string | boolean) => void;
  onTogglePassword: () => void;
  onToggleConfirmPassword: () => void;
  onNotice: (kind: 'terms' | 'privacy') => void;
};

export function SignUpAccountStep({
  values,
  errors,
  showPassword,
  showConfirmPassword,
  onFieldChange,
  onTogglePassword,
  onToggleConfirmPassword,
  onNotice,
}: SignUpAccountStepProps): JSX.Element {
  const strength = passwordStrength(values.password);
  const fieldChange = (field: keyof SignUpValues) => (event: ChangeEvent<HTMLInputElement>): void => {
    onFieldChange(field, event.target.value);
  };

  return (
    <section className="auth-step-content" aria-label="Account details">
      <AuthField
        id="full-name"
        label="Full name"
        value={values.fullName}
        onChange={fieldChange('fullName')}
        placeholder="Your name"
        autoComplete="name"
        error={errors.fullName}
        valid={Boolean(values.fullName.trim()) && !errors.fullName}
      />
      <AuthField
        id="signup-email"
        label="Email"
        type="email"
        value={values.email}
        onChange={fieldChange('email')}
        placeholder="you@example.com"
        autoComplete="email"
        error={errors.email}
        valid={Boolean(values.email && !validateEmail(values.email) && !errors.email)}
      />
      <AuthField
        id="signup-password"
        label="Password"
        type={showPassword ? 'text' : 'password'}
        value={values.password}
        onChange={fieldChange('password')}
        placeholder="At least 8 characters"
        autoComplete="new-password"
        error={errors.password}
        trailing={<PasswordToggle visible={showPassword} onToggle={onTogglePassword} />}
      />
      <div className="password-strength" aria-live="polite">
        <span className="password-strength-hint">At least 8 characters</span>
        <div className="password-strength-bars" aria-hidden="true">
          {[1, 2, 3].map((bar) => (
            <span className={bar <= strength.score ? `is-${strength.score}` : ''} key={bar} />
          ))}
        </div>
        <span className={`password-strength-status${strength.score >= 2 ? ' is-strong' : ''}`}>
          {values.password ? strength.label : 'Start typing'}
        </span>
      </div>
      <AuthField
        id="confirm-password"
        label="Confirm password"
        type={showConfirmPassword ? 'text' : 'password'}
        value={values.confirmPassword}
        onChange={fieldChange('confirmPassword')}
        placeholder="Re-enter your password"
        autoComplete="new-password"
        error={errors.confirmPassword}
        trailing={<PasswordToggle visible={showConfirmPassword} onToggle={onToggleConfirmPassword} />}
      />
      <label className={`auth-checkbox-row${errors.termsAccepted ? ' has-error' : ''}`}>
        <input
          type="checkbox"
          checked={values.termsAccepted}
          onChange={(event) => onFieldChange('termsAccepted', event.target.checked)}
        />
        <span>I agree to the <button type="button" className="auth-inline-link" onClick={() => onNotice('terms')}>Terms</button> and <button type="button" className="auth-inline-link" onClick={() => onNotice('privacy')}>Privacy Policy</button>.</span>
        {values.termsAccepted ? <CheckCircle2 className="auth-checkbox-valid" aria-label="Terms accepted" /> : null}
      </label>
      {errors.termsAccepted ? <p className="auth-field-error" role="alert">{errors.termsAccepted}</p> : null}
    </section>
  );
}
