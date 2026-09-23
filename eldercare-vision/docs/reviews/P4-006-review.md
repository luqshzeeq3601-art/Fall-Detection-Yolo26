# P4-006 Review — Cache derived keypoints

- **Task:** P4-006 "Cache derived keypoints" (`TASK_SKILL_MATRIX.md`: Ultralytics `yolo-inference`, `yolo-datasets`; Owner: `VISION`; Done when: metadata traceable)
- **Role:** Independent Reviewer
- **Date:** 2026-09-23

## Verdict: APPROVE

**0 Critical, 0 Important, 0 Minor, 0 FYI.**

### 1. Scope and Invariant Analysis
- **Traceable Provenance:** `KeypointCacheMetadata` strictly captures source sample IDs, model checkpoints, framework versions, inference parameters, capture FPS, and extraction timestamps per `DATASET_PLAN.md` §9.
- **Anti-Leakage Safeguard:** Enforces `is_derived=True` and `is_ground_truth=False` at schema initialization and validation boundaries, preventing pseudo-keypoints from being marked or treated as ground-truth labels.
- **Domain Interoperability:** Implemented clean conversions between `CachedKeypointSequence` and core domain models (`TrackObservation`, `TrackedFrame`, `PersonPose`, `Keypoint`), ensuring full compatibility with downstream calibration and evaluation workflows.
- **Robust Storage:** Atomic write operations through temporary file replacement prevent cache file corruption during I/O failures; transparent support for `.json` and compressed `.json.gz` files.
- **Framework Confinement:** The cache layer depends strictly on Python standard library and core internal value objects, maintaining complete CPU safety without framework leakage (`torch`, `ultralytics`, `cv2`).
- **Test Integrity:** 20 unit tests and 1 integration test pass; full test suite reaches 716 items; linter and formatter are 100% clean.
