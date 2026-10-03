import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../../api/mockData.ts';
import { IncidentQueuePreview } from './IncidentQueuePreview.tsx';

afterEach(() => { cleanup(); setApiClient(null); });

describe('Incident queue evidence', () => {
  it('uses the saved evidence ID and incident ID to load its image', async () => {
    const api = new MockApiClient();
    setApiClient(api);
    const incident = MOCK_INCIDENTS.find((item) => item.evidence.some((evidence) => evidence.mime_type.startsWith('image/')))!;
    const evidence = incident.evidence.find((item) => item.mime_type.startsWith('image/'))!;
    const url = vi.spyOn(api, 'evidenceUrl');
    render(<IncidentQueuePreview incidentId={incident.id} />);
    await screen.findByRole('img', { name: 'Saved incident preview' });
    expect(url).toHaveBeenCalledWith(incident.id, evidence.id);
  });

  it('shows an explicit missing-image state without substituting artwork', async () => {
    const api = new MockApiClient();
    setApiClient(api);
    vi.spyOn(api, 'getIncident').mockResolvedValue({ ...MOCK_INCIDENTS[0], evidence: [] });
    render(<IncidentQueuePreview incidentId={MOCK_INCIDENTS[0].id} />);
    expect(await screen.findByText('No saved image')).toBeDefined();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('shows unavailable when the evidence request fails', async () => {
    const api = new MockApiClient();
    setApiClient(api);
    vi.spyOn(api, 'getIncident').mockRejectedValue(new Error('Unavailable'));
    render(<IncidentQueuePreview incidentId={MOCK_INCIDENTS[0].id} />);
    expect(await screen.findByText('Preview unavailable')).toBeDefined();
  });

  it('replaces a broken image with a readable fallback', async () => {
    setApiClient(new MockApiClient());
    const incident = MOCK_INCIDENTS.find((item) => item.evidence.some((evidence) => evidence.mime_type.startsWith('image/')))!;
    render(<IncidentQueuePreview incidentId={incident.id} />);
    fireEvent.error(await screen.findByRole('img', { name: 'Saved incident preview' }));
    expect(screen.getByText('Preview unavailable')).toBeDefined();
    expect(screen.queryByRole('img')).toBeNull();
  });
});
