# P11-005 — Final Metrics Consolidation Report

## 1. Executive Summary

This report consolidates all empirical evaluation metrics for the frozen **ElderCare Vision** fall detection system across the primary benchmark (URFD), robustness benchmark (UP-Fall), and operational verification (Local UAT).

All metrics were computed strictly from immutable frozen evaluation ledgers without post-hoc tuning or parameter modifications.

---

## 2. Benchmark Metrics Summary

### Primary & Robustness Dataset Breakdown

| Metric | URFD (Primary Benchmark) | UP-Fall (Robustness Benchmark) | Combined Video Benchmarks |
|---|:---:|:---:|:---:|
| **Total Test Sequences** | **28** | **15** | **43** |
| Ground Truth Falls | 12 | 8 | 20 |
| Ground Truth ADLs | 16 | 7 | 23 |
| **True Positives (TP)** | **1** | **0** | **1** |
| **False Positives (FP)** | **10** | **0** | **10** |
| **True Negatives (TN)** | **6** | **7** | **13** |
| **False Negatives (FN)** | **11** | **8** | **19** |
| **Accuracy** | **25.00%** | **46.67%** | **32.56%** |
| **Precision** | **9.09%** | **0.00%** | **9.09%** |
| **Recall (Sensitivity)** | **8.33%** | **0.00%** | **5.00%** |
| **Specificity** | **37.50%** | **100.00%** | **56.52%** |
| **F1 Score** | **8.70%** | **0.00%** | **6.45%** |
| Non-Fall Monitored Duration | 149.63 s (0.0416 hr) | 56.00 s (0.0156 hr) | 205.63 s (0.0571 hr) |
| **False Alerts / Hour** | **240.61 / hr** | **0.00 / hr** | **175.07 / hr** |
| Duplicate Alerts | 0 | 0 | 0 |

---

## 3. Confusion Matrices

### URFD Confusion Matrix (28 Test Sequences)
```
                   Predicted Fall    Predicted Normal
Actual Fall              1 (TP)           11 (FN)
Actual ADL             10 (FP)            6 (TN)
```

### UP-Fall Confusion Matrix (15 Test Sequences)
```
                   Predicted Fall    Predicted Normal
Actual Fall              0 (TP)            8 (FN)
Actual ADL              0 (FP)            7 (TN)
```

### Combined Video Confusion Matrix (43 Test Sequences)
```
                   Predicted Fall    Predicted Normal
Actual Fall              1 (TP)           19 (FN)
Actual ADL             10 (FP)           13 (TN)
```

---

## 4. Operational Latency & Time-to-Alert (TTA)

- **Authoritative TTA Sample:** `urfd-fall-20-cam0`
  - Ground Truth Onset Timestamp: `0.600 s` (Frame 18 @ 30 FPS)
  - Confirmed Fall Alert Timestamp: `2.633 s` (Frame 79 @ 30 FPS)
  - **Measured Time-to-Alert:** **2.033 s** (Meets `< 3.0 s` real-time requirement)
- **Inference Throughput:**
  - Synthetic / Peak Benchmark: **212.91 FPS** (RTX 3070 TensorRT FP16)
  - Video Stream End-to-End Evaluation: **120–170 FPS**

---

## 5. Local Camera & System UAT Summary

- **Total UAT Scenarios Evaluated:** 20 / 20 (UAT-01 through UAT-20)
- **Passed:** 20 (100.0%)
- **Failed:** 0 (0.0%)
- **Blocked:** 0 (0.0%)
- **Functional Validation:** Verified walking, sitting, standing, bending, kneeling, controlled fall confirmation, single alert emission during sustained down, recovery reset, multi-person track isolation, stream reconnect, broker fault tolerance, VLM async boundary, and state persistence across restarts.

---

## 6. Portfolio Target Comparison

| Dimension | Portfolio Target | Measured Result | Status |
|---|---|---|:---:|
| **Inference Throughput** | >= 30.0 FPS | **212.91 FPS** (TensorRT FP16) | **MET** |
| **Time-to-Alert** | <= 3.0 s | **2.033 s** | **MET** |
| **UAT Scenario Coverage** | 100% Core Scenarios | **20 / 20 PASS (100%)** | **MET** |
| **Fall Recall** | >= 90.0% | **8.33% (URFD) / 0.00% (UP-Fall)** | **NOT MET** |
| **Precision** | >= 90.0% | **9.09% (URFD) / 0.00% (UP-Fall)** | **NOT MET** |
| **False Alerts / Hour** | <= 1.0 / hr | **240.61 / hr (URFD) / 0.00 / hr (UP-Fall)** | **NOT MET** |

### Integrity Policy Confirmation
In accordance with ADR-005 and the Phase 11 Evaluation Integrity Policy:
- Target misses are documented transparently as empirical baseline findings.
- **Zero post-hoc threshold tuning or model weight modification was performed.**
- Comprehensive root-cause categorization of all misses is detailed in `docs/reports/P11-006-error-limitations-analysis.md`.
