# V6.1 Phase 1: Decision-Stage Funnel Diagnostic

**Data**: out-of-fold Dev + dev_longform signals from `models/v6_1_phase0` (no Test split used).
**Operating point**: trigger 0.55, down 0.55, sustain 0.9 s, `require_falling_motion=True`.
**Script**: `scripts/dataset/diagnose_funnel_v6_1.py` → [V6_1_PHASE1_FUNNEL.json](V6_1_PHASE1_FUNNEL.json)

## 1. Where Dev falls are lost (furthest state reached inside the EventMatcher window)

| Camera | Falls | p_falling < trigger | Trigger suppressed | No low posture ≤2 s | Sustain not met | **Alert** |
|---|---|---|---|---|---|---|
| UP-Fall cam1 | 164 | 11 | 0 | 27 | 10 | **116 (71%)** |
| UP-Fall cam2 | 164 | **77 (47%)** | 11 | **57 (35%)** | 3 | **16 (10%)** |
| URFD cam0 | 30 | 1 | 0 | 3 | **12** | **14 (47%)** |

No missed fall had an alert outside the window, so timing isn't the cause.

## 2. Signal differences, cam1 vs cam2 (inside the fall window)

| Signal | cam1 | cam2 |
|---|---|---|
| Median peak `p_falling` | 0.95 | 0.61 |
| Falls with peak `p_fallen` ≥ 0.55 | 91% | 66% |
| Median fraction of frames with geometric floor posture | 0.68 | **0.00** |
| Median fraction of frames where the ADL suppressor fires | 0.06 | **0.42** |
| Median `p_falling` peak offset from annotated fall start | +0.91 s | +1.15 s |

## 3. Single-gate counterfactuals (Dev recall per camera; dev_longform FA/h)

| Variant | cam1 | cam2 | URFD | FA/h |
|---|---|---|---|---|
| Calibrated | 71% | 10% | 47% | 4.6 |
| `require_falling_motion` off | 90% | 11% | 50% | 11.1 |
| Sustain 0.3 s | 71% | 12% | 70% | 5.6 |
| Heuristic suppressor off | 71% | 12% | 53% | 5.8 |
| Floor trust gates off | 72% | 10% | 53% | 10.2 |
| Trigger 0.35 / down 0.35 / transition 3 s (each alone) | 71% | 10% | 47–50% | 5.1–6.5 |
| **All gates relaxed at once** | 98% | **65%** | 87% | **59.1** |

## 4. Conclusions

1. **The classifier is the main cause of the cam2 collapse, not the gating.** 47% of cam2 falls never reach the trigger threshold, and relaxing each gate on its own recovers at most +2 cam2 falls. Even with every gate relaxed, cam2 recall only reaches 65%, at 28% precision and 59 FA/h. The Phase 3 threshold "quick win" hypothesis is rejected.
2. **Geometric floor detection doesn't work on cam2.** The aspect-ratio and torso-angle test almost never fires, because many cam2 falls happen along the camera axis (foreshortened). Low posture then depends only on `p_fallen`, which is also weaker on cam2. This accounts for the 57 falls with no low posture.
3. **The ADL suppressor fires on 42% of cam2 fall frames**, but it's a secondary factor (11 suppressed triggers).
4. **Annotation alignment is fine.** The cam2 peak lags cam1 by about 0.2 s, well inside the 1 s early / 3 s late tolerance.
5. **URFD misses are mostly sustain failures.** URFD clips end about 1.5 s after lying starts, so the 0.9 s sustain requirement runs into the end of the clip. At sustain 0.3 s, URFD recall rises to 70%.
6. **cam1 misses are concentrated** in backward and kneeling-forward falls (no low posture) and sideways falls (below trigger).

## 5. Implication for the plan

Phase 2 (making the model and its features robust to camera view) is now the critical path, not Phase 3.

- **Model and features:**
  - replace bounding-box aspect-ratio geometry with body-normalized vertical descent (hip and head drop relative to torso length);
  - train a cam2-aware model using camera-balanced batches and view augmentation.
- **Decision stage (after Phase 2):**
  - let low posture come from `p_fallen` **or** normalized descent;
  - review which suppressor rules fire on cam2;
  - revisit the sustain time, since clip length truncates it on URFD.
