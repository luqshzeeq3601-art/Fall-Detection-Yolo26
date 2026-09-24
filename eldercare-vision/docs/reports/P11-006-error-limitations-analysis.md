# P11-006 — Error & Limitations Analysis Report

## 1. Executive Summary

This report delivers a rigorous, evidence-based diagnostic analysis of the failure modes, empirical performance characteristics, and real-world operational limitations of the frozen **ElderCare Vision** fall detection system based on Phase 11 evaluations.

In accordance with ADR-005 and the evaluation integrity charter, **no detector parameters, model weights, or heuristic thresholds were modified based on this analysis**.

---

## 2. Root-Cause Error Categorization

Every False Positive (FP) and False Negative (FN) observed in Phase 11 was systematically categorized into 7 discrete architectural categories:

### A. POSE (Keypoint Estimation Failures)
- **Mechanism:** In severe horizontal postures (lying on floor) or extreme camera angles, standard COCO-trained YOLO26s-Pose models experience keypoint jitter, inverted limb assignments, or missing keypoint confidence (< 0.20 threshold).
- **Affected Samples:**
  - `urfd-fall-19-cam0`, `urfd-fall-22-cam0`: Torso keypoints (shoulders/hips) collapsed into low-confidence clusters upon floor impact, preventing reliable torso angle computation.
- **Evidence:** Frame-level keypoint logs show hip/shoulder confidence dropping below 0.35 during the critical landing window.

### B. TRACKING (ByteTrack ID Switches & Occlusion)
- **Mechanism:** Rapid descent dynamics cause significant bounding box displacement frame-over-frame. When tracker association fails, ByteTrack assigns a new track ID to the grounded person, resetting the temporal history buffer before candidate confirmation.
- **Affected Samples:**
  - `urfd-fall-21-cam0`, `urfd-fall-25-cam0`: Ground impact caused track ID switch from ID 1 to ID 2; the descent velocity was captured on ID 1, while resting horizontal posture was observed on ID 2. Neither track accumulated the complete 5-state transition.
- **Evidence:** `results_ledger` indicates presence of secondary track IDs created during mid-fall frames.

### C. TEMPORAL ENGINE (Threshold Sensitivity & Cooldown)
- **Mechanism:** The temporal state machine requires simultaneous satisfaction of normalized vertical descent velocity (`dz/dt > 0.40`), torso tilt angle (`> 60°`), and post-fall resting persistence (`duration >= 1.0s`).
- **Affected Samples:**
  - `urfd-adl-30-cam0` through `urfd-adl-39-cam0` (FPs): Fast sitting / rapid lying down on floor in ADL sequences triggered velocity candidates because uncalibrated camera height inflated pixel-space normalized velocity.
  - `upfall-s12-a01-t1`..`upfall-s17-a01-t1` (FNs): Controlled lateral falls in UP-Fall exhibited lower downward vertical velocity in Camera 1's perspective than the fixed threshold, causing the state machine to remain in `DESCENT_CANDIDATE` without confirming.

### D. DATA & ANNOTATION (Ground Truth Ambiguities)
- **Mechanism:** Differences in dataset annotation conventions. URFD labels the entire sequence as "fall", but certain sequences involve actors rolling or sliding rather than free-fall impacts.
- **Affected Samples:**
  - `urfd-fall-24-cam0`, `urfd-fall-28-cam0`: Fall action is gradual bed-roll / chair slip rather than abrupt vertical descent.

### E. DOMAIN SHIFT (Cross-Dataset Camera Perspective & Geometry)
- **Mechanism:**
  - URFD uses an overhead / ceiling-angled camera (Cam 0).
  - UP-Fall Camera 1 uses a lateral side-view camera.
  - Without camera calibration or dynamic perspective normalization, 2D keypoint projections differ radically between ceiling and lateral perspectives.
- **Affected Samples:**
  - All UP-Fall Camera 1 sequences (`upfall-s12` through `upfall-s17`).

### F. SYSTEM & FAULT TOLERANCE
- **Assessment:** Stream reconnects, MQTT outages, and backend restarts were 100% resilient (20/20 UAT passed).
- **Findings:** Zero system crashes, memory leaks, or unhandled exceptions occurred across all 43 video evaluations and soak tests.

### G. AGENT & VLM CONTEXTUAL ENRICHMENT
- **Assessment:** VLM narrative enrichment is strictly asynchronous and decoupled from real-time alerting.
- **Findings:** VLM provider latency (200ms–2000ms) or provider outages do not impede or alter detector alerts, ensuring critical life-safety alerting remains sub-second.

---

## 3. Comprehensive System Limitations

1. **Poor Cross-Dataset Generalization:**
   Fixed 2D geometric and velocity heuristics do not generalize across varying camera heights, tilt angles, and focal lengths without per-camera calibration.

2. **Dataset Scale & Diversity:**
   Public academic datasets (URFD with 70 seqs, UP-Fall with 17 subjects) feature young healthy volunteers performing staged falls onto mats. They lack the nuanced kinetics of genuine frail elderly falls (stumble, wall grab, slow slide).

3. **Occlusion & Cluttered Home Environments:**
   Furniture occlusion (blankets, tables, low beds) obstructs hip and knee keypoints, degrading pose confidence.

4. **Lighting & Optical Noise:**
   Sudden illumination changes, direct sunlight glare, and night-vision infrared noise degrade keypoint confidence.

5. **Lack of Clinical & Real-World Validation:**
   This system is an engineering prototype and proof-of-concept. It has **NOT** undergone medical device certification, clinical trials, or validation in unconstrained clinical eldercare environments.

6. **VLM Contextual Limitations:**
   Vision-Language Models can provide rich post-incident context (e.g. "person holding chest") but cannot replace deterministic, millisecond-level edge pose inference for initial alarm dispatch.

---

## 4. Recommendations for Future Research (Post-Phase 11)

- Implement 3D pose lifting or camera extrinsic calibration to achieve perspective-invariant velocity calculation.
- Train end-to-end temporal action recognition models (e.g. ST-GCN, Video Transformers) on larger multi-view datasets.
- Implement adaptive multi-camera fusion to eliminate single-view occlusion vulnerabilities.
