# ElderCare Vision — Codex Planning Pack

This folder is the source-of-truth planning package for **ElderCare Vision — Edge AI Fall Detection & Intelligent Video Analytics Platform**.

## Fixed technical decisions

| Area | Decision |
|---|---|
| Primary GPU | NVIDIA RTX 3070 |
| Primary pose model | `yolo26s-pose.pt` |
| Fallback pose model | `yolo26n-pose.pt` |
| Benchmark-only larger model | `yolo26m-pose.pt` |
| Pose pretraining | COCO-Pose / 17-keypoint human pose |
| Tracker | ByteTrack |
| Fall logic | Temporal multi-signal state machine over pose + tracking |
| Primary fall dataset | UR Fall Detection Dataset (RGB sequences) |
| Secondary robustness dataset | UP-Fall RGB subset |
| Deployment-domain validation | Controlled self-recorded IP-camera/phone videos |
| GPU optimization path | PyTorch → ONNX → TensorRT FP16 |
| CPU fallback | OpenVINO, optional |
| Backend | FastAPI + PostgreSQL |
| Real-time UI updates | WebSocket |
| Event transport | MQTT / Mosquitto |
| Frontend | React + TypeScript |
| Deployment | Docker Compose on Linux/WSL2 |
| Agent/VLM | Asynchronous incident enrichment only; never required for core fall detection |

## Important design rule

The project does **not** train YOLO to classify a fall in a single frame.

The core principle is:

```text
YOLO26s-Pose + Person Tracking + Temporal Motion/Orientation Logic
```

A fall is a time-dependent event. Single-frame labels such as "person lying down" are not sufficient.

## Dataset rule

- The official YOLO26s-Pose checkpoint is already pretrained for human pose using COCO-Pose-style 17 keypoints.
- UR Fall Detection and UP-Fall are used primarily to evaluate and tune the **temporal fall engine**, not to retrain the pose network in the MVP.
- Raw public datasets must not be committed to Git.
- Dataset licenses and redistribution restrictions must be respected.
- Never split frames from the same source sequence across training/tuning and final test sets.

## Document map

1. `PROJECT_BRIEF.md`
2. `PRD.md`
3. `CONSTRAINTS.md`
4. `ACCEPTANCE_CRITERIA.md`
5. `RISK_REGISTER.md`
6. `ARCHITECTURE.md`
7. `DATA_FLOW.md`
8. `API_SPEC.md`
9. `DATABASE_SCHEMA.md`
10. `EVENT_SCHEMA.md`
11. `AI_SPEC.md`
12. `DATASET_PLAN.md`
13. `MODEL_EVALUATION.md`
14. `BENCHMARK_PLAN.md`
15. `TEST_STRATEGY.md`
16. `UAT_PLAN.md`
17. `FAILURE_TESTS.md`
18. `IMPLEMENTATION_PLAN.md`
19. `AGENTS.md`
20. `REPOSITORY_STRUCTURE.md`
21. `SOURCES.md`
22. `docs/adr/ADR-001-yolo26s-pose.md`
23. `docs/adr/ADR-002-tensorrt-primary.md`
24. `docs/adr/ADR-003-agent-decoupling.md`
25. `docs/adr/ADR-004-dataset-strategy.md`

## Codex handoff sequence

Before implementation:

```text
Read AGENTS.md
    ↓
Read PRD.md + CONSTRAINTS.md
    ↓
Read ARCHITECTURE.md + AI_SPEC.md + DATASET_PLAN.md
    ↓
Read TEST_STRATEGY.md + ACCEPTANCE_CRITERIA.md
    ↓
Execute IMPLEMENTATION_PLAN.md one phase at a time
```

Do not implement later phases early.

## Recommended Codex skills

Primary engineering workflow:

```bash
codex plugin marketplace add addyosmani/agent-skills
codex plugin add agent-skills@agent-skills
```

Ultralytics-specific source-grounded YOLO workflow:

```bash
codex plugin marketplace add ultralytics/skills
codex plugin add yolo@ultralytics
```

Restart Codex after installing plugins.

## Status

Planning baseline: **Ready for implementation**

Measured performance results: **Not yet available**

No benchmark number in these documents is a claimed result. Targets are acceptance goals until validated on the actual RTX 3070 system.

## Muse Subagent Execution Files

- `TASK_SKILL_MATRIX.md`
- `SUBAGENT_ORCHESTRATION.md`
- `SKILL_SOURCES.md`

Primary coordinator: **Muse + Spark 1.3 xhigh**.

Use Superpowers as the global orchestration framework and the task matrix for specialist skill selection.
