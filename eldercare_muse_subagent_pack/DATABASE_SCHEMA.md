# Database Schema — ElderCare Vision

PostgreSQL is the system of record.

## 1. `cameras`

| Column | Type | Notes |
|---|---|---|
| id | text/uuid | PK |
| name | text | human-readable |
| enabled | boolean | default true |
| status | enum/text | online/degraded/offline/unknown |
| last_frame_at | timestamptz | nullable |
| last_heartbeat_at | timestamptz | nullable |
| reconnect_count | integer | >=0 |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Do not store plaintext RTSP credentials unless encrypted secret storage is explicitly implemented.

## 2. `incidents`

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| camera_id | FK | |
| track_id | text | tracker identity at event time |
| started_at | timestamptz | candidate onset |
| confirmed_at | timestamptz | confirmation |
| ended_at | timestamptz | nullable |
| detector_state | text | confirmed |
| fall_score | numeric | calibrated engine score |
| model_name | text | e.g. yolo26s-pose.pt |
| model_version | text | package/checkpoint fingerprint where available |
| config_version | text | fall configuration fingerprint/version |
| evidence_features | jsonb | explainable trigger data |
| created_at | timestamptz | |

Indexes:

- `(camera_id, confirmed_at desc)`
- `(confirmed_at desc)`

## 3. `incident_evidence`

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| incident_id | FK | |
| evidence_type | text | snapshot / clip |
| storage_path | text | internal controlled path/reference |
| mime_type | text | |
| sha256 | text | integrity |
| captured_at | timestamptz | |
| created_at | timestamptz | |

## 4. `incident_reviews`

Append-only review history.

| Column | Type |
|---|---|
| id | uuid |
| incident_id | FK |
| label | confirmed_fall / non_fall / uncertain |
| notes | text nullable |
| reviewer | text nullable for POC |
| created_at | timestamptz |

Do not overwrite previous reviews.

## 5. `agent_enrichments`

| Column | Type |
|---|---|
| id | uuid |
| incident_id | FK |
| status | pending/running/completed/failed |
| provider | text nullable |
| model | text nullable |
| prompt_version | text |
| output | jsonb nullable |
| error_code | text nullable |
| duration_ms | integer nullable |
| created_at | timestamptz |
| completed_at | timestamptz nullable |

Never mix generated enrichment fields into the original detector evidence JSON.

## 6. `service_metrics_samples` (optional persistence)

Prefer a metrics system for high-frequency telemetry. If PostgreSQL samples are retained, downsample them.

Possible fields:

- service
- camera_id
- timestamp
- processed_fps
- inference_p50_ms
- inference_p95_ms
- gpu_util_pct
- gpu_vram_mb
- cpu_pct
- ram_mb
- dropped_frames

## 7. Migrations

All schema changes use Alembic.

Rules:

- migration must have upgrade/downgrade where practical,
- destructive migrations require explicit review,
- application startup must not silently auto-create production schema outside migration workflow.
