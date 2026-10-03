import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { installFakeApi } from '../test/fakeApi.ts';
import { renderPage } from '../test/renderPage.tsx';
import { SettingsPage } from './SettingsPage.tsx';

beforeEach(() => setApiClient(new MockApiClient()));
afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

describe('Settings', () => {
  it('opens on Detection and switches tabs through the URL', async () => {
    installFakeApi();
    renderPage(<SettingsPage />, '/app/settings');
    expect(await screen.findByText('Sensitivity')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Account' }));
    expect(screen.getByLabelText('location').textContent).toContain('tab=account');
    expect(await screen.findByRole('heading', { name: 'Change password' })).toBeDefined();
  });

  it('saves a detection override to the server', async () => {
    const { calls } = installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=detection');
    fireEvent.click(await screen.findByRole('switch', { name: /use the calibrated defaults/i }));
    fireEvent.change(screen.getByLabelText(/trigger threshold/i), { target: { value: '0.7' } });
    expect(screen.getByText('You have unsaved changes')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT' && (call.body as { fall_threshold: number }).fall_threshold === 0.7)).toBe(true));
    expect(await screen.findByText(/settings saved/i)).toBeDefined();
  });

  it('warns before enabling automatic deletion', async () => {
    installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=data');
    fireEvent.change(await screen.findByLabelText('Retention'), { target: { value: '7' } });
    expect(screen.getByText(/older than 7 days and their keyframes will be permanently deleted/i)).toBeDefined();
  });

  it('lists cameras with rename and enable controls', async () => {
    installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=cameras');
    expect((await screen.findAllByRole('button', { name: /rename/i })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('switch').length).toBeGreaterThan(0);
  });
});
