import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.tsx';
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
});
