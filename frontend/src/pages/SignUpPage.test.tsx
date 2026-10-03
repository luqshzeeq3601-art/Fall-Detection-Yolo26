import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import type { JSX } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../features/auth/AuthProvider.tsx';
import { SignUpPage } from './SignUpPage.tsx';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function renderSignUp(): void {
  render(<MemoryRouter initialEntries={['/signup']}><AuthProvider><SignUpPage /><LocationProbe /></AuthProvider></MemoryRouter>);
}

function fillValidAccount(): void {
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Ada Operator' } });
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ada@example.com' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'SafePass1234' } });
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'SafePass1234' } });
  fireEvent.click(screen.getByRole('checkbox'));
}

describe('SignUpPage', () => {
  it('is a single form that shows every problem at once', () => {
    renderSignUp();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeDefined();
    expect(screen.getByText('Enter your full name.')).toBeDefined();
    expect(screen.queryByText(/select your role/i)).toBeNull();
    expect(screen.getByText('Agree to the terms to continue.')).toBeDefined();
    expect(screen.queryByText(/step \d of/i)).toBeNull();
  });

  it('creates the account and opens the dashboard; care setting is optional', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(url.endsWith('/auth/setup-status') ? new Response(JSON.stringify({ needs_setup: true }), { status: 200 }) : new Response(JSON.stringify({ id: 'u1', email: 'ada@example.com', full_name: 'Ada Operator', role: 'admin', organization: null, care_setting: null, job_role: 'caregiver', created_at: '2026-10-01T00:00:00Z' }), { status: 201 })));
    vi.stubGlobal('fetch', fetchMock);
    renderSignUp();
    fillValidAccount();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByLabelText('location').textContent).toBe('/app'));
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/v1/auth/signup');
    expect(call).toBeDefined();
    expect(JSON.parse(call?.[1].body as string)).toMatchObject({ full_name: 'Ada Operator', email: 'ada@example.com' });
    expect(JSON.parse(call?.[1].body as string)).not.toHaveProperty('job_role');
  });

  it('shows a duplicate email next to the email field', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'HTTP_409', message: 'An account with this email already exists.' } }), { status: 409 }))));
    renderSignUp();
    fillValidAccount();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('An account with this email already exists.')).toBeDefined();
  });

  it('keeps signup available once an admin already exists', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/auth/setup-status')
        ? new Response(JSON.stringify({ needs_setup: false }), { status: 200 })
        : new Response(JSON.stringify({ error: { code: 'HTTP_401', message: 'Sign in required.' } }), { status: 401 }))));
    renderSignUp();
    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeDefined();
    expect(screen.getByLabelText('location').textContent).toBe('/signup');
  });

  it.each([
    { needsSetup: true },
    { needsSetup: false },
  ])('omits all role cards and selectors when needs_setup is $needsSetup', async ({ needsSetup }) => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(
      url.endsWith('/auth/setup-status')
        ? new Response(JSON.stringify({ needs_setup: needsSetup }), { status: 200 })
        : new Response(JSON.stringify({ error: { code: 'HTTP_401', message: 'Sign in required.' } }), { status: 401 }),
    )));
    renderSignUp();
    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeDefined();
    expect(screen.queryByText('Account role')).toBeNull();
    expect(screen.queryByText('Caregiver')).toBeNull();
    expect(screen.queryByText('Facility admin')).toBeNull();
    expect(screen.queryByText('Assigned by the server')).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.getByRole('heading', { level: 2, name: /get started for a safer tomorrow/i })).toBeDefined();
  });
});
