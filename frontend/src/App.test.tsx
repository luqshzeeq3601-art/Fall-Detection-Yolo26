import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.tsx';
import { AppShell } from './components/layout/Shell.tsx';
import { AuthProvider } from './features/auth/AuthProvider.tsx';
import { DashboardProvider } from './hooks/DashboardContext.tsx';
import { setApiClient } from './api/index.ts';
import { MockApiClient } from './api/mockClient.ts';
import { installFakeApi } from './test/fakeApi.ts';

beforeEach(() => {
  window.history.replaceState(null, '', '/app');
  setApiClient(new MockApiClient());
  installFakeApi();
});

afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

describe('App routing and shell', () => {
  it('keeps the landing page public with real sections behind every nav link', () => {
    window.history.replaceState(null, '', '/');
    render(<App />);
    const nav = screen.getByRole('navigation', { name: 'On this page' });
    for (const [label, target] of [['How it works', '#how-it-works'], ['Results', '#results'], ['Privacy', '#privacy']]) {
      const link = within(nav).getByRole('link', { name: label });
      expect(link.getAttribute('href')).toBe(target);
      expect(document.querySelector(target)).not.toBeNull();
    }
    expect(screen.getByRole('link', { name: /see the results/i }).getAttribute('href')).toBe('#results');
    expect(screen.getByText('98.3%')).toBeDefined();
    expect(screen.queryByRole('navigation', { name: 'Dashboard pages' })).toBeNull();
  });

  it('groups the dashboard pages by job: monitor, respond, system', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeDefined();
    const nav = screen.getByRole('navigation', { name: 'Dashboard pages' });
    for (const group of ['Monitor', 'Respond', 'System']) expect(within(nav).getByText(group)).toBeDefined();
    for (const label of ['Overview', 'Live monitor', 'Incidents', 'Review queue', 'System health', 'Model results', 'Settings']) {
      expect(within(nav).getByRole('link', { name: label })).toBeDefined();
    }
  });

  it('shows the signed-in user and a sign-out action in the account menu', async () => {
    render(<App />);
    const menu = await screen.findByRole('button', { name: /operator/i });
    menu.click();
    expect(await screen.findByRole('dialog', { name: 'Account menu' })).toBeDefined();
    expect(screen.getByRole('button', { name: /sign out/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /account & password/i }).getAttribute('href')).toBe('/app/settings?tab=account');
  });

  it('hides technical telemetry and model benchmarks from caregiver nav', async () => {
    const caregiverUser = {
      id: 'cg-1',
      email: 'caregiver@example.test',
      full_name: 'Caregiver Nurse',
      role: 'operator',
      organization: 'Sunrise Home',
      care_setting: 'facility',
      job_role: 'caregiver',
      created_at: '2026-01-01T00:00:00Z',
    };
    render(
      <MemoryRouter initialEntries={['/app']}>
        <AuthProvider initialUser={caregiverUser}>
          <DashboardProvider>
            <AppShell />
          </DashboardProvider>
        </AuthProvider>
      </MemoryRouter>
    );
    const nav = await screen.findByRole('navigation', { name: 'Dashboard pages' });
    expect(within(nav).queryByRole('link', { name: 'System health' })).toBeNull();
    expect(within(nav).queryByRole('link', { name: 'Model results' })).toBeNull();
    expect(within(nav).getByRole('link', { name: 'Overview' })).toBeDefined();
    expect(within(nav).getByRole('link', { name: 'Live monitor' })).toBeDefined();
    expect(within(nav).getByRole('link', { name: 'Incidents' })).toBeDefined();
    expect(within(nav).getByRole('link', { name: 'Review queue' })).toBeDefined();
    expect(within(nav).getByRole('link', { name: 'Settings' })).toBeDefined();
  });

  it('toggles sidebar collapsed state via button and keyboard shortcut Ctrl+B', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeDefined();
    const [collapseBtn] = screen.getAllByRole('button', { name: /collapse sidebar/i });
    expect(document.querySelector('.app-frame.is-collapsed')).toBeNull();

    // Click collapse button
    fireEvent.click(collapseBtn);
    expect(document.querySelector('.app-frame.is-collapsed')).not.toBeNull();
    expect(window.localStorage.getItem('eldercare.sidebar.collapsed')).toBe('true');

    // Press Ctrl+B shortcut to expand
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
    expect(document.querySelector('.app-frame.is-collapsed')).toBeNull();
    expect(window.localStorage.getItem('eldercare.sidebar.collapsed')).toBe('false');
  });
});
