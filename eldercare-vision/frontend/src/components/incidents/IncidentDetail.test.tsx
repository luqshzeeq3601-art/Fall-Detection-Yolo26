import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../../api/mockData.ts';
import { IncidentDetailPanel } from './IncidentDetail.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('IncidentDetail (P6-004)', () => {
  it('shows detector output, features, and evidence via approved routes', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentDetailPanel selectedId={MOCK_INCIDENTS[0].id} />);
    expect(await screen.findByText('yolo26s-pose.pt (1.0.0)')).toBeDefined();
    expect(await screen.findByText(/Score|0\.87/)).toBeDefined();
    expect(await screen.findByText('rapid_vertical_drop')).toBeDefined();
    const link = await screen.findByRole('link', { name: /open evidence/i });
    expect(link.getAttribute('href')).toBe(
      `/incidents/${encodeURIComponent(MOCK_INCIDENTS[0].id)}/evidence/e-0001`,
    );
    expect(link.getAttribute('href')).not.toContain('..');
  });

  it('labels enrichment as generated context, never as detector output', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentDetailPanel selectedId={MOCK_INCIDENTS[2].id} />);
    const labels = await screen.findAllByText('Generated context');
    expect(labels.length).toBeGreaterThan(0);
  });

  it('renders review notes as text, not HTML', async () => {
    const client = new MockApiClient();
    setApiClient(client);
    const id = MOCK_INCIDENTS[1].id;
    await client.submitReview(id, {
      label: 'uncertain',
      notes: '<img src=x onerror=alert(1)> check',
    });
    render(<IncidentDetailPanel selectedId={id} />);
    expect(await screen.findByText(/check/)).toBeDefined();
    expect(document.querySelector('img')).toBeNull();
  });

  it('shows empty reviews state and 404 error with retry', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentDetailPanel selectedId={MOCK_INCIDENTS[0].id} />);
    expect(await screen.findByText(/No reviews yet/)).toBeDefined();
    cleanup();
    render(<IncidentDetailPanel selectedId="missing-id" />);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeDefined();
  });

  it('shows empty state when nothing is selected', () => {
    setApiClient(new MockApiClient());
    render(<IncidentDetailPanel selectedId={null} />);
    expect(screen.getByText(/No incident selected/)).toBeDefined();
  });
});
