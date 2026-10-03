export type SignInValues = {
  email: string;
  password: string;
};

export type SignUpValues = {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
  termsAccepted: boolean;
};

export type SignInErrors = Partial<Record<keyof SignInValues, string>>;
export type AccountErrors = Partial<Record<keyof SignUpValues, string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(email: string): string | undefined {
  const value = email.trim();
  if (!value) return 'Enter your email address.';
  if (!EMAIL_PATTERN.test(value)) return 'Enter a valid email address.';
  return undefined;
}

export function validateSignIn(values: SignInValues): SignInErrors {
  const errors: SignInErrors = {};
  const emailError = validateEmail(values.email);
  if (emailError) errors.email = emailError;
  if (!values.password) errors.password = 'Enter your password.';
  return errors;
}

export type PasswordStrength = {
  score: 0 | 1 | 2 | 3;
  label: 'Start typing' | 'Needs 8 characters' | 'Good' | 'Strong';
};

export function passwordStrength(password: string): PasswordStrength {
  if (!password) return { score: 0, label: 'Start typing' };
  if (password.length < 8) return { score: 1, label: 'Needs 8 characters' };

  const hasNumber = /\d/.test(password);
  const hasMixedCase = /[a-z]/.test(password) && /[A-Z]/.test(password);
  if (password.length >= 12 && hasNumber && hasMixedCase) return { score: 3, label: 'Strong' };
  return { score: 2, label: 'Good' };
}

export function validateAccountStep(values: SignUpValues): AccountErrors {
  const errors: AccountErrors = {};
  if (!values.fullName.trim()) errors.fullName = 'Enter your full name.';
  const emailError = validateEmail(values.email);
  if (emailError) errors.email = emailError;
  if (values.password.length < 8) errors.password = 'Use at least 8 characters.';
  else if (!/[a-z]/i.test(values.password) || !/\d/.test(values.password)) errors.password = 'Include at least one letter and one number.';
  if (!values.confirmPassword) errors.confirmPassword = 'Confirm your password.';
  else if (values.password !== values.confirmPassword) errors.confirmPassword = 'Passwords do not match.';
  if (!values.termsAccepted) errors.termsAccepted = 'Agree to the terms to continue.';
  return errors;
}

export function hasValidationErrors(errors: object): boolean {
  return Object.keys(errors).length > 0;
}
