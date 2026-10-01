/**
 * Typed frontend models derived strictly from Phase 5 backend contracts.
 *
 * Sources of truth:
 * - docs/planning/API_SPEC.md
 * - src/eldercare/api/schemas.py (HealthResponse, ReadyResponse,
 *   LatencySummary, GpuSummary, SystemStatusResponse, CameraRead,
 *   WebSocketEvent)
 * - src/eldercare/incidents/schemas.py (IncidentRead, IncidentDetailRead,
 *   IncidentEvidenceRead, IncidentReviewRead, AgentEnrichmentRead,
 *   PaginatedIncidents, IncidentReviewCreate, ReviewLabel)
 * - src/eldercare/api/routers/*.py (query params, routes, error envelope)
 *
 * Rules:
 * - No invented backend fields.
 * - No RTSP URL / credential fields anywhere.
 * - Timestamps are ISO-8601 strings as transported over JSON.
 */

export interface HealthResponse {
  status: string;
}

export interface ReadyResponse {
  status: string;
  database: string;
  vision_service: string;
  mqtt?: string | null;
  vlm?: string | null;
}

export interface LatencySummary {
  avg: number;
  p95: number;
}

export interface GpuSummary {
  device: string;
  name: string;
  memory_allocated_mb?: number | null;
  memory_total_mb?: number | null;
}

export interface SystemStatusResponse {
  version: string;
  model_name: string;
  model_version: string;
  config_version: string;
  camera_count: number;
  vision_fps: number;
  inference_latency_ms: LatencySummary;
  gpu_summary: GpuSummary;
  integrations: Record<string, string>;
}

export type CameraStatus = string;

export interface Camera {
  id: string;
  name: string;
  status: CameraStatus;
  last_frame_at: string | null;
  last_heartbeat_at: string | null;
  reconnect_count: number;
}

export type ReviewLabel = 'confirmed_fall' | 'non_fall' | 'uncertain';

export const REVIEW_LABELS: readonly ReviewLabel[] = [
  'confirmed_fall',
  'non_fall',
  'uncertain',
] as const;

export function isReviewLabel(value: string): value is ReviewLabel {
  return (REVIEW_LABELS as readonly string[]).includes(value);
}

export interface IncidentEvidence {
  id: string;
  incident_id: string;
  evidence_type: string;
  storage_path: string;
  mime_type: string;
  sha256: string;
  captured_at: string;
  created_at: string;
}

export interface IncidentReview {
  id: string;
  incident_id: string;
  label: string;
  notes: string | null;
  reviewer: string | null;
  created_at: string;
}

export interface AgentEnrichment {
  id: string;
  incident_id: string;
  status: string;
  provider: string | null;
  model: string | null;
  prompt_version: string;
  output: Record<string, unknown> | null;
  error_code: string | null;
  duration_ms: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface Incident {
  id: string;
  camera_id: string;
  track_id: string;
  started_at: string;
  confirmed_at: string;
  ended_at: string | null;
  detector_state: string;
  fall_score: number;
  model_name: string;
  model_version: string;
  config_version: string;
  evidence_features: Record<string, unknown>;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  evidence: IncidentEvidence[];
  reviews: IncidentReview[];
  enrichments: AgentEnrichment[];
}

export interface PaginatedIncidents {
  items: Incident[];
  total: number;
  limit: number;
  offset: number;
}

export interface IncidentFilterParams {
  camera_id?: string;
  status?: string;
  review_label?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
  cursor?: string;
}

export interface IncidentReviewCreate {
  label: ReviewLabel;
  notes?: string;
  reviewer?: string;
}

export type WsEventType =
  | 'camera.online'
  | 'camera.degraded'
  | 'camera.offline'
  | 'camera.reconnected'
  | 'fall.candidate'
  | 'fall.confirmed'
  | 'fall.recovered'
  | 'incident.persisted'
  | 'incident.reviewed'
  | 'agent.enrichment_queued'
  | 'agent.enrichment_completed'
  | 'agent.enrichment_failed'
  | 'service.degraded'
  | 'service.recovered'
  | (string & {});

export interface WsEvent {
  event_id: string;
  event_type: WsEventType;
  occurred_at: string;
  camera_id?: string | null;
  incident_id?: string | null;
  payload: Record<string, unknown>;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}
