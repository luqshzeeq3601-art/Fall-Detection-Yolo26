# P11-002 — URFD Final Evaluation Report

## 1. Executive Summary

- **Evaluation Task:** P11-002 — UR Fall Detection Dataset (URFD) Final Held-Out Evaluation
- **Execution Date:** 2026-09-23T15:37:09Z
- **Hardware:** NVIDIA GeForce RTX 3070 8GB
- **Inference Runtime:** TensorRT 11 FP16
- **Frozen Baseline Model:** `yolo26s-pose` (SHA-256 `a083adb423...`)
- **Frozen TensorRT Engine:** `yolo26s-pose.engine` (SHA-256 `6cf6142e7d...`)
- **Frozen Fall Detection Config:** `config/fall_detection.yaml` (SHA-256 `b56152c7da...`)

## 2. Classification Results & Raw Counts

| Metric | Measured Value |
|---|---|
| **Total Test Sequences** | **28** |
| Ground Truth Falls | 12 |
| Ground Truth ADLs | 16 |
| **True Positives (TP)** | **1** |
| **False Positives (FP)** | **10** |
| **True Negatives (TN)** | **6** |
| **False Negatives (FN)** | **11** |

### Preliminary Performance Metrics

- **Accuracy:** 25.00%
- **Precision:** 9.09%
- **Recall (Sensitivity):** 8.33%
- **F1 Score:** 8.70%

*(Note: Formal final multi-dataset metric consolidation will be compiled in P11-005).*

## 3. Time-to-Alert (TTA) Analysis

- **Evaluated on:** 1 True Positive fall sequences with authoritative ground-truth onset timestamps.
- **Mean Time-to-Alert:** 2.033 s
- **Median Time-to-Alert:** 2.033 s
- **p95 Time-to-Alert:** 2.033 s

## 4. Per-Sequence Evaluation Ledger

| Sample ID | Activity | Ground Truth | Prediction | Class | Incidents | Time-to-Alert | Inference FPS |
|---|---|---|---|:---:|:---:|:---:|:---:|
| `urfd-fall-19-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 44.6 |
| `urfd-fall-20-cam0` | fall | **Fall** | **Fall** | **TP** | 1 | 2.033s | 117.9 |
| `urfd-fall-21-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 103.4 |
| `urfd-fall-22-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 103.2 |
| `urfd-fall-23-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 97.6 |
| `urfd-fall-24-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 106.8 |
| `urfd-fall-25-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 114.9 |
| `urfd-fall-26-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 106.6 |
| `urfd-fall-27-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 118.6 |
| `urfd-fall-28-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 106.5 |
| `urfd-fall-29-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 114.5 |
| `urfd-fall-30-cam0` | fall | **Fall** | Normal | **FN** | 0 | - | 112.1 |
| `urfd-adl-25-cam0` | walking | ADL | Normal | **TN** | 0 | - | 113.2 |
| `urfd-adl-26-cam0` | sitting | ADL | Normal | **TN** | 0 | - | 111.3 |
| `urfd-adl-27-cam0` | bending | ADL | Normal | **TN** | 0 | - | 122.3 |
| `urfd-adl-28-cam0` | lying | ADL | Normal | **TN** | 0 | - | 116.1 |
| `urfd-adl-29-cam0` | walking | ADL | Normal | **TN** | 0 | - | 128.7 |
| `urfd-adl-30-cam0` | sitting | ADL | **Fall** | **FP** | 2 | - | 159.2 |
| `urfd-adl-31-cam0` | bending | ADL | **Fall** | **FP** | 1 | - | 144.0 |
| `urfd-adl-32-cam0` | lying | ADL | **Fall** | **FP** | 1 | - | 137.3 |
| `urfd-adl-33-cam0` | walking | ADL | **Fall** | **FP** | 1 | - | 138.5 |
| `urfd-adl-34-cam0` | sitting | ADL | **Fall** | **FP** | 1 | - | 136.8 |
| `urfd-adl-35-cam0` | bending | ADL | **Fall** | **FP** | 3 | - | 144.7 |
| `urfd-adl-36-cam0` | lying | ADL | **Fall** | **FP** | 1 | - | 146.0 |
| `urfd-adl-37-cam0` | walking | ADL | **Fall** | **FP** | 2 | - | 142.6 |
| `urfd-adl-38-cam0` | sitting | ADL | **Fall** | **FP** | 1 | - | 145.8 |
| `urfd-adl-39-cam0` | bending | ADL | **Fall** | **FP** | 1 | - | 147.6 |
| `urfd-adl-40-cam0` | lying | ADL | Normal | **TN** | 0 | - | 153.1 |

## 5. Failure & Limitations Analysis

- **Decode Failures:** 0 / 28 sequences.
- **Pose Detection Quality:** High robustness observed across all sequences.
- **False Alarm Analysis:** Detailed error breakdown across ADLs recorded in ledger for P11-006 error analysis.

## 6. Verification & Integrity Confirmation

- All 28 test sequences evaluated strictly once.
- 0% sequence overlap with the 42 development sequences.
- Zero model weights or threshold modifications performed during or after evaluation.
