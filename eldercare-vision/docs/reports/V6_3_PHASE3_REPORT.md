# V6.3 Phase 3: Decision-Stage Redesign

**Models**: `models/v6_3_phase3` (same M2 and out-of-fold signals as `v6_2_phase2_mp`; only the decision stage and calibration changed)
**Reports**: [V6_3_PHASE3_FUNNEL.json](V6_3_PHASE3_FUNNEL.json), [V6_3_PHASE3_DEV2_EVALUATION.json](V6_3_PHASE3_DEV2_EVALUATION.json), `models/v6_3_phase3/v6_calibration_grid.json`

## 1. Changes

1. **Bug fix: camera-level handover discarded every handed-over candidate.**
   - When a track is lost mid-fall, the next track inherited only the candidate *time*, not the kinetic peak.
   - With `require_falling_motion=True`, `PostProcessorV5` then reset the candidate as soon as low posture appeared.
   - The handover now carries the peak `p_falling` of the trigger burst.
   - Regression test: `test_camera_handover_carries_kinetic_evidence_to_new_track`.
2. **Calibration grid widened** (3,960 points):
   - trigger thresholds extended up to 0.70 / 0.80;
   - down thresholds extended up to 0.65 / 0.75;
   - new `transition_max_window_sec` axis (2 s / 3 s).
3. **Objective is the worst camera view.** The recall gate uses the minimum per-camera recall.
4. **The report includes the Pareto front** over (min camera recall, FA/h, precision).

## 2. Effect of the handover fix alone (Phase 2 operating point 0.60 / 0.55 / 0.45 s / 2 s)

| | Before fix | After fix |
|---|---|---|
| Dev recall cam1 / cam2 / URFD | 99% / 49% / 87% | 99% / **68%** / 87% |
| dev_longform false alerts (4.3 h) | 1 (0.23/h) | 3 (0.70/h) |
| Dev p95 TTA | 3.03 s | 3.40 s |

## 3. Selected operating point (smallest gate shortfall; no point meets every gate)

Trigger 0.80, down 0.65, sustain 0.30 s, transition window 3.0 s.

| Metric | Phase 2 | Phase 3 |
|---|---|---|
| Dev recall cam1 / cam2 / URFD | 99% / 49% / 87% | 96% / **69%** / 87% |
| Dev min-camera recall | 49% | **69%** |
| Dev precision | 96% | 94% |
| dev_longform FA/h | 0.23 | 0.70 |
| Dev p95 TTA | 3.03 s | 3.25 s |
| Test-A (dev-2) recall / precision / p95 TTA | 100% / 100% / 1.36 s | 100% / 100% / 1.36 s |
| Test-X (dev-2) recall / precision / p95 TTA | 30% / 95% / 3.77 s | **57% / 89% / 3.17 s** |

**Pareto front** (dev): cam2 recall reaches 80% at 2.1 FA/h. The lowest FA/h on the front is 0.70 (3 alerts in 4.3 h), at cam2 recall 62–70%.

## 4. What still blocks the gates

- **Tracking ceiling on cam2.** The falling person is tracked through the fall in only 131/164 dev cam2 clips (80%). Of the 51 remaining dev cam2 misses, 24 have no tracked falling person, so decision thresholds can't recover them. The other 27 fail low-posture confirmation (15) or sustain (12) on a tracked subject.
- **p95 TTA is just over 3 s.** Alerts that come through the handover are about 1–2 s later than same-track alerts.
- **FA/h can't be shown to be ≤ 0.05.** The dev_longform set holds 4.3 h and uses single-person caches.
- **Not done: using body-normalised descent as an alternative low-posture signal.** It could reach the 27 tracked-subject misses; it is the next decision-stage lever.
