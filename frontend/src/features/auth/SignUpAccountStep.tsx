import { Building2, CheckCircle2, Lock, Mail, User, Users } from 'lucide-react';
import type { ChangeEvent, JSX } from 'react';
import { AuthField, PasswordToggle } from './AuthField.tsx';
import { passwordStrength, validateEmail, type AccountErrors, type Role, type SignUpValues } from './authValidation.ts';

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
        leading={<User className="auth-field-leading-icon" />}
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
        leading={<Mail className="auth-field-leading-icon" />}
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
        leading={<Lock className="auth-field-leading-icon" />}
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
        leading={<Lock className="auth-field-leading-icon" />}
        error={errors.confirmPassword}
        trailing={<PasswordToggle visible={showConfirmPassword} onToggle={onToggleConfirmPassword} />}
      />
      <fieldset className="auth-role-fieldset">
        <legend>Select your role</legend>
        <div className="auth-role-grid">
          <RoleChoice
            role="caregiver"
            label="Caregiver"
            description="Monitor and receive alerts"
            icon={<Users />}
            selected={values.role === 'caregiver'}
            onSelect={() => onFieldChange('role', 'caregiver')}
          />
          <RoleChoice
            role="facility-admin"
            label="Facility admin"
            description="Manage facility and users"
            icon={<Building2 />}
            selected={values.role === 'facility-admin'}
            onSelect={() => onFieldChange('role', 'facility-admin')}
          />
        </div>
        {errors.role ? <p className="auth-field-error" role="alert">{errors.role}</p> : null}
      </fieldset>
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

function RoleChoice({
  role,
  label,
  description,
  icon,
  selected,
  onSelect,
}: {
  role: Exclude<Role, ''>;
  label: string;
  description: string;
  icon: JSX.Element;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <label className={`auth-role-choice${selected ? ' is-selected' : ''}`}>
      <input type="radio" name="role" value={role} checked={selected} onChange={onSelect} />
      <span className="auth-role-icon" aria-hidden="true">{icon}</span>
      <span className="auth-role-copy"><strong>{label}</strong><small>{description}</small></span>
      <span className="auth-role-check" aria-hidden="true" />
    </label>
  );
}
