# V6.4 Experiment: Hard-Negative Mining (negative result)

**Models**: `models/v6_4_hnm`
**Reports**: [V6_4_HNM_FUNNEL.json](V6_4_HNM_FUNNEL.json), [V6_4_HNM_DEV2_EVALUATION.json](V6_4_HNM_DEV2_EVALUATION.json)
**Baseline**: `models/v6_3_phase3b` (Phase 3 + descent low posture)

## Method

`train_v6.py --hard-negative-weight 4` works in two passes:

1. A first grouped-CV pass scores every training window out-of-fold.
2. Normal (label 0) windows with out-of-fold `p_falling >= 0.55` are sampled 4x more often in the final CV and in the final M2.

Everything else is identical to the baseline: v2 features, camera balancing, track stitching, and the same calibration grid.

## Result (out-of-fold Dev at each run's calibrated operating point)

| Metric | Baseline | Hard-negative mining |
|---|---|---|
| Windows marked as hard negatives | n/a | 62 / 25,901 |
| Window-level F1 | 0.735 | 0.765 |
| Min per-camera recall | **90.2%** | 87.8% |
| Precision | **93.7%** | 90.7% |
| URFD false alerts | 14 | 14 |
| cam2 false alerts | **5** | 13 |
| dev_longform FA/h | **0.70** | 0.93 |
| Test-X (dev-2) recall / precision | 87% / 91% | 87% / 95% |

## Conclusion

Hard-negative mining is not adopted. The baseline stays the reference.

- **Why it failed:** too few windows qualify, and window-level gains don't carry over to event-level alerts.
- **URFD false alerts are unchanged:** they come from brief moments in 40 URFD ADL clips that the 1.6 s ADL window stride mostly never samples.
- **What would fix them:** more varied ADL footage (Phase 4), not reweighting the existing clips.
- **Status of the flag:** `--hard-negative-weight` stays available, off by default.
