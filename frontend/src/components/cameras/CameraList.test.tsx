import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { CameraList } from './CameraList.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('CameraList (P6-002)', () => {
  it('renders all camera states with text+symbol, not color-only', async () => {
    setApiClient(new MockApiClient());
    render(<CameraList />);
    expect(await screen.findByText('Hallway Camera')).toBeDefined();
    expect(await screen.findByText('Online')).toBeDefined();
    expect(await screen.findByText('Degraded')).toBeDefined();
    expect(await screen.findByText('Offline')).toBeDefined();
    expect(screen.getByRole('list', { name: /camera health/i })).toBeDefined();
  });

  it('shows timestamps and reconnect counts readably', async () => {
    setApiClient(new MockApiClient());
    render(<CameraList />);
    expect(await screen.findByText(/Reconnects 5/)).toBeDefined();
    expect(await screen.findByText(/2026-09-23 08:00:00 UTC/)).toBeDefined();
  });

  it('shows error + retry on failure', async () => {
    const client = new MockApiClient();
    client.setFailureMode('cameras');
    setApiClient(client);
    render(<CameraList />);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeDefined();
  });

  it('exposes accessible per-camera status labels', async () => {
    setApiClient(new MockApiClient());
    render(<CameraList />);
    expect(await screen.findByLabelText(/Hallway Camera status: Online/)).toBeDefined();
    expect(await screen.findByLabelText(/Entrance Camera status: Offline/)).toBeDefined();
  });
});
