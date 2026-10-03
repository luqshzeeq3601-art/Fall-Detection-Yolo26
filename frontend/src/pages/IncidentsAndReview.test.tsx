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

const CAREGIVER = { id: 'cg-1', email: 'caregiver@example.test', full_name: 'Casey Carer', role: 'operator', organization: null, care_setting: null, job_role: 'caregiver', created_at: '2026-01-01T00:00:00Z' };

describe('Incidents', () => {
  it('hides the retraining export from caregivers', async () => {
    fixture();
    renderPage(<IncidentsPage />, '/app/incidents', CAREGIVER);
    await screen.findByRole('tab', { name: 'Not reviewed' });
    expect(screen.queryByRole('button', { name: /export reviewed/i })).toBeNull();
    expect(screen.getByRole('button', { name: /^filter$/i })).toBeDefined();
  });

  it('applies a draft search immediately when Filter is submitted', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<IncidentsPage />, '/app/incidents?status=unreviewed', CAREGIVER);
    fireEvent.change(await screen.findByLabelText('Search incidents'), { target: { value: 'cam-02' } });
    fireEvent.click(screen.getByRole('button', { name: /^filter$/i }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'cam-02', reviewed: false })));
    expect(screen.getByLabelText('location').textContent).toContain('search=cam-02');
  });

  it('moves decision tabs with the keyboard and keeps focus on the active tab', async () => {
    fixture();
    renderPage(<IncidentsPage />, '/app/incidents');
    fireEvent.keyDown(await screen.findByRole('tab', { name: 'All' }), { key: 'ArrowRight' });
    const tab = screen.getByRole('tab', { name: 'Not reviewed' });
    expect(tab.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(tab);
    fireEvent.keyDown(tab, { key: 'End' });
    expect(screen.getByRole('tab', { name: 'Unsure' }).getAttribute('aria-selected')).toBe('true');
  });

  it('shows no invented trends or recording controls', async () => {
    fixture();
    renderPage(<IncidentsPage />, `/app/incidents?selected=${MOCK_INCIDENTS[0].id}`);
    await screen.findAllByRole('button', { name: /mark as real fall/i });
    expect(screen.queryByText(/from last 7 days/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /play recording/i })).toBeNull();
    expect(screen.queryByText('0:12')).toBeNull();
    expect(screen.getByRole('button', { name: /mark as unsure/i })).toBeDefined();
  });

  it('maps the decision tabs to server filters', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<IncidentsPage />, '/app/incidents');
    await screen.findByRole('tab', { name: 'Not reviewed' });
    fireEvent.click(screen.getByRole('tab', { name: 'Not reviewed' }));
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

  it('preserves a camera change while a search is waiting to apply', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<IncidentsPage />, '/app/incidents');
    fireEvent.change(await screen.findByLabelText('Search incidents'), { target: { value: 'incident' } });
    await screen.findByRole('option', { name: 'Lounge Camera' });
    fireEvent.change(screen.getByLabelText('Camera'), { target: { value: 'cam-02' } });
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'incident', camera_id: 'cam-02' })), { timeout: 2000 });
    expect(screen.getByLabelText('location').textContent).toContain('camera=cam-02');
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

  it('hides detector internals and model names from caregivers', async () => {
    fixture();
    const withEnrichment = MOCK_INCIDENTS.find((incident) => incident.enrichments.some((e) => e.status === 'completed'));
    renderPage(<IncidentDetailPanel selectedId={withEnrichment?.id ?? null} />, '/app', CAREGIVER);
    expect(await screen.findByText(/ai second opinion/i)).toBeDefined();
    expect(screen.queryByText('Detector details')).toBeNull();
    expect(screen.getByText(/ai second opinion/i).textContent).not.toContain('·');
  });

  it('guides the user when nothing is selected', () => {
    fixture();
    renderPage(<IncidentDetailPanel selectedId={null} />);
    expect(screen.getByText('Select an incident')).toBeDefined();
  });
});

describe('Review queue', () => {
  it('records F as a false alarm and saves the note', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    renderPage(<ReviewQueuePage />, '/app/review');
    const button = await screen.findByRole('button', { name: /false alarm/i });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    const note = screen.getByLabelText('Note (optional)');
    expect(note.getAttribute('maxlength')).toBe('500');
    fireEvent.change(note, { target: { value: 'Sat down on purpose' } });
    expect(screen.getByText('19/500')).toBeDefined();
    fireEvent.keyDown(window, { key: 'f' });
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.any(String), { label: 'non_fall', notes: 'Sat down on purpose' }));
    expect(await screen.findByText(/1 of .*reviewed this session/i)).toBeDefined();
  });

  it('skips without recording a decision or carrying a note to another incident', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    renderPage(<ReviewQueuePage />, '/app/review');
    const button = await screen.findByRole('button', { name: /skip for now/i });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'For this incident only' } });
    fireEvent.click(button);
    await waitFor(() => expect((screen.getByLabelText('Note (optional)') as HTMLTextAreaElement).value).toBe(''));
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByText(/0 of .*reviewed this session/i)).toBeDefined();
  });

  it('keeps the current incident and note when saving fails', async () => {
    const api = fixture();
    api.setFailureMode('reviews');
    renderPage(<ReviewQueuePage />, '/app/review');
    const button = await screen.findByRole('button', { name: /real fall/i });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'Keep this note' } });
    fireEvent.click(button);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect((screen.getByLabelText('Note (optional)') as HTMLTextAreaElement).value).toBe('Keep this note');
    expect(screen.getByText(/0 of .*reviewed this session/i)).toBeDefined();
  });

  it('lists every unreviewed incident, not only AI-flagged ones', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'listIncidents');
    renderPage(<ReviewQueuePage />, '/app/review');
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.objectContaining({ reviewed: false })));
    expect(spy.mock.calls.every(([params]) => !params?.needs_review)).toBe(true);
  });

  it('records a real fall with the R shortcut and updates the session progress', async () => {
    const api = fixture();
    const spy = vi.spyOn(api, 'submitReview');
    renderPage(<ReviewQueuePage />, '/app/review');
    const realFall = await screen.findByRole('button', { name: /real fall/i });
    await waitFor(() => expect((realFall as HTMLButtonElement).disabled).toBe(false));
    fireEvent.keyDown(window, { key: 'r' });
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.any(String), { label: 'confirmed_fall' }), { timeout: 3000 });
    expect(await screen.findByText(/1 of .*reviewed this session/i)).toBeDefined();
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
