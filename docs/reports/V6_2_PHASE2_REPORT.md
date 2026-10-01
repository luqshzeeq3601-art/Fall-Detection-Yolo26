# V6.2 Phase 2: Multi-Person Pose Caches and View-Robust Features

**Models**: `models/v6_2_phase2_mp` (M2 skeleton classifier, `feature_set=v2`, camera-balanced sampling, track stitching)
**Pose caches**: `datasets/cache/poses_mp` (multi-person, schema 6.2.0; `dev_longform` still single-person)
**Reports**: [V6_2_PHASE2_MP_FUNNEL.json](V6_2_PHASE2_MP_FUNNEL.json), [V6_2_PHASE2_MP_DEV2_EVALUATION.json](V6_2_PHASE2_MP_DEV2_EVALUATION.json)

## 1. Root cause of the cam2 failure: the wrong person was tracked

`save_keypoint_cache_npz` stored only `persons[0]` for each frame. On UP-Fall cam2, that is usually a seated bystander who is closer to the camera and detected with higher confidence than the subject.

**Evidence** (old cache, fall clips where the tracked hip drops by more than 5% of image height):

| Split | Clips where the tracked person falls |
|---|---|
| cam1 dev | 149/164 |
| cam2 dev | **23/164** |
| cam2 Test-X | **6/60** |

All earlier cam2 and Test-X results therefore measured a bystander, not the fall.

## 2. Changes

1. **NPZ caches store every tracked person**: arrays are (T, P, …) with per-slot track IDs. The loader still reads legacy single-person caches.
2. **Pipeline replay emits observations for every track.** Inference runs per track, as it does in deployment.
3. **`OnlineTrackStitcher`**: when stock ByteTrack gives a falling person a new ID, the new ID inherits a recently lost nearby track (≤1 s, ≤1.5 bbox heights). It uses past frames only, so it can run live. Training and inference share it.
4. **Training labels only the track that falls** (largest hip descent / pre-fall height ≥ 0.15). Bystanders are labelled as negatives. Fall clips with no identifiable falling track are skipped (58/358 dev).
5. **v2 skeleton features** (shared training/inference function), which fixes a train/serve skew in v1:
   - one reference scale per window;
   - hip trajectory and velocity;
   - head-above-hip height;
   - bbox and torso ratios.
6. **Training changes**: camera-balanced sampling, vertical-squash augmentation and keypoint-dropout augmentation.

Subject found after re-extraction (stitched): cam1 dev 144/164, cam2 dev 131/164, Test-A 51/60, Test-X 35/60, URFD 25/30.

## 3. Results (out-of-fold Dev; Test-A/X are burned dev-2 diagnostics)

| Metric | Phase 0 baseline | V6.2 Phase 2 |
|---|---|---|
| Classifier OOF F1 (window) | 0.57 | **0.73** |
| Dev recall cam1 / cam2 / URFD | 71% / 10% / 47% | **99% / 49% / 87%** |
| Dev precision cam1 / cam2 / URFD | 98% / 100% / 56% | 99% / 100% / 70% |
| dev_longform FA/h (OOF) | 4.63 | **0.23** |
| Test-A recall / precision / p95 TTA | 77% / 100% / 1.34 s | **100% [94–100] / 100% / 1.36 s** |
| Test-X recall / precision | 2% / 100% | **30% / 95%** |
| Grid points meeting all gates | 0 | 0 |

Operating point: trigger 0.60, down 0.55, sustain 0.45 s. The trigger and down thresholds sit on the grid edge.

## 4. What still limits cam2 (Phase 3 inputs)

- **Every cam2 fall now triggers** (median peak `p_falling` 0.999). The remaining losses are in the decision stage:
  - 61 falls never confirm low posture within the 2 s transition window;
  - 22 falls don't meet the sustain requirement.
- **Geometric floor posture almost never fires on cam2** (1% of window frames).
- **The cheapest lever is widening the transition window to 3 s**: cam2 recall goes from 49% to 62% at unchanged FA/h (0.23) and precision (100%).
- **Tracking caps cam2 at about 80% of dev falls and 58% of Test-X falls**, because the falling person is never tracked through the fall in the rest.
- **The FA/h gate (≤ 0.05) is still unmet** and can't be proven on 4.3 h of footage. `dev_longform` caches are still single-person.
