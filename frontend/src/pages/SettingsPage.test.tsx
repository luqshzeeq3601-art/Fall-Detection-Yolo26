import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { installFakeApi } from '../test/fakeApi.ts';
import { renderPage } from '../test/renderPage.tsx';
import { SettingsPage } from './SettingsPage.tsx';
import { authApi } from '../api/platform.ts';

const caregiverUser = {
  id: 'cg-1', email: 'caregiver@example.test', full_name: 'Caregiver Nurse', role: 'operator',
  organization: 'Sunrise Home', care_setting: 'facility', job_role: 'caregiver', created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => setApiClient(new MockApiClient()));
afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Account settings reference controls', () => {
  it('explains unavailable profile editing without sending an account write', async () => {
    const { calls } = installFakeApi();
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('heading', { name: 'Account editing unavailable' })).toBeDefined();
    expect(screen.getByText(/profile changes are not available here yet/i)).toBeDefined();
    expect(calls.some((call) => call.method !== 'GET')).toBe(false);
  });

  it('toggles each password independently without submitting the form', async () => {
    installFakeApi();
    const changePassword = vi.spyOn(authApi, 'changePassword');
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    const current = await screen.findByLabelText('Current password');
    const next = screen.getByLabelText('New password');
    fireEvent.click(screen.getByRole('button', { name: 'Show current password' }));
    expect(current.getAttribute('type')).toBe('text');
    expect(next.getAttribute('type')).toBe('password');
    fireEvent.click(screen.getByRole('button', { name: 'Show new password' }));
    expect(next.getAttribute('type')).toBe('text');
    fireEvent.click(screen.getByRole('button', { name: 'Hide current password' }));
    expect(current.getAttribute('type')).toBe('password');
    expect(changePassword).not.toHaveBeenCalled();
  });

  it('prevents duplicate password requests and clears both fields and visibility after success', async () => {
    installFakeApi();
    let finish!: () => void;
    const changePassword = vi.spyOn(authApi, 'changePassword').mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    const current = await screen.findByLabelText('Current password') as HTMLInputElement;
    const next = screen.getByLabelText('New password') as HTMLInputElement;
    const submit = screen.getByRole('button', { name: 'Update password' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(current, { target: { value: 'old-test-123' } });
    fireEvent.change(next, { target: { value: 'new-test-456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Show new password' }));
    fireEvent.click(submit);
    fireEvent.submit(submit.closest('form')!);
    expect(changePassword).toHaveBeenCalledTimes(1);
    expect(changePassword).toHaveBeenCalledWith('old-test-123', 'new-test-456');
    expect(screen.getByRole('button', { name: 'Updating…' }).hasAttribute('disabled')).toBe(true);
    finish();
    expect(await screen.findByText('Password changed.')).toBeDefined();
    expect(current.value).toBe('');
    expect(next.value).toBe('');
    expect(next.type).toBe('password');
  });

  it('keeps password entries for correction when the server rejects the change', async () => {
    installFakeApi();
    vi.spyOn(authApi, 'changePassword').mockRejectedValue(new Error('Current password is incorrect.'));
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    const current = await screen.findByLabelText('Current password') as HTMLInputElement;
    const next = screen.getByLabelText('New password') as HTMLInputElement;
    fireEvent.change(current, { target: { value: 'old-test-123' } });
    fireEvent.change(next, { target: { value: 'new-test-456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update password' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Current password is incorrect.');
    expect(current.value).toBe('old-test-123');
    expect(next.value).toBe('new-test-456');
    expect((screen.getByRole('button', { name: 'Update password' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('requests notification permission only after the user acts and updates the status', async () => {
    installFakeApi();
    const requestPermission = vi.fn().mockResolvedValue('granted');
    vi.stubGlobal('Notification', { permission: 'default', requestPermission });
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    const allow = await screen.findByRole('button', { name: 'Allow desktop notifications' });
    expect(requestPermission).not.toHaveBeenCalled();
    fireEvent.click(allow);
    expect(await screen.findByText(/on: fall alerts show/i)).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Allow desktop notifications' })).toBeNull();
    expect(requestPermission).toHaveBeenCalledTimes(1);
  });

  it('keeps the permission action disabled while the browser prompt is pending', async () => {
    installFakeApi();
    let finish!: (permission: NotificationPermission) => void;
    const requestPermission = vi.fn(() => new Promise<NotificationPermission>((resolve) => { finish = resolve; }));
    vi.stubGlobal('Notification', { permission: 'default', requestPermission });
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    fireEvent.click(await screen.findByRole('button', { name: 'Allow desktop notifications' }));
    expect((screen.getByRole('button', { name: 'Waiting for browser…' }) as HTMLButtonElement).disabled).toBe(true);
    expect(requestPermission).toHaveBeenCalledTimes(1);
    finish('default');
    await waitFor(() => expect((screen.getByRole('button', { name: 'Allow desktop notifications' }) as HTMLButtonElement).disabled).toBe(false));
  });

  it('respects the workspace admin disabling desktop notifications', async () => {
    const { state } = installFakeApi();
    state.settings.settings.browser_alerts = false;
    const requestPermission = vi.fn();
    vi.stubGlobal('Notification', { permission: 'default', requestPermission });
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    expect(await screen.findByText('Your workspace admin has turned desktop notifications off.')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Allow desktop notifications' })).toBeNull();
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it.each([
    ['denied', /blocked by the browser/i],
    ['unsupported', /does not support desktop notifications/i],
    ['granted', /on: fall alerts show/i],
  ])('shows the %s permission state without an unusable allow action', async (permission, status) => {
    installFakeApi();
    vi.stubGlobal('Notification', permission === 'unsupported' ? undefined : { permission, requestPermission: vi.fn() });
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    expect(await screen.findByText(status)).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Allow desktop notifications' })).toBeNull();
  });

  it('shows a recoverable error when the browser permission request fails', async () => {
    installFakeApi();
    vi.stubGlobal('Notification', { permission: 'default', requestPermission: vi.fn().mockRejectedValue(new Error('Permission request failed.')) });
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    fireEvent.click(await screen.findByRole('button', { name: 'Allow desktop notifications' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Permission request failed.');
    expect((screen.getByRole('button', { name: 'Allow desktop notifications' }) as HTMLButtonElement).disabled).toBe(false);
  });
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

  it('lists cameras with edit and enable controls', async () => {
    installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=cameras');
    expect((await screen.findAllByRole('button', { name: /^edit$/i })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('switch').length).toBeGreaterThan(0);
  });

  it('restricts caregiver / operator view to Account tab only without savebar', async () => {
    installFakeApi();
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
    renderPage(<SettingsPage />, '/app/settings', caregiverUser);
    expect(await screen.findByRole('heading', { name: 'Account settings' })).toBeDefined();
    expect(screen.queryByRole('navigation', { name: 'Settings sections' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Detection' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cameras' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Data & privacy' })).toBeNull();
    expect(screen.queryByRole('button', { name: /save changes/i })).toBeNull();
    expect(await screen.findByRole('heading', { name: 'Change password' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Alerts on this device' })).toBeDefined();
    expect(screen.queryByRole('button', { name: /add team member/i })).toBeNull();
  });

  it('asks before saving a retention period that deletes incidents', async () => {
    const { calls } = installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=data');
    fireEvent.change(await screen.findByLabelText('Retention'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    expect(await screen.findByRole('heading', { name: 'Delete old incidents?' })).toBeDefined();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Save and delete' }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT' && (call.body as { retention_days: number }).retention_days === 7)).toBe(true));
  });
  it('saves the escalation delay and shows the activity log', async () => {
    const { calls } = installFakeApi();
    renderPage(<SettingsPage />, '/app/settings?tab=alerts');
    fireEvent.change(await screen.findByLabelText('If nobody responds to a fall'), { target: { value: '300' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT' && (call.body as { escalate_after_sec: number }).escalate_after_sec === 300)).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: 'Activity log' }));
    expect(await screen.findByText('Changed settings')).toBeDefined();
    expect(screen.getByText(/fall threshold: 0.6/)).toBeDefined();
  });
});
