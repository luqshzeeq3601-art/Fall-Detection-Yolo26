# ElderCare Vision — Project Brief

## 1. Project title

**ElderCare Vision — Edge AI Fall Detection & Intelligent Video Analytics Platform**

## 2. Target role

**AI Vision Engineer — Computer Vision & Video Analytics**

Primary domain:

- Intelligent surveillance
- CCTV/IP-camera analytics
- Edge AI
- Computer Vision
- IoT/enterprise integration
- AI workflow automation

## 3. Project summary

Build a production-oriented local Edge-AI proof of concept that:

1. receives a live phone/IP-camera stream over RTSP,
2. estimates human pose with YOLO26s-Pose,
3. tracks each person with ByteTrack,
4. detects probable falls using temporal motion and posture evidence,
5. records structured incident evidence,
6. exposes incidents and device health through FastAPI/PostgreSQL,
7. updates a React monitoring dashboard in real time,
8. publishes operational events through MQTT,
9. asynchronously enriches suspicious incidents with an Agent/VLM workflow,
10. collects uncertain cases for human review and later model/system improvement.

## 4. Problem statements

### P1 — Manual monitoring and delayed fall detection

Continuous CCTV monitoring requires sustained human attention. Falls may be missed or noticed late.

### P2 — Raw AI output lacks operational context

A raw pose or detection result does not explain what happened, what evidence triggered the incident, or what an operator should review.

### P3 — Vision systems degrade when deployment conditions change

Camera disconnects, unstable networks, occlusion, lighting changes, resource saturation and false alerts can reduce reliability.

## 5. Objectives

| ID | Objective | Addresses |
|---|---|---|
| O1 | Develop real-time fall detection using human pose, person tracking and temporal video analysis. | P1 |
| O2 | Build an asynchronous incident workflow that enriches suspicious events, supports human review and collects uncertain cases. | P2 |
| O3 | Deploy, monitor, test and optimize the complete Edge-AI system for reliability, latency, accuracy and resource efficiency. | P3 |

## 6. Traceability

| Problem | Objective | Core feature | Evidence |
|---|---|---|---|
| P1 | O1 | YOLO26s-Pose + ByteTrack + temporal fall engine | Precision, Recall, F1, false alerts/hour, time-to-alert |
| P2 | O2 | Incident evidence + Agent/VLM + human review | Review records, agent latency, uncertain-case collection |
| P3 | O3 | RTSP recovery + telemetry + Docker + TensorRT + UAT | FPS, p50/p95 latency, reconnect time, uptime, resource metrics |

## 7. Primary model decision

### Selected model

**`yolo26s-pose.pt`**

Reason:

- stronger pose accuracy than the nano variant,
- still compact enough for a single-stream real-time portfolio system,
- appropriate engineering balance for an RTX 3070,
- leaves sufficient room for tracking, API, dashboard and monitoring processes,
- can be exported to TensorRT for NVIDIA-optimized inference.

### Model policy

| Model | Role |
|---|---|
| `yolo26s-pose.pt` | Default production POC model |
| `yolo26n-pose.pt` | Fallback if full-pipeline latency/FPS targets are missed |
| `yolo26m-pose.pt` | Benchmark comparison only; adopt only if accuracy gain justifies cost |

No model may replace the default without benchmark evidence and an ADR update.

## 8. Dataset decision

### Primary dataset

**UR Fall Detection Dataset**

Use:

- RGB fall sequences
- RGB activities-of-daily-living sequences
- sequence-level evaluation of the temporal fall engine

Important:

- 70 sequences: 30 fall + 40 ADL
- official source provides RGB, depth and accelerometer streams
- license is CC BY-NC-SA 4.0 for non-commercial academic use
- do not redistribute dataset files through the repository

### Secondary dataset

**UP-Fall Detection Dataset — RGB subset only**

Use for:

- additional fall types,
- activities such as walking, standing, picking up objects, sitting, jumping and laying,
- subject-disjoint robustness tests.

The full multimodal dataset is very large; the project should not require downloading all 812 GB.

### Deployment-domain dataset

Record a small controlled validation set using the same phone/IP camera and camera placement intended for the demo.

Do not ask elderly or vulnerable people to simulate falls. Use public data or safe, controlled simulations by consenting healthy adults with appropriate precautions.

## 9. Core technical stack

| Layer | Technology |
|---|---|
| Programming | Python |
| Vision | Ultralytics YOLO26s-Pose |
| Pose keypoints | COCO-style 17 human keypoints |
| Video processing | OpenCV |
| ML framework | PyTorch |
| Tracking | ByteTrack |
| GPU deployment | TensorRT FP16 |
| Portable export | ONNX |
| Optional CPU deployment | OpenVINO |
| Backend | FastAPI |
| Validation/models | Pydantic |
| Persistence | PostgreSQL |
| DB migrations | Alembic |
| Real-time updates | WebSocket |
| IoT/events | MQTT / Mosquitto |
| Frontend | React + TypeScript |
| Deployment | Docker / Docker Compose |
| Host | Linux / WSL2 |
| Version control | Git / GitHub |
| Agent workflow | Ultralytics Agents / equivalent code-generated workflow |
| Context enrichment | Vision-Language Model |

## 10. MVP

Critical:

- RTSP/IP camera ingestion
- reconnect/retry state machine
- YOLO26s-Pose inference
- ByteTrack IDs
- temporal fall engine
- incident snapshot + metadata
- FastAPI
- PostgreSQL
- React monitoring dashboard
- WebSocket updates
- camera health
- performance telemetry
- Docker deployment
- structured UAT

Post-MVP:

- short pre/post incident clips
- Agent/VLM enrichment
- uncertain-case collection
- TensorRT optimization
- multi-camera support
- authentication/RBAC
- external notification integrations

## 11. Safety boundary

This portfolio project is **not a certified medical device, emergency-response service or guaranteed safety system**.

The VLM/Agent layer must never be the sole mechanism responsible for detecting or suppressing a fall alert.

## 12. Expected evidence

- architecture diagram
- live RTSP demo
- pose/tracking overlay
- temporal event timeline
- confusion matrix
- Precision/Recall/F1
- false alerts/hour
- p50/p95 latency
- PyTorch/ONNX/TensorRT benchmark
- camera disconnect/recovery demo
- resource telemetry
- UAT report
- agent enrichment examples
- GitHub Actions
- Docker deployment
- API docs
