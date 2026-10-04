# User Acceptance Testing (UAT) Report — ElderCare Vision

**System**: ElderCare Vision Portfolio Fall Detection System  
**Evaluation Date**: 2026-10-04  
**Evaluator**: Quality Assurance & Test Engineering Team  
**Evaluation Split**: Test-B Held-Out (132 sequences: 60 falls, 72 ADLs)  
**Model Version**: `yolo26s-pose.pt` (TensorRT FP16) + `temporal_skeleton_classifier_v6.pt` (CNN-GRU V6.3)  
**Overall UAT Gate**: **PASSED** (20/20 Scenarios Verified)

---

## 1. Executive Summary

All 20 acceptance criteria defined in [`docs/planning/UAT_PLAN.md`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/planning/UAT_PLAN.md) were rigorously verified against actual system execution, unit test suites, and the frozen Test-B held-out dataset benchmark.

- **Sensitivity / Recall**: **98.3%** (59 / 60 falls detected)
- **Specificity (ADL Rejection)**: **98.6%** (71 / 72 non-fall activities rejected)
- **Alert Latency**: Median Time-to-Alert (TTA) of **0.85s** (p95: 1.58s, well within ≤ 3.0s ceiling)
- **Architectural Resilience**: Decoupled async VLM/MQTT guarantees uninterrupted vision processing even during network or provider outages.

---

## 2. UAT Verification Matrix

| Test ID | Scenario | Expected Result | Actual Result | Status | Evidence / Reference |
|---|---|---|---|:---:|---|
| **UAT-01** | Normal walking | No fall incident | 12/12 walking sequences rejected with 0 false alerts (mean temporal score: 0.026). Upright velocity checks stable. | **PASS** | [`adl-walking-tn.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/adl-walking-tn.png), `test_b` |
| **UAT-02** | Sitting normally | No fall incident | 12/12 sitting sequences rejected. Torso inclination and controlled descent velocity correctly distinguish sitting from collapse. | **PASS** | [`per_scenario_metrics.csv`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/results/evaluation/per_scenario_metrics.csv) |
| **UAT-03** | Standing up | No fall incident | 12/12 standing transitions rejected. Upward vertical velocity correctly recognized as restorative. | **PASS** | `test_portfolio_evaluation.py` |
| **UAT-04** | Bending / picking object | No fall incident | 12/12 bending sequences rejected. Momentary torso tilt triggers candidate state, but rapid upright restoration vetoes confirmation. | **PASS** | `test_fall_state_machine.py` |
| **UAT-05** | Kneeling | No fall incident | Controlled descent to knees maintains upright head/torso posture; no fall alert emitted. | **PASS** | `test_unit_kneeling_recovery.py` |
| **UAT-06** | Intentional slow lying down | No rapid-fall classification where temporal dynamics absent; record behavior | 11/12 lying down sequences correctly rejected. 1 false alert noted on rapid mattress dive (`upfall_s13_a11_t03_c1`) due to sudden velocity mimicry. | **PASS** | [`adl-false-positive.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/adl-false-positive.png), `metrics.json` |
| **UAT-07** | Controlled safe simulated fall / video | Fall candidate then confirmed incident | 59/60 falls detected (98.3% recall). State machine advances from `NORMAL` → `FALLING` → `CONFIRMED_FALL` within temporal window. | **PASS** | [`fall-forward-tp.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/fall-forward-tp.png), [`fall-backward-tp.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/fall-backward-tp.png) |
| **UAT-08** | Person remains down | One incident; no alert storm | Debounce and cooldown timers lock track state after confirmation; exactly 1 primary alert emitted per fall event. | **PASS** | `test_alert_debouncing.py` |
| **UAT-09** | Person recovers | Transition to recovery / normal | If person regains upright posture within timeout window, pipeline transitions track from `CONFIRMED_FALL` to `RECOVERED`. | **PASS** | `test_recovery_transition.py` |
| **UAT-10** | Partial occlusion | No crash; confidence/evidence reflects uncertainty | Evaluated on Camera 2 lateral angle (29/30 falls detected). Lower-body occlusion handled gracefully with Kalman filter tracking. | **PASS** | [`fall-false-negative.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/fall-false-negative.png) |
| **UAT-11** | Two people | Separate track IDs where tracker permits | ByteTrack maintains independent track states and temporal feature buffers across multiple targets without cross-contamination. | **PASS** | `test_multitrack_scalability` |
| **UAT-12** | Low light | System remains stable; degraded AI performance measured | Tested with synthetic low-lux frames; pose confidence drops gracefully; low-confidence keypoints flagged without unhandled exceptions. | **PASS** | `test_low_light_robustness.py` |
| **UAT-13** | Camera disconnected | Offline event + reconnect attempts | Video source failure captured by OpenCV watchdog; triggers exponential backoff reconnection without crashing host process. | **PASS** | `test_camera_stream_watchdog.py` |
| **UAT-14** | Camera restored | Automatic reconnect | Frame ingestion resumes automatically upon stream re-establishment. | **PASS** | `test_camera_reconnect.py` |
| **UAT-15** | MQTT unavailable | Core detection continues | Async MQTT alert dispatcher queues alerts in bounded ring buffer; network drop does not block vision processing loop. | **PASS** | `test_resilient_mqtt_publisher.py` |
| **UAT-16** | VLM unavailable | Core detection continues | VLM is decoupled and asynchronous; core YOLO+GRU detector operates deterministically at 212+ FPS with zero external API dependencies. | **PASS** | `test_vlm_circuit_breaker.py` |
| **UAT-17** | Dashboard closed | Backend/vision continue | Streamlit dashboard runs as independent consumer on HTTP/WebSocket; shutting down browser or UI does not interrupt vision pipeline. | **PASS** | Process isolation verified |
| **UAT-18** | Backend / API restart | Service recovers; persisted incidents remain | SQLite/PostgreSQL storage holds all confirmed alerts, keypoint logs, and metadata across process restarts. | **PASS** | `test_database_persistence.py` |
| **UAT-19** | Human review | Review saved without changing detector record | Audit log endpoints record clinician review annotations in append-only tables; immutable detector evidence is strictly preserved. | **PASS** | `test_audit_immutability.py` |
| **UAT-20** | Extended runtime | No unhandled crash / resource leak beyond accepted bounds | Continuous 0.833h benchmark (30,000+ frames) maintained constant peak RSS of ~493 MB and 0 memory leaks. | **PASS** | [`performance-benchmark.png`](file:///c:/Users/ZeeqRyz/Desktop/Fall%20Detection%20Yolo26/docs/assets/results/performance-benchmark.png) |

---

## 3. Discovered Failure Mode Analysis

Per engineering transparency standards, two edge cases were discovered and thoroughly analyzed:

1. **False Negative (FN) Case — `upfall_s12_a01_t03_c2`**:
   - **Scenario**: Forward fall with hands protecting face, captured from Camera 2 (low-profile lateral view).
   - **Root Cause**: Extreme perspective foreshortening directly towards the camera lens combined with occlusion from furniture prevented vertical bounding box collapse thresholding before ground contact.
   - **Remediation**: Multi-camera consensus or 3D skeleton projection in Phase 4.

2. **False Positive (FP) Case — `upfall_s13_a11_t03_c1`**:
   - **Scenario**: Lying down on mattress, captured from Camera 1 (ceiling view).
   - **Root Cause**: Subject rapidly dived onto bed at high downward velocity, temporarily mimicking a collapse trajectory before settling.
   - **Remediation**: Posture settling dwell time threshold slightly increased in non-emergency profile.

---

## 4. Acceptance Sign-off

- [x] **Test Engineer QA**: PASSED
- [x] **Safety & Architecture Review**: PASSED
- [x] **Portfolio Evidence Documentation**: COMPLETE
