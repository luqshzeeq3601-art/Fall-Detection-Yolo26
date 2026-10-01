import { ApiError, type ApiClient } from './client.ts';
import {
  MOCK_CAMERAS,
  MOCK_INCIDENTS,
  MOCK_READY,
  MOCK_SYSTEM_STATUS,
} from './mockData.ts';
import type {
  Camera,
  HealthResponse,
  IncidentDetail,
  IncidentFilterParams,
  IncidentReview,
  IncidentReviewCreate,
  PaginatedIncidents,
  ReadyResponse,
  SystemStatusResponse,
  WsEvent,
} from './types.ts';
import { MOCK_WS_EVENTS } from './mockData.ts';
import { isReviewLabel } from './types.ts';

export type MockFailureMode =
  | 'none'
  | 'health'
  | 'ready'
  | 'system'
  | 'cameras'
  | 'incidents'
  | 'reviews';

function notFound(code: string, message: string): ApiError {
  return new ApiError(404, code, message);
}

/**
 * Deterministic in-memory mock implementing the same ApiClient interface
 * as the HTTP client. Supports success + failure cases for tests and
 * local development without network. Swap to HttpApiClient via
 * VITE_USE_MOCK=false for the real FastAPI backend.
 */
export class MockApiClient implements ApiClient {
  private failure: MockFailureMode = 'none';
  private incidents: IncidentDetail[];
  private reviewSeq = 100;

  constructor() {
    this.incidents = structuredClone(MOCK_INCIDENTS);
  }

  setFailureMode(mode: MockFailureMode): void {
    this.failure = mode;
  }

  reset(): void {
    this.failure = 'none';
    this.incidents = structuredClone(MOCK_INCIDENTS);
    this.reviewSeq = 100;
  }

  private maybeFail(mode: MockFailureMode, code: string, message: string): void {
    if (this.failure === mode) {
      throw new ApiError(500, code, message);
    }
  }

  async getHealth(): Promise<HealthResponse> {
    this.maybeFail('health', 'MOCK_HEALTH_FAILURE', 'Mock health failure');
    return { status: 'ok' };
  }

  async getReady(): Promise<ReadyResponse> {
    this.maybeFail('ready', 'MOCK_READY_FAILURE', 'Mock readiness failure');
    return structuredClone(MOCK_READY);
  }

  async getSystemStatus(): Promise<SystemStatusResponse> {
    this.maybeFail('system', 'MOCK_SYSTEM_FAILURE', 'Mock system failure');
    return structuredClone(MOCK_SYSTEM_STATUS);
  }

  async listCameras(): Promise<Camera[]> {
    this.maybeFail('cameras', 'MOCK_CAMERAS_FAILURE', 'Mock cameras failure');
    return structuredClone(MOCK_CAMERAS);
  }

  async getCamera(cameraId: string): Promise<Camera> {
    this.maybeFail('cameras', 'MOCK_CAMERAS_FAILURE', 'Mock cameras failure');
    const found = MOCK_CAMERAS.find((c) => c.id === cameraId);
    if (!found) throw notFound('CAMERA_NOT_FOUND', `Camera '${cameraId}' not found.`);
    return structuredClone(found);
  }

  async listIncidents(params?: IncidentFilterParams): Promise<PaginatedIncidents> {
    this.maybeFail('incidents', 'MOCK_INCIDENTS_FAILURE', 'Mock incidents failure');
    let items = [...this.incidents];
    if (params?.camera_id) items = items.filter((i) => i.camera_id === params.camera_id);
    if (params?.status) items = items.filter((i) => i.detector_state === params.status);
    if (params?.review_label) {
      items = items.filter((i) => i.reviews.some((r) => r.label === params.review_label));
    }
    const total = items.length;
    const limit = params?.limit ?? 50;
    const offset = params?.offset ?? 0;
    const page = items.slice(offset, offset + limit).map((detail) => ({
      id: detail.id,
      camera_id: detail.camera_id,
      track_id: detail.track_id,
      started_at: detail.started_at,
      confirmed_at: detail.confirmed_at,
      ended_at: detail.ended_at,
      detector_state: detail.detector_state,
      fall_score: detail.fall_score,
      model_name: detail.model_name,
      model_version: detail.model_version,
      config_version: detail.config_version,
      evidence_features: detail.evidence_features,
      created_at: detail.created_at,
    }));
    return { items: page, total, limit, offset };
  }

  async getIncident(incidentId: string): Promise<IncidentDetail> {
    this.maybeFail('incidents', 'MOCK_INCIDENTS_FAILURE', 'Mock incidents failure');
    const found = this.incidents.find((i) => i.id === incidentId);
    if (!found) throw notFound('INCIDENT_NOT_FOUND', `Incident '${incidentId}' not found.`);
    return structuredClone(found);
  }

  async listReviews(incidentId: string): Promise<IncidentReview[]> {
    this.maybeFail('reviews', 'MOCK_REVIEWS_FAILURE', 'Mock reviews failure');
    const found = this.incidents.find((i) => i.id === incidentId);
    if (!found) throw notFound('INCIDENT_NOT_FOUND', `Incident '${incidentId}' not found.`);
    return structuredClone(found.reviews);
  }

  async submitReview(
    incidentId: string,
    payload: IncidentReviewCreate,
  ): Promise<IncidentReview> {
    this.maybeFail('reviews', 'MOCK_REVIEWS_FAILURE', 'Mock reviews failure');
    const found = this.incidents.find((i) => i.id === incidentId);
    if (!found) throw notFound('INCIDENT_NOT_FOUND', `Incident '${incidentId}' not found.`);
    if (!isReviewLabel(payload.label)) {
      throw new ApiError(422, 'INVALID_REVIEW_LABEL', `Invalid review label '${payload.label}'.`);
    }
    if (payload.notes !== undefined && payload.notes.length > 2000) {
      throw new ApiError(422, 'VALIDATION_ERROR', 'Review notes exceed 2000 characters.');
    }
    const review: IncidentReview = {
      id: `r-mock-${this.reviewSeq++}`,
      incident_id: incidentId,
      label: payload.label,
      notes: payload.notes ?? null,
      reviewer: payload.reviewer ?? null,
      created_at: '2026-09-23T08:30:00Z',
    };
    found.reviews.push(review);
    return structuredClone(review);
  }

  evidenceUrl(incidentId: string, evidenceId: string): string {
    return `/incidents/${encodeURIComponent(incidentId)}/evidence/${encodeURIComponent(evidenceId)}`;
  }

  /** Deterministic WebSocket/event simulation fixtures for hook tests. */
  getMockEvents(): WsEvent[] {
    return structuredClone(MOCK_WS_EVENTS);
  }
}
