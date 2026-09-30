# V6 Rescored Baseline Report (Diagnostic)

**Evaluation Version**: 6.1.0  
**Phase**: Phase 0 Baseline Audit  
**Evaluation Engine**: Strict `EventMatcher` (window $[-1.0\,\text{s}, +3.0\,\text{s}]$) with unclamped TTA.  
**Provenance Manifest**: `datasets/manifests/v6_master_manifest.json`

---

## 1. Summary of Rescored Metrics

| Split | Sequences / Hours | Recall (95% CI) | Precision (95% CI) | Specificity (95% CI) | $F_1$ Score | P95 TTA | False Alarms / hr (95% Poisson CI) | Gate Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Test-A** (Diagnostic) | 132 seqs | **95.00%** [86.3%, 98.3%] | **50.89%** [41.8%, 60.0%] | **51.33%** [42.2%, 60.3%] | **0.6628** | **3.19s** | N/A | **FAIL** (Prec < 85%, TTA > 3s) |
| **Test-X** (Diagnostic) | 132 seqs | **81.67%** [70.1%, 89.4%] | **37.12%** [29.4%, 45.6%] | **22.43%** [15.6%, 31.2%] | **0.5104** | **3.88s** | N/A | **FAIL** (Recall < 90%, Prec < 85%) |
| **Longform ADL** | 12 files (5.15 h) | N/A | N/A | N/A | N/A | N/A | **146.98 / hr** [136.7, 157.8] | **FAIL** (FA/h > 0.05) |

---

## 2. Activity Breakdown Highlights (Test-A)

* **`lying_down`**: 11/12 sequences triggered false alarms (**108 total false alerts**; precision 0.0%).
* **`sitting`**: 3/12 sequences triggered false alarms (9 total alerts; precision 0.0%).
* **Post-Fall Repetition**: In `fall_from_chair` and `fall_forward_knees`, once a fall occurred, the pipeline repeatedly re-triggered alerts after the 5s cooldown expired while the subject remained stationary on the floor.
* **`jumping` / `walking` / `standing` / `picking_up_object`**: 0 false alarms.

---

## 3. Reference Artifacts
* JSON Report: [V6_RESCORED_BASELINE.json](file:///C:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/eldercare-vision/docs/reports/V6_RESCORED_BASELINE.json)
* Alert Sidecar: [V6_RESCORED_BASELINE_alert_dump.json](file:///C:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/eldercare-vision/docs/reports/V6_RESCORED_BASELINE_alert_dump.json) (1,229 total alerts captured)
