# Engineering Constraints — ElderCare Vision

## 1. Scope constraints

- Single-camera reliability before multi-camera scaling.
- Fixed-camera scenario first.
- Core detection must work without Agent/VLM.
- Do not add features outside the approved implementation phase.
- No medical-device or emergency-response claims.

## 2. Hardware constraints

Target hardware:

- NVIDIA RTX 3070
- local PC
- phone/IP camera over local network
- Linux or WSL2 development/deployment environment

Model defaults:

```yaml
pose_model: yolo26s-pose.pt
imgsz: 640
tracker: bytetrack.yaml
device: 0
```

Fallback:

```yaml
pose_model: yolo26n-pose.pt
```

`yolo26m-pose.pt` is benchmark-only until evidence justifies adoption.

## 3. GPU deployment constraints

Primary deployment optimization:

```text
PyTorch baseline
→ ONNX portability validation
→ TensorRT FP16 NVIDIA deployment
```

OpenVINO is an optional CPU/Intel fallback and is not the primary RTX 3070 optimization target.

Do not use INT8 until:

- a representative calibration dataset exists,
- accuracy impact is measured,
- FP16 has already been benchmarked.

## 4. Dataset constraints

### UR Fall Detection

- Treat as non-commercial academic data.
- Preserve attribution.
- Do not redistribute raw dataset in Git.
- Split by complete sequence, never by extracted frame.

### UP-Fall

- Download only the required RGB subset when possible.
- Keep subjects separated across development/final evaluation.
- Do not require the entire multimodal archive.

### Local validation data

- Obtain consent.
- Avoid recording uninvolved people.
- Do not ask elderly/vulnerable persons to simulate falls.
- Keep raw recordings outside source control.

## 5. AI constraints

- YOLO Pose output is not a fall classification by itself.
- A person lying down in one frame is not automatically a fall.
- Fall confirmation requires temporal evidence.
- Missing/low-confidence keypoints must reduce confidence rather than generate fabricated coordinates.
- The temporal engine must retain explainable evidence features.
- Final thresholds must be calibrated on development data and frozen before final test evaluation.
- No final-test tuning.

## 6. Agent/VLM constraints

The Agent/VLM:

- is asynchronous,
- is optional for core operation,
- cannot erase or suppress a confirmed core incident,
- must identify its provider/model/version,
- must use bounded retries/timeouts,
- must not receive raw continuous video,
- receives only approved incident evidence,
- must clearly label generated narrative as model-generated context.

## 7. Architecture constraints

- Vision pipeline must not run inside FastAPI request handlers.
- Database writes must not block the frame capture loop.
- MQTT failure must not crash vision.
- VLM failure must not crash vision.
- Dashboard failure must not crash vision.
- Use bounded queues; no unbounded in-memory buffers.
- Apply backpressure/drop policy explicitly for live video.

## 8. Code quality constraints

Python:

- type hints for public interfaces,
- Pydantic for external schemas,
- Ruff for lint/format,
- pytest for testing,
- no bare `except`,
- no silent error suppression,
- no hidden global mutable state in core logic.

Frontend:

- TypeScript,
- typed API models,
- accessible semantic components,
- no dashboard state coupled directly to raw WebSocket implementation.

## 9. Security constraints

Prohibited:

- credentials in source,
- credentials in logs,
- raw RTSP URLs in API responses,
- hard-coded API keys,
- committing `.env`,
- disabling TLS verification to "make it work",
- shell execution from unvalidated API input.

Required:

- `.env.example` only,
- secrets through environment/configuration,
- redaction helper,
- dependency auditing,
- CORS allowlist,
- input validation,
- file path validation for evidence access.

## 10. Data retention constraints

Default POC behavior:

- continuous video is not persisted,
- confirmed incident snapshot is persisted,
- optional short incident clip is post-MVP,
- retention period is configurable,
- deleting an incident must follow an explicit policy, not ad-hoc filesystem deletion.

## 11. Observability constraints

Every service must produce:

- timestamp,
- level,
- service/component,
- event code,
- camera ID where relevant,
- incident ID where relevant,
- error type without secrets.

Required measured data:

- capture FPS,
- processed FPS,
- inference latency,
- vision loop latency,
- queue depth,
- dropped frames,
- CPU,
- RAM,
- GPU utilization,
- GPU VRAM,
- camera reconnect count.

## 12. Git constraints

- one logical change per commit,
- tests must accompany behavior changes,
- no dataset binaries,
- no model weights committed unless license/size policy explicitly permits,
- no generated benchmark claim without raw result artifact,
- architecture changes require ADR update.
