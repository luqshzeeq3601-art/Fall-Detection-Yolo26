/**
 * Test double for the platform endpoints (`src/api/platform.ts`), installed as a
 * `fetch` stub. Incident/camera reads still go through MockApiClient (VITE_USE_MOCK).
 */
import { vi } from 'vitest';
import type { IncidentStats, LiveSessionStatus, SettingsResponse, TelemetrySample, VideoFile } from '../api/platform.ts';

export interface FakeApiState {
  stats: IncidentStats;
  sessions: LiveSessionStatus[];
  files: VideoFile[];
  cameras: { index: number; label: string; camera_id: string; width: number | null; height: number | null; in_use: boolean }[];
  settings: SettingsResponse;
}

export interface FakeCall {
  method: string;
  path: string;
  body: unknown;
}

const SAMPLE: TelemetrySample = {
  timestamp: '2026-10-02T08:00:00Z', cpu_percent: 42, memory_used_gb: 6.2, memory_total_gb: 16, gpu_percent: null,
  gpu_memory_used_mb: null, gpu_memory_total_mb: null, active_streams: 0, fps: 0, latency_avg_ms: 0, latency_p95_ms: 0,
};

export function session(overrides: Partial<LiveSessionStatus> = {}): LiveSessionStatus {
  return {
    camera_id: 'video-analysis', source_type: 'file', source: 'sample:fall-01-cam0.mp4', source_label: 'fall-01-cam0.mp4',
    phase: 'finished', active: false, error: null, detector_ready: true, state: 'NO_PERSON', confidence: 0, track_id: null,
    fall_likelihood: null, video_time: 5.2, frames: 156, falls: 1, last_incident_id: 'inc-1', fps: 10, latency_avg_ms: 60,
    latency_p95_ms: 90, duration: 5.2, detections: [{ video_time: 3.5, incident_id: 'inc-1', fall_score: 1, track_id: 1 }],
    trace: [[0, 0], [1, 0.1], [2, 0.4], [3, 0.9], [3.5, 1], [4, 0.95]], started_at: '2026-10-02T08:00:00Z',
    ...overrides,
  };
}

export function defaultState(): FakeApiState {
  return {
    stats: { total: 4, today: 1, unreviewed: 2, reviewed: 2, confirmed_falls: 1, false_alarms: 1, last_7_days: Array.from({ length: 7 }, (_, i) => ({ date: `2026-09-${String(20 + i).padStart(2, '0')}`, count: i % 2 })) },
    sessions: [],
    files: [
      { ref: 'sample:adl-01-cam0.mp4', name: 'adl-01-cam0.mp4', kind: 'sample', size_bytes: 1_200_000, expected: 'no_fall' },
      { ref: 'sample:fall-01-cam0.mp4', name: 'fall-01-cam0.mp4', kind: 'sample', size_bytes: 1_200_000, expected: 'fall' },
      { ref: 'upload:kitchen.mp4', name: 'kitchen.mp4', kind: 'upload', size_bytes: 3_000_000, expected: null },
    ],
    cameras: [],
    settings: {
      settings: { fall_threshold: null, min_down_sec: null, show_skeleton: true, show_bbox: true, blur_faces: false, browser_alerts: true, alert_sound: false, retention_days: null, export_include_uncertain: false },
      frozen_defaults: { fall_threshold: 0.55, min_down_sec: 0.45 },
    },
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export function installFakeApi(state: FakeApiState = defaultState()): { state: FakeApiState; calls: FakeCall[] } {
  const calls: FakeCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input), 'http://localhost');
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) as unknown : null;
    calls.push({ method, path: `${path}${url.search}`, body });
    if (path === '/incidents/stats') return json(state.stats);
    if (path === '/live/status') return json({ sessions: state.sessions, metrics: { active_streams: state.sessions.filter((s) => s.active).length, fps: 0, latency_avg_ms: 0, latency_p95_ms: 0 } });
    if (path === '/live/sources') return json({ webcams: [], files: state.files });
    if (path === '/live/cameras') return json({ cameras: state.cameras });
    if (path === '/live/start' && method === 'POST') {
      const request = body as { source_type: 'webcam' | 'file'; source: string };
      const started = session({ camera_id: request.source_type === 'webcam' ? `webcam-${request.source}` : 'video-analysis', source_type: request.source_type, source: request.source, phase: 'running', active: true, falls: 0, detections: [] });
      state.sessions = [started];
      return json(started);
    }
    if (path.endsWith('/stream/stop')) { state.sessions = state.sessions.map((s) => ({ ...s, active: false, phase: 'stopped' })); return json({ stopped: true }); }
    if (path === '/settings' && method === 'GET') return json(state.settings);
    if (path === '/settings' && method === 'PUT') { state.settings = { ...state.settings, settings: body as SettingsResponse['settings'] }; return json(body); }
    if (path === '/system/metrics') return json({ current: SAMPLE, history: [SAMPLE, SAMPLE] });
    if (path === '/auth/users') return json([]);
    if (path === '/incidents/export.jsonl') return new Response('{}\n', { status: 200, headers: { 'X-Record-Count': '1', 'Content-Disposition': 'attachment; filename="x.jsonl"' } });
    return json({ error: { code: 'HTTP_404', message: `No fake for ${method} ${path}` } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { state, calls };
}
