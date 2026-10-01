# Acceptance Criteria — ElderCare Vision

## 1. Definition of Ready

A task is ready only when:

- requirement ID is identified,
- dependencies are known,
- inputs/outputs are defined,
- acceptance criteria exist,
- test approach is defined,
- no unresolved architecture decision blocks implementation.

## 2. Definition of Done

A task is done only when:

- implementation matches approved requirement,
- tests pass,
- lint/type checks required for the component pass,
- relevant failure path is tested,
- documentation/config example is updated,
- no secret or dataset binary was added,
- logs/errors are actionable,
- measured claims include reproducible evidence.

## 3. MVP acceptance

### Camera

- AC-001: Valid RTSP source transitions to `ONLINE`.
- AC-002: Invalid/unreachable source becomes `OFFLINE` without service crash.
- AC-003: Reachable source automatically reconnects after interruption.
- AC-004: Reconnect transition is recorded and emitted.

### Pose/tracking

- AC-010: Default model is `yolo26s-pose.pt`.
- AC-011: Person pose keypoints are available for detected persons.
- AC-012: ByteTrack IDs persist across ordinary continuous motion.
- AC-013: Track history is bounded and expired tracks are removed.

### Temporal fall engine

- AC-020: Walking alone does not create a fall incident in the designated UAT clip.
- AC-021: Sitting normally does not create a fall incident.
- AC-022: Bending/picking-up-object scenario does not create a fall incident.
- AC-023: Controlled fall scenario creates a candidate and confirmed incident.
- AC-024: Incident contains temporal evidence features rather than only a frame label.
- AC-025: Duplicate alerts are suppressed while the same person remains in the same confirmed fall state.
- AC-026: Missing keypoints degrade confidence safely.

### Persistence/API

- AC-030: Confirmed incident is persisted before optional Agent/VLM processing.
- AC-031: Incident API returns detector version and configuration version.
- AC-032: Human review can be saved without mutating original detector output.
- AC-033: OpenAPI documentation is available.
- AC-034: API never returns unredacted RTSP credentials.

### Dashboard

- AC-040: Camera state is visible.
- AC-041: Incident list is visible.
- AC-042: Incident detail includes evidence and detector output.
- AC-043: Human review can be submitted.
- AC-044: VLM text is visually labeled as generated context.

### Reliability

- AC-050: VLM unavailable → core detection continues.
- AC-051: MQTT unavailable → core detection continues.
- AC-052: Dashboard unavailable → core detection continues.
- AC-053: Backend restart recovers without corrupting incident persistence.
- AC-054: Critical exceptions produce structured logs.

## 4. Performance acceptance

Targets on the actual target PC:

| Metric | Gate |
|---|---:|
| Complete vision pipeline | >= 15 processed FPS |
| Stretch complete pipeline | >= 25 processed FPS |
| Vision-loop p95 | <= 100 ms |
| Camera reconnect after source recovery | <= 10 s |
| Critical UAT pass rate | 100% |
| Soak-test unhandled crashes | 0 |

If the default `yolo26s-pose.pt` fails the performance gate after reasonable optimization, benchmark `yolo26n-pose.pt` and record the trade-off.

## 5. AI evaluation acceptance

Final test metrics must be reported:

- TP, FP, TN, FN
- Precision
- Recall
- F1
- confusion matrix
- false alerts/hour
- time-to-alert
- results by scenario where sample count permits

Portfolio targets:

- Recall >= 0.90
- Precision >= 0.85
- false alerts < 1/hour on controlled long-form non-fall validation

Failure to hit a target is not permission to alter the final-test split.

## 6. Shipping acceptance

Before declaring the portfolio release complete:

- Docker Compose startup documented,
- environment example documented,
- UAT report committed,
- benchmark report committed,
- architecture diagram current,
- API docs reproducible,
- license/attribution documentation present,
- known limitations documented,
- no unsupported safety/medical claims.
