# ElderCare Vision — Model Artifact Registry & Retrieval Instructions

This directory contains the frozen, cryptographically verified weights and configurations for ElderCare Vision fall detection models.

## 1. Frozen Model Artifacts & Checksums

| Artifact File | Description | Size (Bytes) | SHA-256 Checksum |
|---|---|---|---|
| `temporal_skeleton_classifier_v5.pt` | V5 1D CNN-GRU Temporal Skeleton Net (PyTorch, 72-dim @ 15 Hz, trained on Dev only) | 651,645 | `c0463a552c7c10ffca9fd15f0e0afa645a4f205f76c1d0b33e416607e8bdc570` |
| `temporal_fall_classifier_v5_m1.joblib` | V5 HistGradientBoostingClassifier Baseline (scikit-learn, 24-dim, trained on Dev only) | 575,941 | `3a64c9e6664fa837c9004a759c293f6b76f7e4810c514c68ef059c47a15781ac` |
| `temporal_fall_classifier_v4.json` | V4 Recurrent GRU Classifier weights (frozen historical) | 35,867 | `c791616840d840742a64fb9465e3d30ae99b6d38fcb93542934720b71e450911` |
| `yolo26s-pose.pt` | YOLO26s Pose Estimation Backbone (17 keypoints) | 24,151,790 | `a083adb42303728ae14c4bd6bd56d80da46f82fb2564dbd6f31dcc92ea321646` |

## 2. Approved Artifact Retrieval Mechanisms

### Option A: Local / Git Checkout
Model weights under 50 MB (`temporal_skeleton_classifier_v5.pt`, `temporal_fall_classifier_v5_m1.joblib`, `temporal_fall_classifier_v4.json`) are committed directly to the repository or managed via Git LFS.

### Option B: Release Artifact Retrieval
For fresh deployments or CI/CD pipelines:
1. Download official release asset bundle `eldercare-vision-models-v5.0.0.tar.gz` from GitHub Releases:
   ```bash
   gh release download v5.0.0 --dir models/ --pattern "*.pt"
   ```
2. Verify integrity:
   ```bash
   python -c "
   import hashlib
   for p, expected in [
       ('models/temporal_skeleton_classifier_v5.pt', 'c0463a552c7c10ffca9fd15f0e0afa645a4f205f76c1d0b33e416607e8bdc570'),
       ('models/temporal_fall_classifier_v5_m1.joblib', '3a64c9e6664fa837c9004a759c293f6b76f7e4810c514c68ef059c47a15781ac'),
   ]:
       actual = hashlib.sha256(open(p, 'rb').read()).hexdigest()
       assert actual == expected, f'Hash mismatch on {p}: {actual} != {expected}'
       print(f'Verified {p}: OK')
   "
   ```

## 3. Cryptographic Freeze Manifests

- **V5 Master Freeze Manifest:** [`models/v5_freeze_manifest.json`](file:///models/v5_freeze_manifest.json)
- **V4 Master Freeze Manifest:** [`models/v4_freeze_manifest.json`](file:///models/v4_freeze_manifest.json)
