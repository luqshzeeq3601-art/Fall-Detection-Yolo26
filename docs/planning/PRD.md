# Product Requirements Document — ElderCare Vision

## 1. Purpose

Define the requirements for an Edge-AI fall-detection and intelligent video-analytics proof of concept intended to demonstrate AI Vision Engineering skills.

## 2. Product outcome

The system must transform a live fixed-camera video stream into:

```text
Person pose
→ persistent person identity
→ temporal fall evidence
→ incident record
→ operator notification/dashboard update
→ optional asynchronous incident enrichment
```

## 3. Users

### Primary user

Facility operator / caregiver monitoring a camera feed and incident queue.

### Secondary user

AI/operations engineer responsible for:

- camera health,
- system performance,
- model configuration,
- incident review,
- benchmark execution,
- troubleshooting.

## 4. User stories

### US-01 Live monitoring

As an operator, I want to see camera health and the latest processed frame status so that I know the system is operating.

### US-02 Fall incident

As an operator, I want a suspected fall to create an incident with timestamp, camera, person track and evidence so that I can review it.

### US-03 Reduced false alerts

As an operator, I want walking, sitting, bending, kneeling and normal lying transitions to be distinguished from rapid fall events as much as practical.

### US-04 Failure visibility

As an operator, I want camera/network/backend failures to be visible instead of silently stopping monitoring.

### US-05 Engineering observability

As an engineer, I want FPS, inference latency, processing latency and hardware usage recorded so that performance can be measured.

### US-06 Human review

As an engineer/operator, I want incidents to be labeled confirmed-fall / non-fall / uncertain so that system quality can be measured.

### US-07 Agent enrichment

As an operator, I want suspicious incident evidence optionally summarized by a VLM so that I receive additional context without blocking the core detector.

## 5. Functional requirements

### Camera/stream

- FR-001: Accept an RTSP camera URL through secure configuration.
- FR-002: Decode frames continuously when camera is online.
- FR-003: Detect stream stalls and transition camera health to degraded/offline.
- FR-004: Automatically retry with bounded exponential backoff.
- FR-005: Emit camera online/offline/reconnected events.

### Vision

- FR-010: Use `yolo26s-pose.pt` as the default pose model.
- FR-011: Run person pose inference at configurable `imgsz`, default 640.
- FR-012: Extract 17-keypoint human poses and confidence scores.
- FR-013: Associate people over time using ByteTrack.
- FR-014: Maintain bounded per-track temporal history.
- FR-015: Generate temporal motion/posture features for each active track.
- FR-016: Evaluate a fall state machine and output state + score + evidence features.
- FR-017: Clear expired track history to prevent unbounded memory growth.

### Incident handling

- FR-020: Create an incident only after the temporal confirmation rule is satisfied.
- FR-021: Store event timestamp, camera, track ID, detector version, configuration version and evidence features.
- FR-022: Store at least one evidence snapshot.
- FR-023: Prevent duplicate incidents for the same continuous fall state using a cooldown/state transition.
- FR-024: Allow human review status to be recorded.
- FR-025: Preserve the original detection result after human review.

### Backend/API

- FR-030: Expose readiness and liveness endpoints.
- FR-031: Expose camera health.
- FR-032: Expose paginated incident search.
- FR-033: Expose a single incident with evidence and review.
- FR-034: Accept human-review updates.
- FR-035: Stream operational/incident updates via WebSocket.
- FR-036: Provide API documentation through FastAPI/OpenAPI.

### MQTT/events

- FR-040: Publish fall-confirmed events.
- FR-041: Publish camera health transitions.
- FR-042: Publish agent enrichment completion/failure.
- FR-043: MQTT failure must not stop the core detector.

### Dashboard

- FR-050: Show camera status.
- FR-051: Show recent incidents.
- FR-052: Show incident detail and evidence.
- FR-053: Allow human review labels.
- FR-054: Show basic performance telemetry.
- FR-055: Clearly distinguish detector output from VLM-generated context.

### Agent/VLM

- FR-060: Run asynchronously after an incident/candidate is persisted.
- FR-061: Never block or suppress a confirmed core incident.
- FR-062: Store model/provider/version/prompt version for reproducibility.
- FR-063: Store enrichment output separately from detector evidence.
- FR-064: Handle provider unavailability without affecting core monitoring.
- FR-065: Support collection of uncertain incidents into a review queue.

## 6. Non-functional requirements

### Performance

- NFR-001: Single-camera pipeline is the required baseline.
- NFR-002: Baseline acceptance: at least 15 processed FPS for the complete vision pipeline on the target RTX 3070.
- NFR-003: Stretch target: 25 processed FPS.
- NFR-004: Vision processing p95 target: <= 100 ms from decoded frame availability to fall-engine output, excluding camera/network transport.
- NFR-005: UI/API operations must remain responsive while inference runs.

Targets are goals, not claimed measurements.

### Reliability

- NFR-010: Vision processing and Agent/VLM execution must be separate failure domains.
- NFR-011: Camera reconnect must be automatic.
- NFR-012: Unhandled errors must not be silently swallowed.
- NFR-013: Services must emit structured logs.

### Security/privacy

- NFR-020: No credentials in Git.
- NFR-021: RTSP URLs containing credentials must be redacted in logs/API output.
- NFR-022: Store only incident evidence required for the POC.
- NFR-023: Evidence retention must be configurable.
- NFR-024: No continuous cloud video upload in the default architecture.
- NFR-025: Agent/VLM image sending must be explicitly configurable and disabled when no approved provider is configured.

### Maintainability

- NFR-030: Business logic must be separated from framework/IO code.
- NFR-031: Fall-engine thresholds/configuration must live outside source code.
- NFR-032: Database changes require migrations.
- NFR-033: Public API schemas are versioned under `/api/v1`.

## 7. Success metrics

### AI quality

- Recall
- Precision
- F1
- false alerts/hour
- false negatives by scenario
- time-to-alert

### System performance

- processed FPS
- pose inference p50/p95
- full vision loop p50/p95
- API p50/p95
- reconnect duration
- CPU/RAM/GPU utilization
- GPU VRAM
- incident processing throughput

### Reliability

- extended runtime without unhandled crash
- recovery after camera disconnect
- recovery after backend restart
- core detector remains operational if VLM/MQTT is unavailable

## 8. Portfolio quality targets

These are project targets, not medical guarantees:

| Metric | Initial target |
|---|---:|
| Fall Recall | >= 0.90 on designated final test set |
| Fall Precision | >= 0.85 on designated final test set |
| F1 | Report, no hidden threshold |
| False alerts | < 1 per hour on controlled long-form non-fall validation |
| Complete vision FPS | >= 15 FPS baseline; >= 25 FPS stretch |
| Camera reconnect | <= 10 s after source becomes reachable |
| Critical UAT | 100% pass |
| Unhandled crash during soak test | 0 |

If targets are not met, report actual results honestly rather than changing the test set.

## 9. Non-goals

The MVP does not attempt to:

- diagnose injury,
- determine medical severity,
- call emergency services autonomously,
- identify people by face,
- perform gait diagnosis,
- estimate clinical fall risk,
- guarantee detection of every real-world fall,
- train a new pose estimator from scratch,
- support many cameras before one-camera reliability is proven.

## 10. Release gate

The project may be called "MVP complete" only when all critical acceptance criteria in `ACCEPTANCE_CRITERIA.md` pass.
