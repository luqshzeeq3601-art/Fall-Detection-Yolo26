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
  });

  it('lists detected cameras and starts monitoring the chosen one', async () => {
    const state = defaultState();
    state.cameras = [{ index: 0, label: 'Camera 0 (default)', camera_id: 'webcam-0', width: 1280, height: 720, in_use: false }];
    const { calls } = installFakeApi(state);
    renderPage(<LiveMonitor />, '/app/surveillance');
    fireEvent.click(await screen.findByRole('radio', { name: /camera 0 \(default\)/i }));
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
});
