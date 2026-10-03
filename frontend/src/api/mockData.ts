import type {
  Camera,
  IncidentDetail,
  ReadyResponse,
  SystemStatusResponse,
  WsEvent,
} from './types.ts';

/**
 * Deterministic mock fixtures mirroring real Phase 5 response shapes.
 * All IDs / timestamps are fixed so tests are repeatable.
 * No RTSP URLs, credentials, or invented backend fields.
 */

export const MOCK_CAMERAS: Camera[] = [
  {
    id: 'cam-01',
    name: 'Hallway Camera',
    status: 'online',
    last_frame_at: '2026-09-23T08:00:00Z',
    last_heartbeat_at: '2026-09-23T08:00:05Z',
    reconnect_count: 0,
  },
  {
    id: 'cam-02',
    name: 'Lounge Camera',
    status: 'degraded',
    last_frame_at: '2026-09-23T07:58:40Z',
    last_heartbeat_at: '2026-09-23T07:59:50Z',
    reconnect_count: 2,
  },
  {
    id: 'cam-03',
    name: 'Entrance Camera',
    status: 'offline',
    last_frame_at: null,
    last_heartbeat_at: '2026-09-23T07:30:00Z',
    reconnect_count: 5,
  },
];

export const MOCK_SYSTEM_STATUS: SystemStatusResponse = {
  version: '1.0.0',
  model_name: 'yolo26s-pose.pt',
  model_version: '1.0.0',
  config_version: '1.0.0',
  camera_count: 3,
  vision_fps: 30.0,
  inference_latency_ms: { avg: 12.4, p95: 18.2 },
  gpu_summary: {
    device: 'cpu',
    name: 'Host CPU',
    memory_allocated_mb: 0.0,
    memory_total_mb: 0.0,
  },
  integrations: { mqtt: 'disabled', vlm: 'disabled' },
};

export const MOCK_READY: ReadyResponse = {
  status: 'ready',
  database: 'ready',
  vision_service: 'ready',
  mqtt: 'disabled',
  vlm: 'disabled',
};

export const MOCK_INCIDENTS: IncidentDetail[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    camera_id: 'cam-01',
    track_id: '7',
    started_at: '2026-09-23T07:10:00Z',
    confirmed_at: '2026-09-23T07:10:04Z',
    ended_at: null,
    detector_state: 'FALL_CONFIRMED',
    fall_score: 0.87,
    model_name: 'yolo26s-pose.pt',
    model_version: '1.0.0',
    config_version: '1.0.0',
    evidence_features: {
      rapid_vertical_drop: true,
      orientation_change: true,
      ground_posture_persisted: true,
    },
    created_at: '2026-09-23T07:10:05Z',
    evidence: [
      {
        id: 'e-0001',
        incident_id: '11111111-1111-4111-8111-111111111111',
        evidence_type: 'snapshot',
        storage_path: 'cam-01/11111111-1111-4111-8111-111111111111/e-0001.jpg',
        mime_type: 'image/jpeg',
        sha256:
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        captured_at: '2026-09-23T07:10:04Z',
        created_at: '2026-09-23T07:10:05Z',
      },
    ],
    reviews: [],
    enrichments: [
      {
        id: 'a-demo-0001',
        incident_id: '11111111-1111-4111-8111-111111111111',
        status: 'completed',
        provider: 'synthetic-demo-provider',
        model: 'synthetic-demo-model',
        prompt_version: 'demo-v1',
        output: {
          summary: 'Synthetic demo verdict: uncertain confidence.',
          confidence_assessment: 'uncertain',
          fall_assessment: 'fall',
        },
        error_code: null,
        duration_ms: 12,
        created_at: '2026-09-23T07:10:06Z',
        completed_at: '2026-09-23T07:10:07Z',
      },
    ],
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    camera_id: 'cam-02',
    track_id: '3',
    started_at: '2026-09-23T06:40:00Z',
    confirmed_at: '2026-09-23T06:40:06Z',
    ended_at: '2026-09-23T06:45:00Z',
    detector_state: 'FALL_CONFIRMED',
    fall_score: 0.72,
    model_name: 'yolo26s-pose.pt',
    model_version: '1.0.0',
    config_version: '1.0.0',
    evidence_features: {
      rapid_vertical_drop: true,
      orientation_change: false,
      ground_posture_persisted: true,
    },
    created_at: '2026-09-23T06:40:07Z',
    evidence: [],
    reviews: [
      {
        id: 'r-0001',
        incident_id: '22222222-2222-4222-8222-222222222222',
        label: 'non_fall',
        notes: 'Controlled sitting test.',
        reviewer: 'operator-1',
        created_at: '2026-09-23T06:50:00Z',
      },
    ],
    enrichments: [],
  },
  {
    id: '33333333-3333-4333-8333-333333333333',
    camera_id: 'cam-01',
    track_id: '9',
    started_at: '2026-09-23T05:20:00Z',
    confirmed_at: '2026-09-23T05:20:05Z',
    ended_at: null,
    detector_state: 'FALL_CONFIRMED',
    fall_score: 0.64,
    model_name: 'yolo26s-pose.pt',
    model_version: '1.0.0',
    config_version: '1.0.0',
    evidence_features: {
      rapid_vertical_drop: false,
      orientation_change: true,
      ground_posture_persisted: false,
    },
    created_at: '2026-09-23T05:20:06Z',
    evidence: [],
    reviews: [],
    enrichments: [
      {
        id: 'a-0001',
        incident_id: '33333333-3333-4333-8333-333333333333',
        status: 'completed',
        provider: 'mock-provider',
        model: 'mock-vlm-1',
        prompt_version: 'v1',
        output: {
          summary: 'Synthetic demo verdict: scene assessment is unclear.',
          confidence_assessment: 'high',
          fall_assessment: 'unclear',
        },
        error_code: null,
        duration_ms: 1200,
        created_at: '2026-09-23T05:21:00Z',
        completed_at: '2026-09-23T05:21:02Z',
      },
    ],
  },
];

export const MOCK_WS_EVENTS: WsEvent[] = [
  {
    event_id: 'ev-0001',
    event_type: 'fall.confirmed',
    occurred_at: '2026-09-23T07:10:04Z',
    camera_id: 'cam-01',
    incident_id: '11111111-1111-4111-8111-111111111111',
    payload: {
      track_id: '7',
      fall_score: 0.87,
      model_name: 'yolo26s-pose.pt',
      config_version: '1.0.0',
    },
  },
  {
    event_id: 'ev-0002',
    event_type: 'camera.offline',
    occurred_at: '2026-09-23T07:30:00Z',
    camera_id: 'cam-03',
    incident_id: null,
    payload: {},
  },
  {
    event_id: 'ev-0003',
    event_type: 'camera.reconnected',
    occurred_at: '2026-09-23T07:59:50Z',
    camera_id: 'cam-02',
    incident_id: null,
    payload: { reconnect_count: 2 },
  },
];
