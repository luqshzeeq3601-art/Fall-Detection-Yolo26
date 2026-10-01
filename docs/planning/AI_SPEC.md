# AI / Computer Vision Specification — ElderCare Vision

## 1. Objective

Detect probable human falls from fixed-camera video using:

```text
YOLO26s-Pose
+ ByteTrack
+ temporal motion/posture features
+ state machine
```

## 2. Selected model

Default:

```text
yolo26s-pose.pt
```

Why:

- official YOLO26 pose checkpoint,
- 17-keypoint human pose representation,
- better pose accuracy than nano while remaining relatively compact,
- appropriate accuracy/performance balance for the target RTX 3070,
- exportable to ONNX/TensorRT.

Fallback:

```text
yolo26n-pose.pt
```

Benchmark-only alternative:

```text
yolo26m-pose.pt
```

## 3. Model training policy

### MVP

Do **not** fine-tune the pose model initially.

Use pretrained YOLO26s-Pose and establish:

- pose quality,
- pipeline latency,
- fall-engine performance,
- failure scenarios.

Fine-tuning is allowed only if evidence shows pose estimation itself is a limiting factor and a valid keypoint-labeled dataset is available.

UR Fall Detection and UP-Fall are fall/action datasets, not automatically valid YOLO pose-training datasets.

## 4. Pose representation

Use standard 17 human keypoints where available from the model:

- nose
- left/right eye
- left/right ear
- left/right shoulder
- left/right elbow
- left/right wrist
- left/right hip
- left/right knee
- left/right ankle

Never invent coordinates for missing points.

## 5. Tracking

Default tracker:

```text
ByteTrack
```

Reason:

- simple real-time baseline,
- low overhead,
- supported by Ultralytics tracking,
- appropriate for fixed-camera single/multi-person POC.

Track history is keyed by `(camera_id, track_id)`.

## 6. Temporal feature set

For every active track compute confidence-aware features.

### Geometry

- bbox height
- bbox width
- height/width ratio
- shoulder midpoint
- hip midpoint
- torso vector
- torso orientation angle
- body center

### Motion

Over timestamped history:

- vertical displacement of hip/torso center
- vertical velocity
- change in bbox height
- change in bbox aspect ratio
- torso-angle change
- duration of low/horizontal posture
- motion stability after descent

Normalize displacement by person/bbox size where practical to reduce dependence on camera distance.

## 7. Fall-state machine

Required states:

```text
NORMAL
DESCENT_CANDIDATE
DOWN_CONFIRMING
FALL_CONFIRMED
RECOVERY
```

### NORMAL → DESCENT_CANDIDATE

Require evidence of an unusually rapid downward transition and/or strong orientation change.

### DESCENT_CANDIDATE → DOWN_CONFIRMING

Require multiple signals across multiple frames. A single horizontal frame is insufficient.

### DOWN_CONFIRMING → FALL_CONFIRMED

Require persistence of post-fall/low posture for a configurable duration and sufficient overall evidence quality.

### FALL_CONFIRMED → RECOVERY

Triggered when posture/motion indicates recovery or track leaves.

### RECOVERY → NORMAL

After recovery/cooldown completion.

## 8. Confidence-aware logic

Fall score should combine evidence such as:

```text
motion evidence
+ posture/orientation evidence
+ persistence evidence
- missing-keypoint penalty
- unstable-track penalty
```

The exact calibrated weights/thresholds live in configuration and are not embedded as magic constants throughout code.

## 9. Bootstrap configuration

Initial engineering defaults may be used to make the pipeline executable, but they are not final acceptance thresholds.

Example configuration keys:

```yaml
pose:
  model: yolo26s-pose.pt
  imgsz: 640
  min_keypoint_confidence: 0.30

tracking:
  tracker: bytetrack.yaml
  history_seconds: 2.0

fall_engine:
  analysis_window_seconds: 1.5
  down_confirmation_seconds: 1.0
  incident_cooldown_seconds: 5.0
```

Motion/orientation thresholds must be calibrated using development sequences before final evaluation.

## 10. Evidence explainability

Every confirmed event stores:

- state transition timestamps,
- fall score,
- key contributing features,
- average/summary pose confidence,
- detector model,
- tracker,
- config version.

## 11. Dataset usage

### Pose model

Pretrained COCO-Pose-style checkpoint.

### Temporal fall engine development/evaluation

- UR Fall Detection Dataset
- selected UP-Fall RGB subset
- controlled local IP-camera validation clips

## 12. Agent/VLM role

VLM may answer contextual questions such as:

- "Describe the person's posture and nearby objects."
- "Does this evidence appear consistent with a rapid fall, normal sitting, or uncertainty?"

But:

- VLM output is generated context,
- VLM does not replace deterministic/temporal evidence,
- VLM does not suppress a confirmed core incident,
- VLM is not used on every frame.

## 13. Optimization

Benchmark in this order:

1. PyTorch FP32/standard inference
2. PyTorch FP16 if supported by runtime
3. ONNX validation
4. TensorRT FP16
5. optional `yolo26n-pose` TensorRT fallback
6. optional OpenVINO CPU fallback

## 14. Future learned temporal model

Only after the rule-based baseline is measured.

Possible input:

```text
T x (keypoint coordinates + confidence + bbox features)
```

Potential approaches:

- gradient-boosted features,
- temporal CNN,
- LSTM/GRU,
- transformer over keypoint sequences.

A learned temporal model must use subject/sequence-disjoint evaluation and must beat the baseline on predefined metrics before replacing it.
