# Project Methodology — ElderCare Vision

## 1. Methodology

ElderCare Vision uses a **hybrid Project Management + AI/ML Engineering + Software Engineering lifecycle**.

The methodology combines:

- requirements-first planning,
- specification-driven development,
- incremental implementation,
- test-driven development for deterministic logic,
- source-driven development for version-sensitive libraries,
- measurable AI/ML evaluation,
- risk-based validation,
- benchmark-before-claim discipline,
- continuous progress tracking.

Primary execution principle:

```text
Define → Plan → Build → Verify → Review → Measure → Document → Progress Update
```

No task is considered complete until verification evidence exists and `PROGRESS.md` has been updated.

---

## 2. Project-Level Flowchart

```mermaid
flowchart TD
    A[Project Idea / Job-Market Goal] --> B[Project Brief]
    B --> C[PRD + Problem Statements + Objectives]
    C --> D[Constraints + Acceptance Criteria + Risk Register]
    D --> E[System Architecture + Data Flow + API + Database + Event Schemas]
    E --> F[AI Specification + Dataset Plan + Evaluation Plan]
    F --> G[Implementation Plan + Repository Structure + AGENTS.md]
    G --> H{Phase Ready?}

    H -- No --> C
    H -- Yes --> I[Phase 0: Repository & Quality Baseline]
    I --> J[Phase 1: RTSP Stream Manager]
    J --> K[Phase 2: YOLO26s-Pose]
    K --> L[Phase 3: ByteTrack]
    L --> M[Phase 4: Temporal Fall Engine]
    M --> N[Phase 5: Incident Persistence + FastAPI]
    N --> O[Phase 6: React Dashboard]
    O --> P[Phase 7: MQTT + Observability]
    P --> Q[Phase 8: Reliability + UAT]
    Q --> R[Phase 9: RTX 3070 Optimization]
    R --> S[Phase 10: Agent/VLM Enrichment]
    S --> T[Phase 11: Final Evaluation]
    T --> U[Phase 12: Portfolio Release]

    U --> V[Measured Resume / Portfolio Evidence]

    I -. every verified task .-> W[Update PROGRESS.md]
    J -. every verified task .-> W
    K -. every verified task .-> W
    L -. every verified task .-> W
    M -. every verified task .-> W
    N -. every verified task .-> W
    O -. every verified task .-> W
    P -. every verified task .-> W
    Q -. every verified task .-> W
    R -. every verified task .-> W
    S -. every verified task .-> W
    T -. every verified task .-> W
    U -. every verified task .-> W
```

---

## 3. Per-Task Engineering Loop

Every implementation task follows this loop:

```mermaid
flowchart LR
    A[Read Requirement + Current Progress] --> B[Confirm Task Scope]
    B --> C[Check Official Sources / Existing Code]
    C --> D[Write or Update Test]
    D --> E[Implement Smallest Working Change]
    E --> F[Run Tests + Lint + Validation]

    F -->|Fail| G[Debug Root Cause]
    G --> E

    F -->|Pass| H[Review Against Acceptance Criteria]
    H -->|Gap Found| E
    H -->|Pass| I[Record Evidence]

    I --> J[Update PROGRESS.md]
    J --> K[Update Docs / ADR if Needed]
    K --> L[Atomic Git Commit]
    L --> M[Move to Next Task]
```

### Mandatory task completion order

```text
Implement
→ Test
→ Verify acceptance criteria
→ Record evidence
→ Update PROGRESS.md
→ Commit
```

A task must **not** be marked complete because code was merely written.

---

## 4. AI / Computer Vision Methodology

```mermaid
flowchart TD
    A[Pretrained YOLO26s-Pose] --> B[Establish Pose Baseline]
    B --> C[ByteTrack Person Tracking]
    C --> D[Extract Temporal Pose Features]
    D --> E[Rule-Based Fall State Machine]
    E --> F[Development Dataset Evaluation]
    F --> G[Threshold / Rule Calibration]
    G --> H[Freeze Model + Config + Split]
    H --> I[Final Held-Out Evaluation]
    I --> J[Error Analysis]

    J --> K{Pose Model Is Bottleneck?}
    K -- No --> L[Keep Pretrained Pose Model]
    K -- Yes --> M[Evaluate Need for Pose Fine-Tuning]

    L --> N[RTX 3070 Runtime Benchmark]
    M --> N

    N --> O[PyTorch Baseline]
    O --> P[ONNX Validation]
    P --> Q[TensorRT FP16]
    Q --> R[Select Runtime From Evidence]

    R --> S[Agent/VLM Incident Enrichment]
    S --> T[Final UAT + Portfolio Evidence]
```

### AI methodology rules

- Do not classify falls from one frame.
- Do not tune using final-test data.
- Do not fine-tune YOLO26s-Pose before proving pose quality is the bottleneck.
- Keep dataset splits sequence/subject-disjoint.
- Report failed targets honestly.
- Preserve model, configuration, dataset split and Git commit for every final evaluation.

---

## 5. Dataset Methodology

```text
Official YOLO26s-Pose
        │
        └── COCO-Pose pretrained human keypoints

UR Fall Detection
        │
        ├── development/tuning sequences
        └── frozen final-test sequences

UP-Fall RGB subset
        │
        └── secondary cross-dataset robustness

Local controlled IP-camera clips
        │
        └── deployment-domain UAT
```

### Dataset process

1. Download externally.
2. Verify license/source.
3. Create manifest.
4. Assign complete sequences/subjects to splits.
5. Never commit raw large datasets.
6. Cache derived keypoints only with model/config metadata.
7. Freeze final-test manifest before final evaluation.

---

## 6. Validation Methodology

| Layer | Validation |
|---|---|
| Code | Unit tests, lint, type checks |
| Component | Stream, tracking, fall engine, persistence |
| Integration | FastAPI, PostgreSQL, WebSocket, MQTT |
| AI | Precision, Recall, F1, false alerts/hour |
| Runtime | FPS, p50/p95 latency, CPU/GPU/RAM/VRAM |
| Reliability | Disconnect/reconnect, provider failure, queue overload |
| UAT | End-to-end operational scenarios |
| Security | Secret handling, validation, evidence-path protection |
| Portfolio | Claims backed by reproducible results |

---

## 7. Phase Gates

| Phase | Gate |
|---|---|
| 0 | Repository, CI and quality tooling operational |
| 1 | Stable RTSP ingest + reconnect |
| 2 | YOLO26s-Pose produces normalized observations |
| 3 | ByteTrack + bounded track history verified |
| 4 | Temporal fall engine passes synthetic and development tests |
| 5 | Incidents persist and API contracts pass |
| 6 | Operator can inspect/review incidents |
| 7 | Telemetry + MQTT work without coupling failures |
| 8 | Critical UAT and failure tests pass |
| 9 | RTX 3070 benchmark completed and runtime selected |
| 10 | Agent/VLM works asynchronously without affecting core detector |
| 11 | Frozen final evaluation completed |
| 12 | Documentation, demo and evidence ready |

---

## 8. Gantt Chart

Planned baseline schedule starting **21 September 2026**.

This is a planning baseline. Actual completion is recorded in `PROGRESS.md`.

```mermaid
gantt
    title ElderCare Vision — Baseline Execution Plan
    dateFormat  YYYY-MM-DD
    axisFormat  %d %b

    section Planning / Foundation
    Planning pack & methodology         :done, p0, 2026-09-19, 2d
    Phase 0 Repository & quality        :p1, 2026-09-21, 4d

    section Core Vision
    Phase 1 RTSP stream manager         :p2, after p1, 5d
    Phase 2 YOLO26s-Pose                :p3, after p2, 5d
    Phase 3 ByteTrack                    :p4, after p3, 4d
    Phase 4 Temporal fall engine         :p5, after p4, 8d

    section Platform
    Phase 5 FastAPI + PostgreSQL         :p6, after p5, 6d
    Phase 6 React dashboard              :p7, after p6, 6d
    Phase 7 MQTT + observability         :p8, after p7, 4d

    section Validation / Optimization
    Phase 8 Reliability + UAT            :p9, after p8, 5d
    Phase 9 RTX 3070 optimization        :p10, after p9, 5d
    Phase 10 Agent/VLM enrichment        :p11, after p10, 5d

    section Finalization
    Phase 11 Final evaluation            :p12, after p11, 5d
    Phase 12 Portfolio release           :p13, after p12, 4d
```

---

## 9. Milestones

| Milestone | Definition |
|---|---|
| M1 — Foundation Ready | Repo, CI, Docker and quality tooling operational |
| M2 — Vision Baseline | RTSP + YOLO26s-Pose + ByteTrack working |
| M3 — Fall Detection | Temporal fall engine validated |
| M4 — Full Application | Backend + dashboard + persistence working |
| M5 — Reliable Edge System | Monitoring, recovery and UAT complete |
| M6 — Optimized RTX 3070 | TensorRT benchmark and runtime decision complete |
| M7 — Intelligent Workflow | Agent/VLM enrichment working asynchronously |
| M8 — Portfolio Release | Final metrics, documentation and demo ready |

---

## 10. Progress Tracking Method

`PROGRESS.md` is the live state of the project.

It must contain:

- current phase,
- current task,
- overall status,
- completed tasks,
- active tasks,
- blocked tasks,
- evidence/tests,
- important decisions,
- next task,
- progress log.

### Required update trigger

Update `PROGRESS.md` immediately after:

- completing a task,
- failing a task and discovering a blocker,
- changing an architecture decision,
- changing model/runtime/dataset configuration,
- completing a benchmark,
- completing UAT/evaluation.

### Source of truth hierarchy

```text
PRD / Constraints / Architecture
        ↓
Implementation Plan
        ↓
PROGRESS.md
        ↓
Code + Test Evidence
```

`PROGRESS.md` reports actual state. It does not replace requirements.
