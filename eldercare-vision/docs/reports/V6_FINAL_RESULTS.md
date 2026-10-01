# Fall Detection V6.3: Final Results

**Model**: `models/v6_3_phase3b`, frozen in `models/v6_3_phase3b/freeze_manifest.json` (commit `6e128e0`)
**Final evaluation**: run once, after the freeze, on the sealed Test-B and longform held-out splits ([V6_3_FINAL_TESTB_EVALUATION.json](V6_3_FINAL_TESTB_EVALUATION.json), commit `e139811`)
**Branch**: `v6-1-phase0-eval-integrity`

## 1. Headline result (sealed Test-B, UP-Fall subjects 12–17, cameras 1 and 2)

| Metric | Result (95% CI) | Gate | Status |
|---|---|---|---|
| Recall | **98.3%** (59/60) [91.1–99.7] | ≥ 90% | ✅ |
| Precision | **96.7%** [88.8–99.1] | ≥ 85% | ✅ |
| Specificity (ADL clips without any alert) | 98.6% (71/72) | n/a | n/a |
| F1 | 0.975 | n/a | n/a |
| Time-to-alert median / p95 | 0.85 s / **1.58 s** | p95 ≤ 3 s | ✅ |
| Recall, camera 1 / camera 2 | 100% (30/30) / 96.7% (29/30) | n/a | n/a |
| False alarms, longform held-out (0.83 h) | 0 → 0.0 /h, 95% CI [0, 3.59] | ≤ 0.05 /h | ⚠️ point estimate only |

**Errors:**
- One missed fall: `fall_forward_hands`, camera 2.
- Two false alerts: one in a `lying_down` ADL clip, and one extra alert inside a fall clip.

## 2. Pipeline

1. **Pose:** YOLO26s-pose with stock ByteTrack at 15 Hz. Every tracked person is kept (multi-person cache).
2. **Track stitching:** `OnlineTrackStitcher` rejoins a person whose tracker ID changes mid-fall. It uses only past frames.
3. **Per-track M2 classifier:** a CNN-GRU over 2 s windows of v2 skeleton features. It outputs `p_normal`, `p_falling` and `p_fallen`. The v2 features use one reference scale per window plus hip trajectory and velocity channels. Training uses camera-balanced sampling and squash/dropout augmentation.
4. **Decision stage:**
   - A kinetic trigger (`p_falling` ≥ 0.55) must be followed by low posture within 3 s.
   - Low posture can come from `p_fallen` ≥ 0.55, the geometric floor check, or body-normalised descent (hips ≥ 1 torso length down and body flat).
   - The low posture must be sustained for 0.45 s.
   - If a track is lost mid-fall, the camera-level handover carries the kinetic evidence to its replacement.
   - After an alert, no new alert fires until the person is upright again.

## 3. How we got here

| Stage | Dev recall cam1 / cam2 / URFD | Longform FA/h | Test-A recall | Test-X recall |
|---|---|---|---|---|
| V6.1 as reported (pre-audit) | n/a | 0.58 (leaky) | 78% | 2% |
| Phase 0: evaluation integrity | 71% / 10% / 47% | 4.63 (out-of-fold) | 77% | 2% |
| Phase 2: multi-person caches, stitching, v2 features | 99% / 49% / 87% | 0.23 | 100% | 30% |
| Phase 3: handover fix, worst-camera calibration | 96% / 69% / 87% | 0.70 | 100% | 57% |
| Phase 3 + descent low posture (**frozen**) | **99% / 90% / 97%** | 0.70 | 100% | **87%** |

Dev values are out-of-fold. Test-A and Test-X were used during development, so their numbers are dev-2 diagnostics.

### Key findings

1. **Evaluation leaks (Phase 0).**
   - Chunks of the same longform video fell into different CV folds, so the reported 0.58 FA/h was really 4.63 out-of-fold.
   - Test-A and Test-X had been evaluated under several operating points, so both were reclassified as development data.
2. **The pose cache tracked the wrong person (Phase 2).** It kept only `persons[0]`. On camera 2 that was usually a seated bystander, so the falling subject was in the cache for only 23/164 dev falls. This bug, not camera-view robustness, explained the camera-2 collapse.
3. **The handover could never fire (Phase 3).** When a track was lost mid-fall, the replacement track inherited only the candidate time. With `require_falling_motion`, every handed-over candidate was then rejected.
4. **Foreshortened falls never looked "fallen" (Phase 3).** On camera 2, `p_fallen` stayed low for falls toward the camera. Body-normalised descent recovered most of these.
5. **Hard-negative mining did not help** ([V6_4_HNM_REPORT.md](V6_4_HNM_REPORT.md)). Only 62 windows qualified, and event-level metrics got worse, so it was not adopted.

## 4. Limitations

1. **The FA/h target is unproven.** The held-out set gave 0 alerts in 0.83 h, so the 95% upper bound is 3.6 /h. Showing ≤ 0.05 /h needs about 60 h or more of held-out ADL footage. Charades has been ingested for this and paused (see [V6_5_PHASE4_DEFERRED.md](V6_5_PHASE4_DEFERRED.md)). Dev longform is currently 0.70 /h (3 alerts in 4.3 h).
2. **Test-B shares subjects with Test-A and Test-X.** All three use UP-Fall subjects 12–17 (different trials), and Test-A/X guided design decisions. So Test-B measures generalisation to new recordings of seen people, not to new people.
3. **It is a single lab with two camera views.** The falls are staged by young adults on a mattress. Real homes, other cameras and elderly people may perform worse.
4. **URFD precision is low.** On dev it is 67% (14 false alerts on 40 ADL clips): the model fires on that dataset's sitting, bending and lying.
5. **Tracking still limits camera 2.** On dev, the falling person isn't tracked through the fall in about 20% of camera-2 clips.
6. **Longform caches are single-person.** The dev and held-out vlogs have not been re-extracted with every tracked person.

## 5. Future work (priority order)

1. Resume Phase 4: extract the Charades dev (63 h) and held-out (17 h) clips, recalibrate, and report FA/h with a narrow CI.
2. Evaluate on fully unseen people and environments (new held-out data). Test-B is now consumed.
3. Improve tracking or re-identification through falls, and handle the URFD-style ADL false triggers with more varied negatives.
4. Update the Streamlit app to the frozen `v6_3_phase3b` model and the multi-person/stitching pipeline.

## 6. Reproduce

```bash
# Final evaluation of the frozen model (sealed splits; already run once)
python scripts/dataset/evaluate_v6.py --models-dir models/v6_3_phase3b --cache-dir datasets/cache/poses_mp --split all_heldout --allow-sealed
```

Phase reports: [V6_RESCORED_BASELINE.md](V6_RESCORED_BASELINE.md), [V6_1_PHASE1_FUNNEL.md](V6_1_PHASE1_FUNNEL.md), [V6_2_PHASE2_REPORT.md](V6_2_PHASE2_REPORT.md), [V6_3_PHASE3_REPORT.md](V6_3_PHASE3_REPORT.md), [V6_4_HNM_REPORT.md](V6_4_HNM_REPORT.md), [V6_5_PHASE4_DEFERRED.md](V6_5_PHASE4_DEFERRED.md).
