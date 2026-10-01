# Models

## Current model: V6.3 (`v6_3_phase3b/`)

The production fall classifier is frozen in [`v6_3_phase3b/`](v6_3_phase3b). The Streamlit demo and the final sealed evaluation both use it.

| File | Contents |
|---|---|
| `temporal_skeleton_classifier_v6.pt` | M2 per-track 1D CNN-GRU over 2 s windows of v2 skeleton features (PyTorch, 0.7 MB) |
| `temporal_fall_classifier_v6_m1.joblib` | M1 gradient-boosted baseline on hand-crafted temporal features |
| `v6_training_report.json` | Training settings, out-of-fold metrics and the calibrated operating point |
| `v6_calibration_grid.json` | Full threshold sweep used for calibration |
| `v6_1_folds/` | Grouped CV fold assignment and out-of-fold signal statistics |
| `freeze_manifest.json` | SHA-256 of every frozen artifact, the operating point and the final-evaluation plan |

Operating point: kinetic trigger `p_falling ≥ 0.55`, low posture `p_fallen ≥ 0.55` or body-normalised descent, sustained for 0.45 s within a 3 s window. Results are in [`docs/reports/V6_FINAL_RESULTS.md`](../docs/reports/V6_FINAL_RESULTS.md).

## Pose backbone

`yolo26s-pose.pt` (Ultralytics, 17 COCO keypoints) isn't committed. Ultralytics downloads it on first use:

```bash
uv run python -c "from ultralytics import YOLO; YOLO('yolo26s-pose.pt')"
```

`scripts/export_tensorrt_fp16.py` exports it to ONNX and a TensorRT FP16 engine for GPU deployment. Exported `.onnx` and `.engine` files are git-ignored.

## Development phases

Each V6 phase folder holds the same report set as the frozen model, so the progression can be compared. The demo's Results page reads them.

| Folder | Phase |
|---|---|
| `v6_1_phase0/` | Leak-free evaluation baseline |
| `v6_2_phase2/`, `v6_2_phase2_mp/` | Multi-person pose caches and track stitching |
| `v6_3_phase3/` | Track handover fix and worst-camera calibration |
| `v6_3_phase3b/` | **Frozen V6.3**: adds body-normalised descent |
| `v6_4_hnm/` | Hard-negative mining experiment (not adopted) |

Files at this folder's top level (`*_v2`–`*_v5`, `v4_freeze_manifest.json`, `v5_*`, `v6_*`) are earlier model generations. They're kept because their freeze manifests and regression tests reference them.

## Verifying integrity

Frozen files are stored byte-for-byte (see `/.gitattributes`), so their hashes match the manifests on any OS:

```bash
uv run python -c "import hashlib, json; m = json.load(open('models/v6_3_phase3b/freeze_manifest.json')); [print(p, 'OK' if hashlib.sha256(open(p, 'rb').read()).hexdigest() == a['sha256'] else 'MISMATCH') for p, a in m['artifacts'].items()]"
```

One file reports `MISMATCH` on purpose. After the freeze, `src/eldercare/fall_engine/pipeline_v6_1.py` gained a helper, `pipeline_config_from_calibration`, so the demo app can build its config from the training report (commit `596bd11`). The change only adds code; the frozen decision logic is unchanged. You can confirm with `git diff dbd5756 HEAD -M -- eldercare-vision/src/eldercare/fall_engine/pipeline_v6_1.py src/eldercare/fall_engine/pipeline_v6_1.py`.

The out-of-fold signal caches (`v6_1_folds/oof_signals.pkl`, 40–76 MB each) are git-ignored. `scripts/dataset/train_v6.py` regenerates them.
