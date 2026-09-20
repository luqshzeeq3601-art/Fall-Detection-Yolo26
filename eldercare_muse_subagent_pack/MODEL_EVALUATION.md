# Model and Fall-Engine Evaluation Plan

## 1. Evaluation layers

Evaluate separately:

1. pose/inference runtime quality,
2. tracking behavior,
3. temporal fall-event quality,
4. end-to-end system behavior,
5. Agent/VLM enrichment quality.

Do not collapse all failures into "YOLO accuracy".

## 2. Primary fall metrics

From final held-out event/sequence evaluation:

```text
TP = fall correctly detected
FN = fall not detected
FP = non-fall incorrectly alerted
TN = non-fall correctly not alerted
```

Report:

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1
- confusion matrix

## 3. Operational metrics

Also report:

- false alerts/hour,
- time-to-alert from annotated fall onset,
- duplicate incidents per fall,
- incidents with insufficient pose confidence,
- results by activity type,
- results by lighting/occlusion scenario where data permits.

## 4. Portfolio targets

Targets are not pre-existing results:

| Metric | Target |
|---|---:|
| Recall | >= 0.90 |
| Precision | >= 0.85 |
| False alerts/hour | < 1 on controlled non-fall run |
| Duplicate incidents | 0 per continuous fall event |

If the sample size is small, report confidence limitations and raw counts.

## 5. Development protocol

### Stage A — rule bootstrap

- run pretrained `yolo26s-pose.pt`,
- extract track/keypoint histories,
- implement temporal state machine,
- inspect obvious failure cases.

### Stage B — tune on development split

Tune:

- confidence handling,
- analysis window,
- motion thresholds,
- orientation threshold,
- persistence duration,
- cooldown.

### Stage C — freeze

Freeze:

- code commit,
- config version,
- model,
- tracker config,
- split manifest.

### Stage D — final evaluation

Run exactly once per approved final configuration or explicitly document every rerun.

Do not tune from final-test results.

## 6. Cross-dataset evaluation

At minimum:

- main benchmark on designated URFD held-out sequences,
- robustness check on selected UP-Fall RGB sequences,
- local-camera UAT.

A drop across datasets is expected and must be reported, not hidden.

## 7. Tracking evaluation

Qualitative/quantitative checks:

- ID continuity,
- ID switches during overlap,
- track recovery after short occlusion,
- incorrect state inheritance after ID switch.

If tracker behavior creates fall errors, categorize separately.

## 8. Pose failure analysis

Tag failures such as:

- person too small,
- heavy occlusion,
- low light,
- motion blur,
- truncated body,
- person on edge of frame,
- multiple overlapping persons.

## 9. Agent/VLM evaluation

Use a fixed incident set and rubric:

- factual consistency with visible evidence,
- whether uncertainty is acknowledged,
- whether generated text invents unsupported injury/identity claims,
- latency,
- provider failure behavior.

The VLM is never graded as the ground-truth fall detector.

## 10. Required artifacts

Save under `benchmarks/results/<run_id>/`:

- configuration snapshot,
- model/runtime versions,
- dataset manifest hash,
- raw predictions,
- confusion matrix,
- metrics JSON,
- human-readable report,
- hardware info,
- Git commit.
