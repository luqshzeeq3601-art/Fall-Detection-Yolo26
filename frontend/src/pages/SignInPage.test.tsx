import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import type { JSX } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../features/auth/AuthProvider.tsx';
import { SignInPage } from './SignInPage.tsx';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function renderSignIn(): void {
  render(<MemoryRouter initialEntries={['/signin']}><AuthProvider><SignInPage /><LocationProbe /></AuthProvider></MemoryRouter>);
}

const USER = { id: 'u1', email: 'operator@example.com', full_name: 'Operator', role: 'admin', organization: null, care_setting: 'home', job_role: 'caregiver', created_at: '2026-10-01T00:00:00Z' };

describe('SignInPage', () => {
  it('shows field validation when submitted empty', () => {
    renderSignIn();
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(screen.getByText('Enter your email address.')).toBeDefined();
    expect(screen.getByText('Enter your password.')).toBeDefined();
  });

  it('signs in through the API and opens the dashboard without storing credentials', async () => {
    localStorage.clear();
    const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith('/auth/setup-status') ? { needs_setup: true } : USER), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    renderSignIn();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'operator@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(screen.getByLabelText('location').textContent).toContain('/app'));
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(fetchMock.mock.calls.find(([url]) => url === '/api/v1/auth/login')?.[1].body as string)).toEqual({ email: 'operator@example.com', password: 'secret123', remember: false });
    expect(localStorage.length).toBe(0);
  });

  it('shows the server error and stays on sign-in when credentials are rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'HTTP_401', message: 'Email or password is incorrect.' } }), { status: 401 }))));
    renderSignIn();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'operator@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-pass1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Email or password is incorrect.');
    expect(screen.getByLabelText('location').textContent).toBe('/signin');
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('');
  });

  it('shows admin setup while setup is open, then caregiver registration', async () => {
    const stub = (needsSetup: boolean): void => {
      vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
        Promise.resolve(url.endsWith('/auth/setup-status')
          ? new Response(JSON.stringify({ needs_setup: needsSetup }), { status: 200 })
          : new Response(JSON.stringify({ error: { code: 'HTTP_401', message: 'Sign in required.' } }), { status: 401 }))));
    };
    stub(true);
    renderSignIn();
    expect(await screen.findByText('Initial admin setup')).toBeDefined();
    cleanup();
    stub(false);
    renderSignIn();
    expect(await screen.findByText('Create an account')).toBeDefined();
    expect(screen.queryByText('Initial admin setup')).toBeNull();
  });
});
