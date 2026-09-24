# P11-003 — UP-Fall Final Robustness Evaluation Report

## 1. Executive Summary

- **Evaluation Task:** P11-003 — UP-Fall Detection Dataset Final Held-Out Evaluation (Camera 1 RGB)
- **Execution Date:** 2026-09-24T13:15:42Z
- **Hardware:** NVIDIA GeForce RTX 3070 8GB
- **Inference Runtime:** TensorRT 11 FP16
- **Frozen Baseline Model:** `yolo26s-pose` (SHA-256 `a083adb423...`)
- **Frozen TensorRT Engine:** `yolo26s-pose.engine` (SHA-256 `6cf6142e7d...`)
- **Frozen Fall Detection Config:** `config/fall_detection.yaml` (SHA-256 `b56152c7da...`)

## 2. Classification Results & Raw Counts

| Metric | Measured Value |
|---|---|
| **Total Test Sequences** | **15** |
| Ground Truth Falls | 8 |
| Ground Truth ADLs | 7 |
| **True Positives (TP)** | **0** |
| **False Positives (FP)** | **0** |
| **True Negatives (TN)** | **7** |
| **False Negatives (FN)** | **8** |

### Robustness Performance Metrics

- **Accuracy:** 46.67%
- **Precision:** 0.00%
- **Recall (Sensitivity):** 0.00%
- **F1 Score:** 0.00%

*(Note: Formal final multi-dataset metric consolidation will be compiled in P11-005).*

## 3. Descriptive Comparison with Frozen URFD Baseline

- **URFD (Primary Benchmark):** TP=1, FP=10, TN=6, FN=11 (Precision=9.09%, Recall=8.33%, F1=8.70%, Accuracy=25.00%)
- **UP-Fall (Robustness Benchmark):** TP=0, FP=0, TN=7, FN=8 (Precision=0.00%, Recall=0.00%, F1=0.00%, Accuracy=46.67%)
- **Generalization Note:** Cross-dataset differences highlight domain shift across camera angles, framerates, room geometry, and subject variations without tuning detector thresholds.

## 4. Per-Sequence Evaluation Ledger

| Sample ID | Subject | Activity | Ground Truth | Prediction | Class | Incidents | FPS |
|---|---|---|---|---|:---:|:---:|:---:|
| `upfall-s12-a01-t1` | Subject12 | fall_forward | **Fall** | Normal | **FN** | 0 | 31.7 |
| `upfall-s12-a02-t1` | Subject12 | fall_backward | **Fall** | Normal | **FN** | 0 | 150.0 |
| `upfall-s12-a06-t1` | Subject12 | walking | ADL | Normal | **TN** | 0 | 151.3 |
| `upfall-s12-a08-t1` | Subject12 | sitting | ADL | Normal | **TN** | 0 | 158.2 |
| `upfall-s13-a01-t1` | Subject13 | fall_forward | **Fall** | Normal | **FN** | 0 | 170.6 |
| `upfall-s13-a02-t1` | Subject13 | fall_backward | **Fall** | Normal | **FN** | 0 | 170.7 |
| `upfall-s13-a06-t1` | Subject13 | walking | ADL | Normal | **TN** | 0 | 157.1 |
| `upfall-s14-a01-t1` | Subject14 | fall_forward | **Fall** | Normal | **FN** | 0 | 169.9 |
| `upfall-s14-a06-t1` | Subject14 | walking | ADL | Normal | **TN** | 0 | 160.6 |
| `upfall-s15-a01-t1` | Subject15 | fall_forward | **Fall** | Normal | **FN** | 0 | 173.6 |
| `upfall-s15-a08-t1` | Subject15 | sitting | ADL | Normal | **TN** | 0 | 162.1 |
| `upfall-s16-a01-t1` | Subject16 | fall_forward | **Fall** | Normal | **FN** | 0 | 160.6 |
| `upfall-s16-a06-t1` | Subject16 | walking | ADL | Normal | **TN** | 0 | 153.9 |
| `upfall-s17-a01-t1` | Subject17 | fall_forward | **Fall** | Normal | **FN** | 0 | 168.4 |
| `upfall-s17-a08-t1` | Subject17 | sitting | ADL | Normal | **TN** | 0 | 165.5 |

## 5. Failure & Limitations Analysis

- **Decode Failures:** 0 / 15 sequences.
- **Subject-Disjoint Guarantee:** All 15 test sequences belong strictly to held-out test subjects (`Subject12` through `Subject17`), ensuring zero cross-subject leakage with the 27 development sequences.
- **Zero-Tuning Policy:** Evaluated strictly once without weight updates or threshold tuning.

## 6. Verification & Integrity Confirmation

- All 15 test sequences evaluated strictly once.
- 0% sequence or subject overlap with development set.
- Zero model weights or threshold modifications performed.
