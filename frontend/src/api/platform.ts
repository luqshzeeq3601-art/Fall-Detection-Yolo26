/**
 * Endpoints beyond the Phase 5 incident contracts: accounts, live video,
 * aggregates, telemetry, workspace settings and camera management.
 * Sources: src/eldercare/api/routers/{auth,live,settings,cameras,incidents}.py
 */
import { apiBaseUrl } from './index.ts';
import { requestJson } from './client.ts';
import type { Camera } from './types.ts';

const url = (path: string): string => `${apiBaseUrl()}${path}`;
const enc = encodeURIComponent;
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

// -- accounts -----------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'operator' | string;
  organization: string | null;
  care_setting: string | null;
  job_role: string | null;
  created_at: string;
}

export interface SignUpPayload {
  full_name: string;
  email: string;
  password: string;
  organization?: string;
  care_setting?: 'home' | 'facility';
  job_role?: 'caregiver' | 'facility-admin';
}

export const authApi = {
  me: (): Promise<User> => requestJson<User>(url('/auth/me')),
  login: (email: string, password: string, remember: boolean): Promise<User> =>
    requestJson<User>(url('/auth/login'), json('POST', { email, password, remember })),
  signup: (payload: SignUpPayload): Promise<User> =>
    requestJson<User>(url('/auth/signup'), json('POST', payload)),
  logout: (): Promise<void> => requestJson<void>(url('/auth/logout'), json('POST')),
  changePassword: (current_password: string, new_password: string): Promise<void> =>
    requestJson<void>(url('/auth/password'), json('POST', { current_password, new_password })),
  team: (): Promise<User[]> => requestJson<User[]>(url('/auth/users')),
};

// -- live video -----------------------------------------------------------------

export type SourceType = 'webcam' | 'file';

export interface VideoFile {
  ref: string;
  name: string;
  kind: 'upload' | 'sample';
  size_bytes: number;
  /** Dataset clips only: what the clip contains, from its URFD file name. */
  expected: 'fall' | 'no_fall' | null;
}

export interface DetectedCamera {
  index: number;
  label: string;
  camera_id: string;
  width: number | null;
  height: number | null;
  in_use: boolean;
}

export interface FallDetection {
  video_time: number;
  incident_id: string | null;
  fall_score: number;
  track_id: number;
}

export interface LiveSources {
  webcams: { source: string; label: string }[];
  files: VideoFile[];
}

export type LivePhase = 'starting' | 'running' | 'finished' | 'stopped' | 'error';
export type LiveState = 'NO_PERSON' | 'NORMAL' | 'FALLING' | 'FALL_DETECTED';

export interface LiveSessionStatus {
  camera_id: string;
  source_type: SourceType;
  source: string;
  source_label: string;
  phase: LivePhase;
  active: boolean;
  error: string | null;
  detector_ready: boolean;
  state: LiveState;
  confidence: number;
  track_id: number | null;
  fall_likelihood: number | null;
  video_time: number;
  frames: number;
  falls: number;
  last_incident_id: string | null;
  fps: number;
  latency_avg_ms: number;
  latency_p95_ms: number;
  duration: number | null;
  detections: FallDetection[];
  trace: [number, number][];
  started_at: string;
}

export interface StreamMetrics {
  active_streams: number;
  fps: number;
  latency_avg_ms: number;
  latency_p95_ms: number;
}

export interface CameraSource {
  camera_id: string;
  source_type: SourceType;
  source: string;
  room: string | null;
  loop: boolean;
}

export const liveApi = {
  sources: (): Promise<LiveSources> => requestJson<LiveSources>(url('/live/sources')),
  status: (): Promise<{ sessions: LiveSessionStatus[]; metrics: StreamMetrics }> =>
    requestJson(url('/live/status')),
  upload: (file: File): Promise<VideoFile> => {
    const body = new FormData();
    body.append('file', file);
    return requestJson<VideoFile>(url('/live/uploads'), { method: 'POST', body });
  },
  /** Upload with progress reporting (fetch cannot report upload progress). */
  uploadWithProgress: (file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<VideoFile> =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url('/live/uploads'));
      xhr.withCredentials = true;
      xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
      xhr.onload = () => {
        let parsed: unknown = null;
        try { parsed = JSON.parse(xhr.responseText); } catch { /* reported below */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(parsed as VideoFile);
        else reject(new Error((parsed as { error?: { message?: string } } | null)?.error?.message ?? `Upload failed (${xhr.status}).`));
      };
      xhr.onerror = () => reject(new Error('Upload failed: the server could not be reached.'));
      xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));
      signal?.addEventListener('abort', () => xhr.abort(), { once: true });
      const form = new FormData();
      form.append('file', file);
      xhr.send(form);
    }),
  deleteUpload: (name: string): Promise<void> => requestJson<void>(url(`/live/uploads/${enc(name)}`), json('DELETE')),
  detectCameras: (): Promise<{ cameras: DetectedCamera[] }> => requestJson(url('/live/cameras')),
  startSource: (source_type: SourceType, source: string, loop = false): Promise<LiveSessionStatus> =>
    requestJson(url('/live/start'), json('POST', { source_type, source, loop })),
  test: (source_type: SourceType, source: string): Promise<{ ok: boolean; detail: string }> =>
    requestJson(url('/live/test'), json('POST', { source_type, source })),
  cameraSources: (): Promise<CameraSource[]> => requestJson<CameraSource[]>(url('/live/camera-sources')),
  setCameraSource: (
    cameraId: string,
    value: { source_type: SourceType; source: string; room?: string | null; loop?: boolean },
  ): Promise<CameraSource> => requestJson<CameraSource>(url(`/cameras/${enc(cameraId)}/source`), json('PUT', value)),
  start: (
    cameraId: string,
    value: { source_type?: SourceType; source?: string; loop?: boolean } = {},
  ): Promise<LiveSessionStatus> => requestJson(url(`/cameras/${enc(cameraId)}/stream/start`), json('POST', value)),
  stop: (cameraId: string): Promise<{ stopped: boolean }> =>
    requestJson(url(`/cameras/${enc(cameraId)}/stream/stop`), json('POST')),
  streamUrl: (cameraId: string, startedAt: string): string =>
    url(`/cameras/${enc(cameraId)}/stream.mjpg?t=${enc(startedAt)}`),
  snapshotUrl: (cameraId: string): string => url(`/cameras/${enc(cameraId)}/snapshot.jpg`),
};

// -- cameras ----------------------------------------------------------------------

export const cameraApi = {
  create: (id: string, name: string): Promise<Camera> =>
    requestJson<Camera>(url('/cameras'), json('POST', { id, name, enabled: true })),
  update: (id: string, value: { name?: string; enabled?: boolean }): Promise<Camera> =>
    requestJson<Camera>(url(`/cameras/${enc(id)}`), json('PATCH', value)),
  remove: (id: string): Promise<void> => requestJson<void>(url(`/cameras/${enc(id)}`), json('DELETE')),
};

// -- incidents aggregates / export ---------------------------------------------

export interface IncidentStats {
  total: number;
  today: number;
  unreviewed: number;
  reviewed: number;
  confirmed_falls: number;
  false_alarms: number;
  last_7_days: { date: string; count: number }[];
}

/** ISO string for the start of the caller's local day, with its UTC offset. */
export function localDayStart(now = new Date()): string {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const offset = -start.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const pad = (n: number): string => String(Math.floor(Math.abs(n))).padStart(2, '0');
  const y = start.getFullYear();
  return `${y}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}T00:00:00${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
}

export const incidentApi = {
  stats: (): Promise<IncidentStats> =>
    requestJson<IncidentStats>(url(`/incidents/stats?day_start=${enc(localDayStart())}`)),
  /** Download the reviewed-incident JSONL manifest; returns the record count. */
  exportDataset: async (options: { ids?: string[]; includeUncertain?: boolean } = {}): Promise<number> => {
    const params = new URLSearchParams();
    for (const id of options.ids ?? []) params.append('ids', id);
    if (options.includeUncertain !== undefined) params.set('include_uncertain', String(options.includeUncertain));
    const query = params.toString();
    const response = await fetch(url(`/incidents/export.jsonl${query ? `?${query}` : ''}`), { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Export failed (${response.status}).`);
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'eldercare-reviewed.jsonl';
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    return Number(response.headers.get('X-Record-Count') ?? '0');
  },
};

// -- telemetry ------------------------------------------------------------------------

export interface TelemetrySample extends StreamMetrics {
  timestamp: string;
  cpu_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  gpu_percent: number | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
}

export const telemetryApi = {
  metrics: (): Promise<{ current: TelemetrySample; history: TelemetrySample[] }> =>
    requestJson(url('/system/metrics')),
};

// -- workspace settings -------------------------------------------------------------

export interface WorkspaceSettings {
  fall_threshold: number | null;
  min_down_sec: number | null;
  show_skeleton: boolean;
  show_bbox: boolean;
  blur_faces: boolean;
  browser_alerts: boolean;
  alert_sound: boolean;
  retention_days: number | null;
  export_include_uncertain: boolean;
}

export interface SettingsResponse {
  settings: WorkspaceSettings;
  frozen_defaults: { fall_threshold: number | null; min_down_sec: number | null };
}

export const settingsApi = {
  get: (): Promise<SettingsResponse> => requestJson<SettingsResponse>(url('/settings')),
  put: (value: WorkspaceSettings): Promise<WorkspaceSettings> =>
    requestJson<WorkspaceSettings>(url('/settings'), json('PUT', value)),
};
