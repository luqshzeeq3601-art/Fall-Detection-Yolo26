# System Architecture — ElderCare Vision

## 1. Architectural goals

- local-first real-time vision,
- bounded latency,
- failure isolation,
- explainable temporal fall evidence,
- reproducible measurement,
- asynchronous Agent/VLM enrichment,
- clear separation between detection and presentation.

## 2. Logical architecture

```text
┌─────────────────────────┐
│ Phone / IP Camera       │
│ RTSP                    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Stream Manager          │
│ decode / health / retry │
└────────────┬────────────┘
             │ latest-frame queue
             ▼
┌─────────────────────────┐
│ Vision Worker           │
│ YOLO26s-Pose            │
│ ByteTrack               │
└────────────┬────────────┘
             │ per-track observations
             ▼
┌─────────────────────────┐
│ Temporal Fall Engine    │
│ state machine + score   │
└────────────┬────────────┘
             │ confirmed/candidate events
             ▼
┌─────────────────────────┐
│ Incident Service        │
│ persist evidence first  │
└───────┬─────────┬───────┘
        │         │
        │         └──────────────┐
        ▼                        ▼
┌──────────────┐        ┌──────────────────┐
│ PostgreSQL   │        │ Async Agent/VLM  │
└──────┬───────┘        │ enrichment       │
       │                └────────┬─────────┘
       │                         │
       │                         ▼
       │                enrichment/review data
       │
       ├───────────────┐
       ▼               ▼
┌──────────────┐  ┌───────────────┐
│ FastAPI      │  │ MQTT Publisher│
│ REST + WS    │  └───────────────┘
└──────┬───────┘
       ▼
┌──────────────┐
│ React UI     │
└──────────────┘
```

## 3. Process boundaries

Recommended services/processes:

### `vision-service`

Owns:

- RTSP decode,
- pose inference,
- tracking,
- temporal state,
- vision telemetry,
- incident-event production.

Must not depend on frontend availability.

### `api-service`

Owns:

- REST API,
- WebSocket fan-out,
- database access,
- human review,
- evidence metadata.

### `agent-worker`

Owns:

- VLM/provider call,
- prompt version,
- enrichment output,
- retry/timeout,
- uncertain-case routing.

### `mqtt-broker`

Mosquitto for local event transport/demo.

### `web`

React static/frontend application.

## 4. Concurrency model

The video path must prefer freshness over processing every frame.

Use:

```text
RTSP decoder
→ bounded queue size 1–2
→ inference worker
```

If inference falls behind, drop stale frames rather than allowing delay to grow indefinitely.

Database/Agent/MQTT work must not execute synchronously inside the capture loop.

## 5. Core interfaces

### Frame observation

Internal object:

```text
camera_id
frame_id
capture_timestamp
decode_timestamp
image
```

### Track observation

```text
camera_id
track_id
timestamp
bbox
keypoints[17]
keypoint_confidence[17]
pose_confidence_summary
```

### Fall decision

```text
camera_id
track_id
timestamp
state
fall_score
evidence_features
config_version
model_version
```

## 6. State ownership

- Stream health: Stream Manager
- Track state/history: Vision Worker / Fall Engine
- Persistent incidents: PostgreSQL
- Review state: API/database
- Agent task state: Agent worker/database
- UI transient state: React

## 7. Failure isolation

| Failure | Expected behavior |
|---|---|
| Camera unavailable | reconnect loop; emit offline |
| YOLO inference exception | log + restart/health failure; never fabricate result |
| Database unavailable | explicit degraded/error path; no fake persistence success |
| MQTT unavailable | queue/drop according to policy; detector continues |
| Agent unavailable | mark enrichment failed/pending; detector continues |
| UI unavailable | detector/API continue |

## 8. Deployment

Docker Compose services:

```text
vision
api
agent-worker
postgres
mosquitto
web
```

GPU access is required only by the vision service unless a local VLM is later added.

## 9. Architecture decisions

See:

- `docs/adr/ADR-001-yolo26s-pose.md`
- `docs/adr/ADR-002-tensorrt-primary.md`
- `docs/adr/ADR-003-agent-decoupling.md`
- `docs/adr/ADR-004-dataset-strategy.md`

## 10. Phase 6 frontend redesign follow-up (2026-10-02)

The frontend has three public UI-only routes and a nested /app dashboard with seven pages. BrowserRouter owns navigation; one dashboard provider owns shared camera/status/readiness queries and one event connection. Evidence/action components are keyed by incident ID/request readiness. Human-review writes remain append-only and original detector output is unchanged.

Demo presentation fixtures, synthetic media, visit-local settings/dataset selection and static evaluation snapshots are separate from backend DTOs. Unsupported API capabilities are visibly unavailable. No backend authentication, live video transport or new operational configuration interface was introduced. Details and evidence: frontend/README.md and docs/task-reports/P6-REDESIGN.md.
