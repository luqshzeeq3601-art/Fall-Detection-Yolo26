import { cleanup, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../api/mockData.ts';
import { defaultState, installFakeApi, session } from '../test/fakeApi.ts';
import { renderPage } from '../test/renderPage.tsx';
import { DashboardPage } from './DashboardPage.tsx';

beforeEach(() => setApiClient(new MockApiClient()));
afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

describe('Overview', () => {
  it('leads with what needs attention and links each number to its action', async () => {
    installFakeApi();
    renderPage(<DashboardPage />);
    const summary = await screen.findByRole('region', { name: 'Summary' });
    await waitFor(() => expect(within(summary).getByText('2')).toBeDefined());
    expect(within(summary).getByRole('link', { name: /review them now/i }).getAttribute('href')).toBe('/app/review');
    expect(within(summary).getByText('Idle')).toBeDefined();
    expect(screen.getByRole('link', { name: /start monitoring/i }).getAttribute('href')).toBe('/app/surveillance');
  });

  it('offers the three ways to start when nothing is running', async () => {
    installFakeApi();
    renderPage(<DashboardPage />);
    expect(await screen.findByText(/nothing is being monitored/i)).toBeDefined();
    expect(screen.getByRole('link', { name: /watch a camera/i }).getAttribute('href')).toBe('/app/surveillance?source=camera');
    expect(screen.getByRole('link', { name: /test with a dataset clip/i }).getAttribute('href')).toBe('/app/surveillance?source=video');
    expect(screen.getByRole('link', { name: /analyse your own video/i }).getAttribute('href')).toBe('/app/surveillance?source=upload');
  });

  it('shows the running source instead of the start choices', async () => {
    const state = defaultState();
    state.sessions = [session({ active: true, phase: 'running', camera_id: 'webcam-0', source_type: 'webcam', source: '0' })];
    installFakeApi(state);
    renderPage(<DashboardPage />);
    expect(await screen.findByText('Live · Camera 0')).toBeDefined();
    expect(screen.queryByText(/nothing is being monitored/i)).toBeNull();
  });

  it('lists the latest incidents with their review state', async () => {
    installFakeApi();
    renderPage(<DashboardPage />);
    const newest = [...MOCK_INCIDENTS].sort((a, b) => b.confirmed_at.localeCompare(a.confirmed_at))[0];
    await waitFor(() => expect(screen.getAllByRole('link').some((item) => item.getAttribute('href') === `/app/incidents?selected=${newest.id}`)).toBe(true));
    expect(screen.getAllByText(/needs review|confirmed fall|false alarm|unsure/i).length).toBeGreaterThan(0);
  });
});
