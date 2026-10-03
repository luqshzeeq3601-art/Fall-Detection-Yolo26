import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../api/mockData.ts';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';
import { installFakeApi } from '../test/fakeApi.ts';
import { renderPage } from '../test/renderPage.tsx';
import { IncidentsPage } from './IncidentsPage.tsx';
import { ReviewQueuePage } from './ReviewQueuePage.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

function fixture(): MockApiClient {
  const api = new MockApiClient();
  setApiClient(api);
  installFakeApi();
  return api;
}

describe('Incidents', () => {
  it('maps the decision tabs to server filters', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<IncidentsPage />, '/app/incidents');
    await screen.findByRole('tab', { name: 'Needs review' });
    fireEvent.click(screen.getByRole('tab', { name: 'Needs review' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ reviewed: false })));
    fireEvent.click(screen.getByRole('tab', { name: 'Real falls' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ review_label: 'confirmed_fall' })));
    fireEvent.click(screen.getByRole('tab', { name: 'False alarms' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ review_label: 'non_fall' })));
  });

  it('searches on the server after typing pauses', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<IncidentsPage />, '/app/incidents');
    fireEvent.change(await screen.findByLabelText('Search incidents'), { target: { value: 'cam-02' } });
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'cam-02' })), { timeout: 2000 });
    expect(screen.getByLabelText('location').textContent).toContain('search=cam-02');
  });

  it('opens an incident with its keyframes and records a decision as the signed-in user', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    const target = MOCK_INCIDENTS[0];
    renderPage(<IncidentsPage />, `/app/incidents?selected=${target.id}`);
    expect(await screen.findByRole('img', { name: /keyframe at the alert/i })).toBeDefined();
    fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'Slid off the chair' } });
    fireEvent.click(screen.getByRole('button', { name: /real fall/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(target.id, { label: 'confirmed_fall', notes: 'Slid off the chair' }));
    expect(await screen.findByText(/saved as “real fall”/i)).toBeDefined();
  });

  it('labels the AI second opinion as generated text', async () => {
    fixture();
    const withEnrichment = MOCK_INCIDENTS.find((incident) => incident.enrichments.some((e) => e.status === 'completed'));
    expect(withEnrichment).toBeDefined();
    renderPage(<IncidentDetailPanel selectedId={withEnrichment?.id ?? null} />);
    expect(await screen.findByText(/ai second opinion/i)).toBeDefined();
    expect(screen.getByText(/never overrides your decision/i)).toBeDefined();
  });

  it('guides the user when nothing is selected', () => {
    fixture();
    renderPage(<IncidentDetailPanel selectedId={null} />);
    expect(screen.getByText('Select an incident')).toBeDefined();
  });
});

describe('Review queue', () => {
  it('lists every unreviewed incident, not only AI-flagged ones', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<ReviewQueuePage />, '/app/review');
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.objectContaining({ reviewed: false })));
    expect(spy.mock.calls.every(([params]) => !params?.needs_review)).toBe(true);
  });

  it('records a decision with the F shortcut and moves to the next case', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    renderPage(<ReviewQueuePage />, '/app/review');
    const realFall = await screen.findByRole('button', { name: /real fall/i });
    await waitFor(() => expect((realFall as HTMLButtonElement).disabled).toBe(false));
    fireEvent.keyDown(window, { key: 'f' });
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.any(String), { label: 'confirmed_fall' }), { timeout: 3000 });
    expect(await screen.findByText(/reviewed this session · 1/i)).toBeDefined();
  });

  it('ignores shortcuts while typing in a field', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    renderPage(<><input aria-label="scratch" /><ReviewQueuePage /></>, '/app/review');
    await screen.findByRole('button', { name: /real fall/i });
    fireEvent.keyDown(screen.getByLabelText('scratch'), { key: 'f' });
    expect(spy).not.toHaveBeenCalled();
  });
});
