# V6 Final Evaluation Report: Held-Out Benchmarks & Generalization Audit

**Version**: 6.0.0  
**Phase**: Phase 11.8 / V6 (Superceded by V6 Rescored Baseline)  
**Timestamp**: 2026-09-30T01:39:30Z  
**Evaluator Status**: COMPLETED (Audited — Pre-declared Gate Criteria FAILED)

---

## 1. Executive Summary

**Headline metrics are event-level** (strict `EventMatcher`, window $[-1.0\,	ext{s}, +3.0\,	ext{s}]$, unclamped TTA). The clip-level any-alert numbers originally reported here overstated precision and are kept in Section 2 for traceability only.

| Evaluation Gate | Split / Dataset | Sequences / Duration | Recall (95% CI) | Precision (95% CI) | $F_1$ Score | P95 TTA | Gate Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gate 1: Primary Test** | **Test-A** (UP-Fall Cam 1, Subj 12..17) | 132 sequences | **95.00%** [86.3%, 98.3%] | **50.89%** [41.8%, 60.0%] | **0.6628** | **3.19s** | **FAIL** (Precision < 85%, TTA > 3s) |
| **Gate 2: Cross-View** | **Test-X** (UP-Fall Cam 2, Subj 12..17) | 132 sequences | **81.67%** [70.1%, 89.4%] | **37.12%** [29.4%, 45.6%] | **0.5104** | **3.88s** | **FAIL** (Recall < 90%, Precision < 85%) |
| **Gate 3: Continuous False Alarms** | **Longform ADL** (YouTube CC Vlogs) | 12 files (5.15 hours) | N/A (ADL only) | N/A | N/A | N/A | **FAIL** (146.98 / hr vs <= 0.05 target) |

> [!IMPORTANT]
> **Evidence status (Phase 0 audit, 2026-09-30).**
> * Test-A and Test-X have since been evaluated under several operating points (V6, V6.1, V6.1 no-fixes, diagnostic thresholds). They are **burned**: from now on they are development diagnostics ("dev-2"), not held-out evidence. Only the sealed **Test-B** and **`longform_adl_heldout`** splits support a final claim.
> * The longform false-alarm rate above was measured on footage the model trained on (in-sample). Longform videos are now grouped by creator; HattieHomemaking and LaurenWhittington (0.83 h) are sealed as `longform_adl_heldout`.
>
> Details: [V6_RESCORED_BASELINE.md](V6_RESCORED_BASELINE.md).

---

## 2. Split-by-Split Breakdown

### 2.1 Test-A (Primary Benchmark; clip-level, superseded)
* **Design**: 132 unseen video trials from Subjects 12 through 17 recorded from Camera 1.
* **Confusion Matrix (Clip-Level)**:
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

### 2.2 Test-X (Cross-Camera Benchmark; clip-level, superseded)
* **Design**: 132 unseen video trials from Subjects 12 through 17 recorded from Camera 2 (orthogonal side view).
* **Confusion Matrix (Clip-Level)**:
  * **True Positives (TP)**: 52
  * **False Positives (FP)**: 48
  * **True Negatives (TN)**: 24
  * **False Negatives (FN)**: 8
* **Metrics**:
  * **Recall**: 86.67% (Wilson 95% CI: $[0.758, 0.931]$)
  * **Precision**: 52.00% (Wilson 95% CI: $[0.423, 0.615]$)
  * **$F_1$ Score**: 0.6500
  * **Latency (TTA)**: Median $1.27\,\text{s}$, 95th Percentile $3.71\,\text{s}$, Mean $1.42\,\text{s}$.

### 2.3 Longform ADL (Continuous Uncut Activity Benchmark; in-sample)
* **Total Footage**: 5.15 Hours (12 continuous sequences, ~275,000 frames).
* **Total False Alarms**: 757 alerts.
* **Empirical False Alarm Rate**: $146.98\,\text{alerts/hour}$ (95% Poisson CI: $[136.70, 157.84]$).
* **Audit Findings**:
  * Root causes include initiation of candidate state from `p_fallen` alone without prior kinetic descent, geometric floor check firing on partial skeletons, and bypassing the ADL suppressor when floor posture is asserted.
  * Controlled laboratory sequences also showed elevated false alarms on lying down and sitting activities.

---

## 3. Cryptographic Partition Lockdown Audit

* **Test-B Partition**: **STRICTLY SEALED** (0 records accessed, preserved for post-freeze clinical verification).
* **Subject Isolation**: Verified $0\%$ overlap between Dev and Test sets.
* **Manifest Integrity**: SHA-256 hash verified against `datasets/manifests/v6_master_manifest.json`.
