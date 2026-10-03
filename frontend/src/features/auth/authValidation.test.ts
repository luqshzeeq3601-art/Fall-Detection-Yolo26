import { describe, expect, it } from 'vitest';
import { hasValidationErrors, passwordStrength, validateAccountStep, validateSignIn, type SignUpValues } from './authValidation.ts';

const validValues: SignUpValues = {
  fullName: 'Demo operator',
  email: 'operator@example.com',
  password: 'SafePass1234',
  confirmPassword: 'SafePass1234',
  termsAccepted: true,
};

describe('auth validation', () => {
  it('rejects empty sign-in values and accepts a valid email/password pair', () => {
    expect(validateSignIn({ email: '', password: '' })).toEqual({ email: 'Enter your email address.', password: 'Enter your password.' });
    expect(validateSignIn({ email: 'operator@example.com', password: 'local-only' })).toEqual({});
  });

  it('keeps password requirements visible through strength scores', () => {
    expect(passwordStrength('').score).toBe(0);
    expect(passwordStrength('short').label).toBe('Needs 8 characters');
    expect(passwordStrength('SafePass1234').label).toBe('Strong');
  });

  it('reports account mismatch and terms errors before the next step', () => {
    const errors = validateAccountStep({ ...validValues, confirmPassword: 'different', termsAccepted: false });
    expect(errors.confirmPassword).toBe('Passwords do not match.');
    expect(errors.termsAccepted).toBe('Agree to the terms to continue.');
    expect(hasValidationErrors(errors)).toBe(true);
    expect(validateAccountStep(validValues)).toEqual({});
  });

  it('requires a letter and a number in the password, matching the server rule', () => {
    expect(validateAccountStep({ ...validValues, password: 'lettersonly', confirmPassword: 'lettersonly' }).password).toBe('Include at least one letter and one number.');
  });
});
