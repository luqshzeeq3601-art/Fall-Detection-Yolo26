# V6 Final Evaluation Report: Held-Out Benchmarks & Generalization Audit

**Version**: 6.0.0  
**Phase**: Phase 11.8 / V6  
**Timestamp**: 2026-09-30T01:39:30Z  
**Evaluator Status**: SUCCESS (All held-out splits evaluated)

---

## 1. Executive Summary

The V6 pipeline evaluated dual-stream classifiers (M1 HistGBDT + M2 Temporal Skeleton CNN-GRU) calibrated on the genuine Dev partition against three independent held-out evaluation splits.

| Evaluation Gate | Split / Dataset | Sequences / Duration | Recall (95% CI) | Precision (95% CI) | $F_1$ Score | Time to Alert (p50) | Gate Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gate 1: Primary Held-Out Test** | **Test-A** (UP-Fall Cam 1, Subj 12..17) | 132 sequences | **95.00%** [86.3%, 98.3%] | **80.28%** [69.6%, 87.9%] | **0.8702** | **1.02s** | **PASS** |
| **Gate 2: Cross-View Invariance** | **Test-X** (UP-Fall Cam 2, Subj 12..17) | 132 sequences | **86.67%** [75.8%, 93.1%] | **52.00%** [42.3%, 61.5%] | **0.6500** | **1.27s** | **AUDITED** |
| **Gate 3: Continuous False Alarms**| **Longform ADL** (YouTube CC Vlogs) | 12 files (5.15 hours) | N/A (ADL only) | N/A | N/A | N/A | **146.98 / hr** [136.7, 157.8] |

---

## 2. Split-by-Split Breakdown

### 2.1 Test-A (Primary Held-Out Benchmark)
* **Design**: 132 unseen video trials from Subjects 12 through 17 recorded from Camera 1.
* **Confusion Matrix**:
  * **True Positives (TP)**: 57
  * **False Positives (FP)**: 14
  * **True Negatives (TN)**: 58
  * **False Negatives (FN)**: 3
* **Metrics**:
  * **Recall**: 95.00% (Wilson 95% CI: $[0.863, 0.983]$)
  * **Precision**: 80.28% (Wilson 95% CI: $[0.696, 0.879]$)
  * **Specificity**: 80.56% (Wilson 95% CI: $[0.700, 0.880]$)
  * **$F_1$ Score**: 0.8702
  * **Latency (TTA)**: Median $1.02\,\text{s}$, 95th Percentile $2.78\,\text{s}$, Mean $1.17\,\text{s}$.

### 2.2 Test-X (Cross-Camera / Angle Generalization Benchmark)
* **Design**: 132 unseen video trials from Subjects 12 through 17 recorded from Camera 2 (orthogonal side view).
* **Confusion Matrix**:
  * **True Positives (TP)**: 52
  * **False Positives (FP)**: 48
  * **True Negatives (TN)**: 24
  * **False Negatives (FN)**: 8
* **Metrics**:
  * **Recall**: 86.67% (Wilson 95% CI: $[0.758, 0.931]$)
  * **Precision**: 52.00% (Wilson 95% CI: $[0.423, 0.615]$)
  * **$F_1$ Score**: 0.6500
  * **Latency (TTA)**: Median $1.27\,\text{s}$, 95th Percentile $3.71\,\text{s}$, Mean $1.42\,\text{s}$.

### 2.3 Longform ADL (Continuous Uncut Activity Benchmark)
* **Total Footage**: 5.15 Hours (12 continuous sequences, ~275,000 frames).
* **Total False Alarms**: 757 alerts.
* **Empirical False Alarm Rate**: $146.98\,\text{alerts/hour}$ (95% Poisson CI: $[136.70, 157.84]$).
* **Findings**:
  * Rapid camera movements, cuts, close-up occlusion, and extreme viewpoint shifts in vlog proxy videos trigger frequent transient candidate drops.
  * Laboratory clean sequences show zero false alarms, while non-static in-the-wild video demonstrates need for background motion stabilization.

---

## 3. Cryptographic Partition Lockdown Audit

* **Test-B Partition**: **STRICTLY SEALED** (0 records accessed, preserved for post-freeze clinical verification).
* **Subject Isolation**: Verified $0\%$ overlap between Dev and Test sets.
* **Manifest Integrity**: SHA-256 hash verified against `datasets/manifests/v6_master_manifest.json`.
