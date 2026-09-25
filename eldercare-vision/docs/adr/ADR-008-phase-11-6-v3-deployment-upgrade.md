# ADR-008: Phase 11.6 V3 Fall Engine — Deployment Performance Upgrade

## Status

ACCEPTED

## Date

2026-09-24

## Context

Phase 11.5 (V2) achieved a 100% relative improvement over V1 baseline but absolute
performance remains far below deployment requirements:

- URFD V2 F1 = 17.39%, Recall = 16.67%
- Combined URFD+UP-Fall F1 = 12.90%, Recall = 10.00%
- UP-Fall test: 0% detection (extreme camera angle + domain shift)

Root-cause analysis (P11-006) identified 7 error categories:
1. POSE: Keypoint jitter/collapse at ground level
2. TRACKING: ByteTrack ID switches during rapid descent
3. TEMPORAL: Fixed thresholds not generalizing across cameras
4. DATA: Annotation ambiguities in URFD
5. DOMAIN SHIFT: Ceiling vs lateral camera perspectives
6. SYSTEM: No issues (20/20 UAT PASS)
7. AGENT/VLM: Properly decoupled (no issues)

## Decision

### V3 Architecture Changes

1. **Feature Engineering**: Replace 12-dim V2 features with ~24-dim body-referenced,
   scale/translation-normalized features including angular velocity, acceleration,
   floor proximity, track quality, and keypoint availability metrics.

2. **Tracking Improvements**: Enhance ByteTrack with larger lost-track buffers,
   spatial/keypoint-aware track stitching, explicit track continuity measurement.

3. **Temporal Classifier**: Benchmark multiple architectures (logistic baseline,
   1D-CNN/TCN, GRU/LSTM, ST-GCN) using subject-disjoint cross-validation on
   development data. Select by pre-declared F2-maximization rule.

4. **Camera Normalization**: Optional floor-plane/homography normalization for
   fixed CCTV cameras to handle varying camera heights and tilt angles.

5. **Pose Backbone**: Study only. Compare yolo26s-pose vs larger models if
   available. Keep backbone frozen unless legally-compliant fine-tuning data exists.

### Methodology Constraints

- V1/V2 models, configs, and benchmarks preserved unchanged
- URFD/UP-Fall test sets treated as legacy benchmarks only
- Fresh deployment holdout created before model work begins
- Model selection exclusively from development evidence
- One-shot final evaluation after V3 freeze
- F2, Recall, and false-alert/hour as primary optimization criteria

## Consequences

- V3 will have larger feature vector requiring new temporal classifier
- Fresh holdout construction may require additional data acquisition
- Longer development cycle due to systematic classifier benchmarking
- Infrastructure changes (V3 metrics, experiment tracking)
- If deployment gates not met, honest NOT MET reporting
