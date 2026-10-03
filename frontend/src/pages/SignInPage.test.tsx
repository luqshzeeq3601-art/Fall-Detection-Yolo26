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
  it('explains Google sign-in availability without attempting authentication', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderSignIn();
    fireEvent.click(screen.getByRole('button', { name: 'Continue with Google' }));
    expect(screen.getByRole('dialog', { name: 'Google sign-in' })).toBeDefined();
    expect(screen.getByText('Google sign-in is not available in this workspace. Use your email and password to sign in.')).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows field validation when submitted empty', () => {
    renderSignIn();
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(screen.getByText('Enter your email address.')).toBeDefined();
    expect(screen.getByText('Enter your password.')).toBeDefined();
  });

  it('signs in through the API and opens the dashboard without storing credentials', async () => {
    localStorage.clear();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(USER), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    renderSignIn();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'operator@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(screen.getByLabelText('location').textContent).toContain('/app'));
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ email: 'operator@example.com', password: 'secret123', remember: false });
    expect(localStorage.length).toBe(0);
  });

  it('shows the server error and stays on sign-in when credentials are rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'HTTP_401', message: 'Email or password is incorrect.' } }), { status: 401 })));
    renderSignIn();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'operator@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-pass1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Email or password is incorrect.');
    expect(screen.getByLabelText('location').textContent).toBe('/signin');
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('');
  });
});
