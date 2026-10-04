# ElderCare Vision — Model Evaluation Report

**System Under Test**: YOLO26s-Pose + ByteTrack + TemporalSkeletonClassifierV6.3 (CNN-GRU) + FallEnginePipelineV61  
**Frozen Evaluation Split**: Test-B Held-Out Split (UP-Fall Subjects 12–17, Trial 1, Cameras 1 & 2)  
**Evaluation Timestamp**: 2026-10-04 09:04:38 UTC  
**Deployment Gate Status**: ✅ **PASSED**

---

## 1. Executive Summary & Headline Metrics

The frozen ElderCare Vision V6.3 fall detection pipeline was evaluated against the sealed, held-out Test-B evaluation dataset comprising 132 video sequences (60 fall events across 5 motion types, and 72 diverse Activities of Daily Living).

| Metric | Measured Value (95% Wilson CI) | Target Gate | Status |
|---|---|---|---|
| **Recall (Sensitivity)** | **98.3%** (59/60) [91.1% – 99.7%] | ≥ 90.0% | ✅ PASS |
| **Precision (PPV)** | **98.3%** [91.1% – 99.7%] | ≥ 85.0% | ✅ PASS |
| **Specificity (ADL Rejection)** | **98.6%** (71/72) [92.5% – 99.8%] | ≥ 95.0% | ✅ PASS |
| **F1-Score** | **0.983** | ≥ 0.880 | ✅ PASS |
| **Time-to-Alert (Median / P95)** | **0.846s** / **1.579s** | P95 ≤ 3.0s | ✅ PASS |
| **False Alarms (Continuous Held-Out)** | **0.0 / hour** (0 alerts in 0.833h) | ≤ 0.05 / hour | ⚠️ Point estimate |

---

## 2. Confusion Matrix

| Actual \ Predicted | Predicted Fall | Predicted Non-Fall (ADL) | Total |
|---|---|---|---|
| **Actual Fall** | **59 (True Positive)** | **1 (False Negative)** | 60 |
| **Actual Non-Fall (ADL)** | **1 (False Positive)** | **71 (True Negative)** | 72 |
| **Total Sequences** | 60 | 72 | **132** |

- **Total False Alerts Emitted**: 2 (1 in `lying_down` ADL clip, 1 secondary alert inside fall clip)
- **Fall Sequences with Alerts**: 59/60 detected successfully.

---

## 3. Fall-Type Scenario Analysis

| Scenario / Motion Type | Total Sequences | Detected (TP) | Missed (FN) | Recall Rate | Median Time-to-Alert | Representative Case |
|---|---|---|---|---|---|---|
| **fall_backward** | 12 | 12 | 0 | **100.0%** | 0.753s | `upfall_s12_a03_t03_c1` |
| **fall_forward_hands** | 12 | 11 | 1 | **91.7%** | 0.741s | `upfall_s12_a01_t03_c1` |
| **fall_forward_knees** | 12 | 12 | 0 | **100.0%** | 0.921s | `upfall_s12_a02_t03_c1` |
| **fall_from_chair** | 12 | 12 | 0 | **100.0%** | 1.189s | `upfall_s12_a05_t03_c1` |
| **fall_sideways** | 12 | 12 | 0 | **100.0%** | 0.7s | `upfall_s12_a04_t03_c1` |

---

## 4. Activities of Daily Living (ADL) Rejection Analysis

| Activity Type | Total Sequences | Correctly Rejected (TN) | False Alerts (FP) | Specificity | False Positive Rate | Representative Case |
|---|---|---|---|---|---|---|
| **jumping** | 12 | 12 | 0 | **100.0%** | 0.0% | `upfall_s12_a10_t03_c1` |
| **lying_down** | 12 | 11 | 1 | **91.7%** | 8.3% | `upfall_s12_a11_t03_c1` |
| **picking_up_object** | 12 | 12 | 0 | **100.0%** | 0.0% | `upfall_s12_a09_t03_c1` |
| **sitting** | 12 | 12 | 0 | **100.0%** | 0.0% | `upfall_s12_a08_t03_c1` |
| **standing** | 12 | 12 | 0 | **100.0%** | 0.0% | `upfall_s12_a07_t03_c1` |
| **walking** | 12 | 12 | 0 | **100.0%** | 0.0% | `upfall_s12_a06_t03_c1` |

---

## 5. Viewpoint and Difficult Conditions Analysis

| Condition / Viewpoint | Sequences | Recall | Precision | Specificity | Key Observation |
|---|---|---|---|---|---|
| **Camera 1 (Ceiling High-Angle)** | 66 | **100.0%** (30/30) | **96.8%** | **97.2%** | High vantage point provides unoccluded view of floor plane and posture transitions. |
| **Camera 2 (Lateral Angle + Seated Bystander)** | 66 | **96.7%** (29/30) | **100.0%** | **100.0%** | Bystander presence handled by multi-person tracking and track stitching. |
| **Rapid Posture Change (`lying_down`)** | 12 | N/A | N/A | **91.7%** (11/12) | 1 false alert caused by rapid descent onto mattress mimicking fall velocity. |
| **Bending (`picking_up_object`)** | 12 | N/A | N/A | **100.0%** (12/12) | Correctly classified: torso orientation recovers upright without sustained floor posture. |
| **Dynamic Impact (`jumping`)** | 12 | N/A | N/A | **100.0%** (12/12) | Kinetic spike detected but immediately rejected because person remains upright. |

---

## 6. Root-Cause Analysis of Discrepancies

### The Single Missed Fall (False Negative)
- **Sequence**: `upfall_s16_a01_t01_c2` (`fall_forward_hands`, Subject 16, Camera 2)
- **Root Cause**: The fall occurred directly toward Camera 2 (extreme foreshortening). In addition, lower body limbs were partially occluded by the foreground mattress boundary. Although the kinetic trigger fired (`p_falling` = 0.58), the foreshortened posture failed to satisfy `p_fallen` or geometric flatness within the 3.0-second post-fall window.
- **Mitigation in Pipeline**: Body-normalized descent ratio recovered 90% of foreshortened falls; residual edge cases require wide-angle coverage or 3D bounding heuristics.

### The Single ADL False Alarm (False Positive)
- **Sequence**: `upfall_s12_a11_t01_c1` (`lying_down`, Subject 12, Camera 1)
- **Root Cause**: The participant executed an abrupt, uncontrolled dive onto the mattress rather than a controlled reclining motion. Vertical hip velocity exceeded 1.8 torso lengths/sec, satisfying both kinetic trigger and floor sustain thresholds.

---

## 7. Inference Latency and Hardware Performance

Measured on target **NVIDIA GeForce RTX 3070** (8GB VRAM, TDP 140W):

| Engine / Framework | Resolution | Batch Size | Precision | Median Latency | Throughput (FPS) |
|---|---|---|---|---|---|
| **TensorRT (Optimized)** | 640x640 | 1 | FP16 | **4.04 ms** | **212.9 FPS** |
| **PyTorch (Native)** | 640x640 | 1 | FP16 | 7.03 ms | 142.1 FPS |
| **PyTorch (Baseline)** | 640x640 | 1 | FP32 | 13.01 ms | 76.6 FPS |
| **ONNX Runtime** | 640x640 | 1 | FP32 | 8.44 ms | 118.4 FPS |

- **M2 Temporal Classifier Overhead**: ~0.08 ms per 2-second track window.
- **Multi-Track Scalability**: 364 FPS (1 person), 159 FPS (2 persons), 80.7 FPS (4 persons).

---

*Report generated by ElderCare Vision Test Engineer Pipeline.*