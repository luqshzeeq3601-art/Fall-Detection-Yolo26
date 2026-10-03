import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { defaultState, installFakeApi, session } from '../../test/fakeApi.ts';
import { renderPage } from '../../test/renderPage.tsx';
import { LiveMonitor } from './LiveMonitor.tsx';
import { clipExpectation, clipTitle, sourceTitle } from './sourceLabels.ts';

beforeEach(() => setApiClient(new MockApiClient()));
afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

describe('source labels', () => {
  it('names URFD clips and their expected outcome', () => {
    expect(clipTitle('fall-03-cam0.mp4')).toBe('Fall 03 · camera 0');
    expect(clipTitle('adl-12-cam1.mp4')).toBe('Daily activity 12 · camera 1');
    expect(clipTitle('kitchen.mov')).toBe('kitchen.mov');
    expect(sourceTitle('webcam', '1')).toBe('Camera 1');
    expect(sourceTitle('file', 'upload:my:video.mp4')).toBe('my:video.mp4');
    expect(clipExpectation('sample:fall-01-cam0.mp4')).toBe('fall');
    expect(clipExpectation('sample:adl-01-cam0.mp4')).toBe('no_fall');
    expect(clipExpectation('upload:fall-video.mp4')).toBeNull();
  });
});

describe('Live monitor', () => {
  it('explains what to do when no camera is detected', async () => {
    installFakeApi();
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByText(/no camera found/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /choose a source to start/i }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Choose video source' }));
    expect(document.activeElement?.id).toBe('monitor-source-control');
  });

  it('lists detected cameras and starts monitoring the chosen one', async () => {
    const state = defaultState();
    state.cameras = [{ index: 0, label: 'Camera 0 (default)', camera_id: 'webcam-0', width: 1280, height: 720, in_use: false }];
    const { calls } = installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    await screen.findByRole('option', { name: /camera 0 \(default\)/i });
    fireEvent.change(screen.getByRole('combobox', { name: /select camera/i }), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: /start monitoring camera 0/i }));
    await waitFor(() => expect(calls.some((call) => call.path === '/live/start' && JSON.stringify(call.body) === JSON.stringify({ source_type: 'webcam', source: '0', loop: false }))).toBe(true));
  });

  it('filters dataset clips by their label and analyses one', async () => {
    const { calls } = installFakeApi();
    renderPage(<LiveMonitor />, '/app/surveillance?source=video');
    fireEvent.click(await screen.findByRole('button', { name: /^falls 1$/i }));
    expect(screen.queryByText('Daily activity 01 · camera 0')).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: /fall 01 · camera 0/i }));
    fireEvent.click(screen.getByRole('button', { name: /analyse fall 01 · camera 0/i }));
    await waitFor(() => expect(calls.some((call) => call.path === '/live/start' && (call.body as { source: string }).source === 'sample:fall-01-cam0.mp4')).toBe(true));
  });

  it('checks a finished dataset run against the clip label and links each fall', async () => {
    const state = defaultState();
    state.sessions = [session()];
    installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByText('Analysis finished')).toBeDefined();
    expect(screen.getByText(/matches the label/i)).toBeDefined();
    expect(screen.getByRole('link', { name: /review incident/i }).getAttribute('href')).toBe('/app/incidents?selected=inc-1');
    expect(screen.getByRole('img', { name: /fall likelihood over/i })).toBeDefined();
  });

  it('flags a missed fall as not matching the label', async () => {
    const state = defaultState();
    state.sessions = [session({ falls: 0, detections: [] })];
    installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByText(/does not match the label/i)).toBeDefined();
    expect(screen.getByText(/detector missed it/i)).toBeDefined();
  });

  it('shows uploaded videos in "Your video" with a delete action', async () => {
    installFakeApi();
    renderPage(<LiveMonitor />, '/app/surveillance?source=upload');
    expect(await screen.findByRole('radio', { name: /kitchen\.mp4/i })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Delete kitchen.mp4' })).toBeDefined();
    expect(screen.getByRole('button', { name: /drop a video here or browse/i })).toBeDefined();
  });

  it('shows reported detector values without inventing duration or person count', async () => {
    const state = defaultState();
    state.sessions = [session({ source_type: 'webcam', source: '0', source_label: 'Camera 0', active: true, phase: 'running', state: 'NORMAL', track_id: 7, confidence: 0.93, fall_likelihood: 0.12, frames: 9184, falls: 0, detections: [] })];
    installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByText('Person detected')).toBeDefined();
    expect(screen.getByText('0.93')).toBeDefined();
    expect(screen.getByText('9,184')).toBeDefined();
    expect(screen.getByTitle('Not reported by the detector').textContent).toBe('—');
    expect(screen.getByTitle('Total person count is not reported by the detector').textContent).toBe('—');
  });

  it('explains an unavailable video and still lets the operator stop', async () => {
    const state = defaultState();
    state.sessions = [session({ active: true, phase: 'running' })];
    const { calls } = installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    fireEvent.error(await screen.findByRole('img', { name: /live annotated video/i }));
    expect(screen.getByText('The video could not be loaded. Stop this source and start it again.')).toBeDefined();
    expect(screen.queryByText('Connected')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Stop monitoring' }));
    await waitFor(() => expect(calls.some((call) => call.path.endsWith('/stream/stop'))).toBe(true));
  });

  it('links overlay configuration to the existing detection settings', async () => {
    installFakeApi();
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByRole('link', { name: 'Configure pose overlays' })).toHaveProperty('href', expect.stringContaining('/app/settings?tab=detection'));
  });

  it('announces unavailable live status and disables starting', async () => {
    installFakeApi();
    const originalFetch = globalThis.fetch;
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => String(input).includes('/live/status') ? Promise.reject(new Error('Status connection failed.')) : originalFetch(input, init));
    renderPage(<LiveMonitor />, '/app/surveillance');
    expect(await screen.findByText(/last reported session values may be out of date/i)).toBeDefined();
    expect(screen.queryByText('Monitoring')).toBeNull();
    expect(screen.getByRole('button', { name: /choose a source to start/i }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDefined();
  });
  it('offers caregivers cameras only, without dataset clips or uploads', async () => {
    installFakeApi();
    renderPage(<LiveMonitor />, '/app/surveillance?source=upload', { id: 'cg-1', email: 'c@example.test', full_name: 'Casey Carer', role: 'operator', organization: null, care_setting: null, job_role: 'caregiver', created_at: '2026-01-01T00:00:00Z' });
    expect(await screen.findByText('Cameras connected to the computer running ElderCare Vision.')).toBeDefined();
    expect(screen.queryByRole('tablist', { name: 'Video source type' })).toBeNull();
    expect(screen.queryByText(/drop a video/i)).toBeNull();
    expect(screen.queryByRole('tab', { name: /your video/i })).toBeNull();
  });
});
