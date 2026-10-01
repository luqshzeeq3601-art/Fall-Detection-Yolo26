# Phase 4 (Deferred): Charades Longform ADL for False-Alarm Measurement

**Status**: paused 2026-10-01 by decision. The current reference results stay those of `models/v6_3_phase3b` ([V6_3_PHASE3_REPORT.md](V6_3_PHASE3_REPORT.md) §5). The official manifest `datasets/manifests/v6_master_manifest.json` is unchanged; it does **not** include Charades.

## Why it matters

The FA/h gate (≤ 0.05) is the only failing dev gate. The current 0.70 FA/h comes from 3 alerts in 4.3 h, and its 95% CI spans about 0.15–2.0 FA/h. Phase 4 does not change recall; it makes the FA/h estimate defensible and may shift the calibrated thresholds.

## What is ready

| Item | Location |
|---|---|
| Charades videos (16.3 GB) + annotations | `G:/My Drive/charades/Charades_v1_480.zip`, `Charades.zip` |
| Ingest code (`--charades-video-zip`, `--charades-annotations-zip`, `--base-manifest`) | `scripts/dataset/ingest_v6.py` |
| Zip-member video reading and `--max-inference-fps` | `scripts/dataset/extract_pose_cache.py` |
| Per-source FA/h with Poisson CI; unseen groups scored by the final model | `scripts/dataset/calibrate_event_v6_1.py` |
| Manifest with Charades (10,929 records) | `datasets/manifests/phase4_charades/v6_master_manifest_with_charades.json` (+ `.csv`) |
| Fall-mention exclusions (70 clips), probe cache, rejections | `datasets/manifests/phase4_charades/` |
| Partial pose caches (198 / 7,482 dev clips) | `datasets/cache/poses_mp/charades_*.npz` (git-ignored) |

**Charades split** (by subject, salted hash, ~20% of hours held out):

| Split | Clips | Hours | Subjects |
|---|---|---|---|
| `dev_longform` | 7,482 | 63.1 | 212 |
| `longform_adl_heldout` (sealed) | 2,249 | 17.2 | 55 |

**Rejected: 117 clips.** 70 mention a fall, trip, slip or collapse in their script/description, and 47 are byte-identical duplicates under another id.

## To resume

1. Restore the Charades manifest:
   `cp datasets/manifests/phase4_charades/v6_master_manifest_with_charades.* datasets/manifests/` (rename to `v6_master_manifest.*`).
2. Extract dev clips. This takes about 8 h at 8 shards, is CPU/GPU-bound, and resumes from existing caches:
   `python scripts/dataset/extract_pose_cache.py --split dev_longform --cache-dir datasets/cache/poses_mp --max-inference-fps 15 --shard K/8`
3. Recalibrate on the reference model:
   `python scripts/dataset/calibrate_event_v6_1.py --models-dir <copy of models/v6_3_phase3b> --cache-dir datasets/cache/poses_mp --workers 8`
4. Only after freezing a model: extract and evaluate `longform_adl_heldout` together with Test-B (`--allow-sealed`).

## Caveats

- **Licence:** Charades is for non-commercial academic research only.
- **Fall screening is keyword-only:** clips are excluded by script keywords, with no human review.
- **Clip length:** Charades clips are short (~30 s), so FA/h measures short-clip behaviour, not continuous monitoring.
- **Existing vlog footage:** the 4.3 h `dev_longform` vlogs are still single-person caches.
