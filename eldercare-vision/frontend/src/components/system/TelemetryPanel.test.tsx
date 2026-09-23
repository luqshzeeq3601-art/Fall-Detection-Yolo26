import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { TelemetryPanel } from './TelemetryPanel.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('TelemetryPanel (P6-007)', () => {
  it('renders only real transported metrics', async () => {
    setApiClient(new MockApiClient());
    render(<TelemetryPanel />);
    expect(
      await screen.findByText((_, el) => el?.textContent === 'yolo26s-pose.pt (1.0.0)'),
    ).toBeDefined();
  });

  it('shows exact mock telemetry values', async () => {
    setApiClient(new MockApiClient());
    render(<TelemetryPanel />);
    expect(await screen.findByText('30.0 fps')).toBeDefined();
    expect(await screen.findByText('12.4 ms avg / 18.2 ms p95')).toBeDefined();
    expect(await screen.findByText('Host CPU (cpu)')).toBeDefined();
    expect((await screen.findAllByText('disabled'))).toHaveLength(2);
  });

  it('contains no invented analytics or predictions', async () => {
    setApiClient(new MockApiClient());
    const { container } = render(<TelemetryPanel />);
    await screen.findByText(/30\.0 fps/);
    const text = container.textContent?.toLowerCase() ?? '';
    for (const invented of ['accuracy', 'predict', 'forecast', 'chart', 'trend', 'alerts/hour']) {
      expect(text).not.toContain(invented);
    }
  });

  it('shows error + retry on failure', async () => {
    const client = new MockApiClient();
    client.setFailureMode('system');
    setApiClient(client);
    render(<TelemetryPanel />);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeDefined();
  });
});
