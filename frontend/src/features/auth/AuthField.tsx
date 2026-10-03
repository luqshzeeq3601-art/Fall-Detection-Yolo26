import { CheckCircle2, Eye, EyeOff } from 'lucide-react';
import type { ChangeEvent, InputHTMLAttributes, JSX, ReactNode } from 'react';

type AuthFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange'> & {
  label: string;
  error?: string;
  valid?: boolean;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  trailing?: ReactNode;
};

export function AuthField({
  id,
  label,
  error,
  valid = false,
  trailing,
  ...inputProps
}: AuthFieldProps): JSX.Element {
  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className={`auth-input-wrap${error ? ' has-error' : ''}${valid ? ' is-valid' : ''}`}>
        <input id={id} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} {...inputProps} />
        {trailing ? <span className="auth-field-trailing">{trailing}</span> : null}
        {valid && !trailing ? <CheckCircle2 className="auth-valid-icon" aria-label="Valid" /> : null}
      </div>
      {error ? <p id={`${id}-error`} className="auth-field-error" role="alert">{error}</p> : null}
    </div>
  );
}

export function PasswordToggle({
  visible,
  onToggle,
}: {
  visible: boolean;
  onToggle: () => void;
}): JSX.Element {
  return (
    <button
      className="auth-password-toggle"
      type="button"
      aria-label={visible ? 'Hide password' : 'Show password'}
      onClick={onToggle}
    >
      {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
    </button>
  );
}
