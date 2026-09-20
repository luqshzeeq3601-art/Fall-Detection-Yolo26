# Implementation Plan — ElderCare Vision

## Execution rule

Complete and verify one phase before starting the next.

Atomic tasks, assigned skills, subagent roles and verification gates are defined in `TASK_SKILL_MATRIX.md`.

Subagent dispatch and review must follow `SUBAGENT_ORCHESTRATION.md`.

After every accepted task, the coordinator must update `PROGRESS.md` before moving on.

## Phase 0 — Repository and quality baseline

### Deliverables

- repository scaffold
- Python environment/package config
- React TypeScript app scaffold
- Docker Compose skeleton
- `.env.example`
- Ruff/pytest
- frontend lint/typecheck/test
- CI baseline
- structured logging foundation

### Acceptance

- clean install/start instructions,
- health placeholder services run,
- CI passes,
- no secrets.

## Phase 1 — RTSP stream manager

### Build

- camera config model,
- RTSP capture abstraction,
- latest-frame bounded queue,
- stall detection,
- reconnect state machine,
- health telemetry.

### Tests

- invalid URL,
- disconnect/reconnect,
- corrupt frame handling,
- queue boundedness.

### Exit

Camera stream runs independently of AI.

## Phase 2 — YOLO26s-Pose inference

### Build

- Ultralytics adapter,
- load `yolo26s-pose.pt`,
- GPU device selection,
- frame preprocessing/inference,
- keypoint result adapter,
- timing metrics.

### Rules

- use official Ultralytics APIs,
- no fine-tuning,
- no fall logic yet.

### Exit

Recorded/live frame produces normalized internal pose observations.

## Phase 3 — ByteTrack

### Build

- tracking configuration,
- stable internal track observation model,
- track lifecycle/expiry,
- per-track bounded history.

### Tests

- synthetic observation history,
- multi-person recorded clip,
- expired track cleanup.

## Phase 4 — Temporal fall engine

### Build

- feature extraction,
- state machine,
- confidence-aware scoring,
- cooldown/dedup,
- synthetic tests,
- development dataset runner.

### Evaluation

- tune only on development split,
- freeze configuration before final evaluation.

### Exit

Fall engine outputs candidate/confirmed/recovery with evidence.

## Phase 5 — Incident persistence + backend

### Build

- PostgreSQL schema,
- Alembic migrations,
- incident service,
- evidence snapshot storage,
- FastAPI REST,
- WebSocket events,
- review workflow.

### Tests

- API integration,
- migration,
- persistence,
- evidence access security.

## Phase 6 — Dashboard

### Build

- camera health page,
- incident list,
- incident detail,
- evidence display,
- human review,
- telemetry panel,
- WebSocket updates.

### Exit

Operator can inspect and review incidents end-to-end.

## Phase 7 — MQTT + system observability

### Build

- Mosquitto,
- event publisher,
- structured metrics,
- CPU/RAM/GPU telemetry,
- reconnect/error counters.

### Rule

Broker outage does not stop detector.

## Phase 8 — Reliability/UAT hardening

Execute:

- UAT plan,
- failure tests,
- soak test,
- privacy/security review.

Fix critical failures before optimization.

## Phase 9 — RTX 3070 optimization

Benchmark:

1. PyTorch
2. ONNX
3. TensorRT FP16
4. `yolo26n-pose` fallback if necessary

Output:

- raw benchmark results,
- comparison report,
- selected runtime.

Do not optimize before correctness/reliability baseline.

## Phase 10 — Agent/VLM incident enrichment

### Build

- asynchronous agent job,
- evidence selection,
- structured prompt/output,
- timeout/retry,
- provider/model/prompt version persistence,
- uncertain-case review queue.

### Rule

Agent cannot suppress the original incident.

## Phase 11 — Final evaluation

Run frozen:

- URFD final set,
- selected UP-Fall robustness set,
- local UAT,
- benchmark,
- failure suite.

Create:

- metrics report,
- confusion matrix,
- benchmark table,
- UAT report,
- limitations.

## Phase 12 — Portfolio release

Prepare:

- README,
- architecture diagram,
- demo instructions,
- screenshots/video,
- API docs,
- benchmark evidence,
- license attribution,
- resume bullets based only on measured results.

## Dependency graph

```text
0
↓
1
↓
2
↓
3
↓
4
↓
5
↓
6
↓
7
↓
8
↓
9
↓
10
↓
11
↓
12
```

Some frontend scaffolding may proceed earlier, but feature completion must respect backend contracts.

## Critical path

```text
RTSP
→ Pose
→ Tracking
→ Temporal Fall Engine
→ Incident Persistence
→ UAT
→ TensorRT Benchmark
→ Agent Enrichment
→ Final Evaluation
```
