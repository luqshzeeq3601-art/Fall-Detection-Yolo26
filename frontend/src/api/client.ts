import type {
  Camera,
  HealthResponse,
  Incident,
  IncidentDetail,
  IncidentFilterParams,
  IncidentReview,
  IncidentReviewCreate,
  PaginatedIncidents,
  ReadyResponse,
  SystemStatusResponse,
} from './types.ts';

export interface ApiClient {
  getHealth(): Promise<HealthResponse>;
  getReady(): Promise<ReadyResponse>;
  getSystemStatus(): Promise<SystemStatusResponse>;
  listCameras(): Promise<Camera[]>;
  getCamera(cameraId: string): Promise<Camera>;
  listIncidents(params?: IncidentFilterParams): Promise<PaginatedIncidents>;
  getIncident(incidentId: string): Promise<IncidentDetail>;
  listReviews(incidentId: string): Promise<IncidentReview[]>;
  submitReview(
    incidentId: string,
    payload: IncidentReviewCreate,
  ): Promise<IncidentReview>;
  evidenceUrl(incidentId: string, evidenceId: string): string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function encodeParams(params?: IncidentFilterParams): string {
  if (!params) return '';
  const search = new URLSearchParams();
  if (params.camera_id) search.set('camera_id', params.camera_id);
  if (params.status) search.set('status', params.status);
  if (params.review_label) search.set('review_label', params.review_label);
  if (params.needs_review !== undefined) {
    search.set('needs_review', String(params.needs_review));
  }
  if (params.reviewed !== undefined) search.set('reviewed', String(params.reviewed));
  if (params.q) search.set('q', params.q);
  if (params.from) search.set('from', params.from);
  if (params.to) search.set('to', params.to);
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  if (params.cursor) search.set('cursor', params.cursor);
  const query = search.toString();
  return query ? `?${query}` : '';
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    throw new ApiError(response.status, `HTTP_${response.status}`, 'Empty response body');
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(
      response.status,
      `HTTP_${response.status}`,
      'Invalid JSON response from server',
    );
  }
}

/** Fired on any 401 so the auth layer can return the user to sign-in. */
export const UNAUTHORIZED_EVENT = 'eldercare:unauthorized';

/**
 * Shared fetch wrapper: JSON (or FormData) bodies, cookie session, error envelope
 * mapping to ApiError. 204 responses resolve to undefined.
 */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const isForm = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  try {
    response = await fetch(url, {
      credentials: 'same-origin',
      ...init,
      headers: isForm ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Network request failed');
  }
  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    let message = `Request failed with status ${response.status}`;
    let requestId: string | undefined;
    try {
      const body = (await response.json()) as {
        error?: { code?: string; message?: string; request_id?: string };
      };
      if (body.error?.code) code = body.error.code;
      if (body.error?.message) message = body.error.message;
      requestId = body.error?.request_id;
    } catch {
      // Keep generic message; never surface raw stack traces.
    }
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(response.status, code, message, requestId);
  }
  if (response.status === 204) return undefined as T;
  return parseJson<T>(response);
}

/**
 * HTTP implementation of the Phase 5 REST contracts.
 * All fetch logic lives here; components must use hooks / this client.
 */
export class HttpApiClient implements ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private request<T>(path: string, init?: RequestInit): Promise<T> {
    return requestJson<T>(this.url(path), init);
  }

  getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  getReady(): Promise<ReadyResponse> {
    return this.request<ReadyResponse>('/ready');
  }

  getSystemStatus(): Promise<SystemStatusResponse> {
    return this.request<SystemStatusResponse>('/system/status');
  }

  listCameras(): Promise<Camera[]> {
    return this.request<Camera[]>('/cameras');
  }

  getCamera(cameraId: string): Promise<Camera> {
    return this.request<Camera>(`/cameras/${encodeURIComponent(cameraId)}`);
  }

  listIncidents(params?: IncidentFilterParams): Promise<PaginatedIncidents> {
    return this.request<PaginatedIncidents>(`/incidents${encodeParams(params)}`);
  }

  getIncident(incidentId: string): Promise<IncidentDetail> {
    return this.request<IncidentDetail>(
      `/incidents/${encodeURIComponent(incidentId)}`,
    );
  }

  listReviews(incidentId: string): Promise<IncidentReview[]> {
    return this.request<IncidentReview[]>(
      `/incidents/${encodeURIComponent(incidentId)}/reviews`,
    );
  }

  submitReview(
    incidentId: string,
    payload: IncidentReviewCreate,
  ): Promise<IncidentReview> {
    return this.request<IncidentReview>(
      `/incidents/${encodeURIComponent(incidentId)}/reviews`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  }

  evidenceUrl(incidentId: string, evidenceId: string): string {
    return this.url(
      `/incidents/${encodeURIComponent(incidentId)}/evidence/${encodeURIComponent(evidenceId)}`,
    );
  }
}

export function isNotFoundError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 ||
      error.code === 'INCIDENT_NOT_FOUND' ||
      error.code === 'CAMERA_NOT_FOUND' ||
      error.code === 'EVIDENCE_NOT_FOUND' ||
      error.code === 'EVIDENCE_FILE_NOT_FOUND')
  );
}

export type { Incident };
