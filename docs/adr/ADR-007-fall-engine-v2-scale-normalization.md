# ADR-007 — Fall Engine V2 Scale-Normalization, Dynamic Reference Height, and Learned Probabilistic Classifier

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** VISION, EVAL, DOC, COORD

## Context

Phase 11 final evaluation revealed significant recall drop on non-standard camera angles (UP-Fall top/oblique views) and camera-distance sensitivity due to fixed pixel/bounding-box heuristic assumptions in the baseline V1 fall engine. In particular:
1. Fixed vertical velocity thresholds in pixels/second failed when subjects were far from the camera (small apparent height).
2. Pure aspect-ratio triggers caused false alerts during routine sitting, bending, or floor activities.
3. The pretrained YOLO26s-Pose keypoint detector weights must remain frozen because benchmark datasets lack COCO 17-keypoint ground-truth labels.

To resolve these root causes without modifying frozen backbone weights or compromising original evaluation baselines, Phase 11.5 introduced Fall Engine V2.

## Decision

Adopt the **Hybrid Scale-Normalized Fall Engine V2 with Learned Probabilistic Temporal Classifier (Candidate 3)** as the enhanced fall detection engine:

1. **Dynamic Upright Reference Height (`reference_height`)**:
   - Tracks person upright dimensions over preceding temporal windows to normalize downward velocity by subject apparent standing height.
2. **Multi-Tier Robust Torso Inclination**:
   - Computes torso angle from mid-shoulder to mid-hip vectors with fallback to individual shoulder-hip pairs or aspect ratio when keypoints are occluded.
3. **12-Dimensional Temporal Feature Vector**:
   - Captures normalized descent velocity, peak velocity, normalized displacement, relative aspect ratio drop, torso angle trajectory, duration on floor, stability, and hip height ratio.
4. **Calibrated Probabilistic Classifier**:
   - Logistic probability classifier trained strictly on development partitions (`models/temporal_fall_classifier_v2.json`) to confirm fall transitions.
5. **Frozen Backbone Invariance**:
   - `yolo26s-pose.pt` and `yolo26s-pose.engine` remain 100% frozen and unmodified.

## Component Checksums & Configuration

| File Path | SHA-256 Digest | Description |
|---|---|---|
| `config/fall_detection_v2.yaml` | Tracked in P11.5-004 manifest | Production V2 configuration parameters |
| `models/temporal_fall_classifier_v2.json` | Tracked in P11.5-004 manifest | Calibrated temporal classifier weights |
| `src/eldercare/fall_engine/features/geometry_v2.py` | Tracked in P11.5-004 manifest | Multi-tier torso angle & normalized bounding box logic |
| `src/eldercare/fall_engine/features/motion_v2.py` | Tracked in P11.5-004 manifest | Dynamic reference height & scale-normalized velocity |
| `src/eldercare/fall_engine/learned_classifier/classifier.py` | Tracked in P11.5-004 manifest | Probabilistic temporal classifier inference |
| `src/eldercare/fall_engine/state_machine_v2/machine_v2.py` | Tracked in P11.5-004 manifest | Fall state machine v2 implementation |

## Consequences

- **Scale Invariance:** Detection accuracy is robust across varying camera distances (near/far) and heights.
- **Enhanced Specificity:** Significant reduction in false alerts from everyday sitting/bending ADLs.
- **Strict Anti-Leakage:** Calibration performed exclusively on development splits, maintaining the scientific integrity of test benchmark comparisons.
- **High Throughput Preserved:** V2 feature extraction and lightweight linear classifier maintain >200 FPS on RTX 3070 TensorRT FP16.
