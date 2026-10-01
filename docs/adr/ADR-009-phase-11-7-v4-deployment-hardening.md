# ADR-009: Phase 11.7 V4 Fall Engine — Real-World Deployment Hardening & Model Upgrade

## Status
ACCEPTED (2026-09-25)

## Date
2026-09-25

## Context
Following the evidence quarantine and methodology audit (ADR-008 & P11.7-001), prior evaluation results derived from synthetic shortcuts were quarantined. Real-world deployment benchmarks on genuine decoded optical video revealed true baseline operational performance (Recall = 33.33%–50.00%).

To achieve production-grade reliability (>90% Recall, >85% Precision, 0.0 false alerts on dev ADLs, and real-time inference latency), a comprehensive Phase 11.7 architecture upgrade was undertaken.

---

## Decision

### 1. Genuine Optical Ingestion & Subject-Disjoint Governance
- **Dataset:** 70 real-world optical MP4 video sequences (11,936 frames, 397.86s total duration, 10 human subjects `subj-01` through `subj-10`).
- **Governance:** `DatasetSplitGuard` enforces strict physical isolation. The development split (42 videos, `subj-01`..`subj-06`) is used for training, augmentation, and calibration. The held-out test split (28 videos, `subj-07`..`subj-10`) remains quarantined until final one-shot evaluation.

### 2. Verified Ingestion & Wiring Pipeline (W1–W6)
- Standardized 17-keypoint normalized contracts across YOLO26s-Pose, ByteTrack, and feature extraction.
- Rectified aspect ratio orientation, anatomical torso vectors, and bounding box coordinate bridges.

### 3. Recurrent Temporal Classifier (`GRUClassifierV4`)
- **Architecture:** 24-dimensional input, 64-unit Gated Recurrent Unit (GRU) with LayerNorm, Dropout, and calibrated sigmoid output head.
- **Training Strategy:** Subject-disjoint 5-fold cross-validation with multi-modal track augmentation (speed scaling $\pm 25\%$, camera tilt $\pm 10^\circ$, keypoint occlusion dropouts, and tracking gap injection).
- **Frozen Performance on Dev Split:** Recall = 99.73%, Precision = 93.68%, F2 = 0.9845.

### 4. Calibrated Operating Triplet
- $\tau_{\text{veto}} = 0.55$: Vetoes spurious candidate falls on non-fall ADLs (100.0% specificity on dev ADLs).
- $\tau_{\text{trigger}} = 0.68$: Enters `DESCENT_CANDIDATE` on kinetic downward collapse.
- $\tau_{\text{confirm}} = 0.69$: Confirms low posture in `FALL_CONFIRMED`.
- Strict ordering verified: $\tau_{\text{veto}} \le \tau_{\text{trigger}} \le \tau_{\text{confirm}}$.

### 5. Multi-Scale Temporal Context Horizons
- Simultaneous feature extraction across:
  - **Short Window (0.5s / 15 frames):** Captures sharp kinetic slips and high-velocity collapse spikes.
  - **Medium Window (1.0s / 30 frames):** Baseline temporal tracking window.
  - **Long Window (2.0s / 60 frames):** Captures slow progressive slumps, faints, and cumulative stability loss.
- Precomputed keypoint geometry reused across all 3 slices to guarantee <2.0ms update latency.

### 6. Complex ADL False-Alert Suppression
- Heuristic and learned secondary suppression gates (`ADLFalseAlertSuppressor`):
  - **Controlled Bending:** Foot/ankle stability check (< 0.15h movement) with smooth acceleration.
  - **Controlled Sitting:** Elevated hip ratio check (hip remains >= 0.25h above ground) with upright torso.
  - **Intentional Reclining:** Controlled descent rate (< 0.55h/s peak velocity) + high post-transition stability.
  - **Classifier Veto:** Rejection when $P(\text{fall}) < \tau_{\text{veto}} = 0.55$.

### 7. Camera Perspective & Height Invariance Normalization
- `CameraPerspectiveNormalizer` provides:
  - Gravity-aligned vertical velocity rectification ($\frac{v_y}{\cos \theta_p}$).
  - 3D torso angle de-rotation.
  - Ground-plane distance scaling.
  - Self-supervised pitch auto-calibration from upright tracks.

---

## Consequences & Invariants
- All V4 model weights (`models/temporal_fall_classifier_v4.json`), configurations (`config/fall_detection_v4.yaml`), and feature datasets are cryptographically frozen via SHA-256 manifest before test split evaluation.
- Held-out test split evaluation (P11.7-016) is strictly one-shot with zero parameter tuning permitted.
