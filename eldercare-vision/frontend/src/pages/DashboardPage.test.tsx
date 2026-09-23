import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { DashboardPage } from './DashboardPage.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('DashboardPage (P6-001…P6-003)', () => {
  it('renders system, camera, and incident data from the mock boundary', async () => {
    setApiClient(new MockApiClient());
    render(<DashboardPage />);
    const hallway = await screen.findAllByText('Hallway Camera');
    expect(hallway.length).toBeGreaterThan(0);
    expect(await screen.findByText('yolo26s-pose.pt')).toBeDefined();
    expect(await screen.findByText(/Showing 3 of 3 incidents/)).toBeDefined();
    expect(await screen.findByText(/No incident selected/)).toBeDefined();
  });

  it('shows distinct offline state without relying on color', async () => {
    setApiClient(new MockApiClient());
    render(<DashboardPage />);
    expect(await screen.findByText('Offline')).toBeDefined();
    expect(await screen.findByText('Degraded')).toBeDefined();
  });

  it('shows error state with retry when cameras fail', async () => {
    const client = new MockApiClient();
    client.setFailureMode('cameras');
    setApiClient(client);
    render(<DashboardPage />);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeDefined();
  });
});
