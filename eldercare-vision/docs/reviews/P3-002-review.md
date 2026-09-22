# P3-002 Review — `TrackObservation` interface (fresh reviewer)

Verdict: **APPROVE**. Zero Critical/Important findings. 2 FYI notes, no fix required.

## 1. Scope and snapshot

- Brief (binding): `docs/task-briefs/P3-002.md` — frozen `TrackObservation`, exact 8 fields,
  two deliberate omissions (`pose_confidence_summary`, `frame_id`), AC-P3-002a..g, forbidden scope.
- Files under review (verified by full read, not by trusting the report):
  - `src/eldercare/vision/tracking/observation.py` (new, 235 lines, read in full)
  - `src/eldercare/vision/tracking/__init__.py` + git diff (read + diff inspected)
  - `tests/unit/test_track_observation.py` (new, 421 lines, read in full)
  - `tests/integration/test_track_observation_sequence.py` (new, 142 lines, read in full)
  - `docs/task-reports/P3-002.md` (treated as unverified claims; every load-bearing claim re-probed)
- Pack references: `ARCHITECTURE.md` §5, `AI_SPEC.md` §5, `TASK_SKILL_MATRIX.md` P3-002 row.
- Base commit: `91d2933` (P3-001). No commit made; no P3-003 started; nothing outside the
  review file was written.

## 2. Fresh verification (exact outputs, reviewer-run)

Python env: `.venv\Scripts\python.exe`, Python 3.10.8, pytest 9.1.1, CPU-only.
Ruff not installed in the project venv (and per instructions nothing was installed/upgraded);
reused the pre-existing isolated binary at `%TEMP%\ruff-p3002\bin\ruff.exe` (no new install).

| Gate | Command (from `eldercare-vision/`) | Result |
|---|---|---|
| Focused pytest | `pytest tests/unit/test_track_observation.py tests/integration/test_track_observation_sequence.py -q` | `28 passed in 0.30s` |
| Full pytest | `pytest -q` | `550 passed in 2.85s` (522 prior + 28 new; arithmetic checks out) |
| Ruff check | `ruff.exe check .` | `All checks passed!` |
| Ruff format | `ruff.exe format --check .` | `127 files already formatted` (ruff 0.16.8) |
| Footprint | `git status --porcelain` + `git diff --name-only` (repo root) | 1 modified tracked file (`tracking/__init__.py`, +6 lines, additive-only — full diff inspected); 5 untracked new files (brief, report, `observation.py`, 2 test files). Zero other modified tracked files. No `tracker.py`/Phase 2/test-file/config modifications. |

FYI (no action): report states `126 files already formatted`; fresh run says `127`.
Both runs pass; the count delta is unexplained but immaterial (likely file-tree timing).
Recorded here for accuracy.

Historical-vs-fresh: the RED→GREEN narrative, command log, and per-criterion verdicts in the
report were NOT taken on faith. All gates above were re-executed fresh by this reviewer, plus
the live probes in §4 (43 assertions, all passing after correcting one probe-side expectation
bug — disclosed below).

## 3. AC-by-AC verdicts

- AC-P3-002a (frozen/typed, exact fields, both omissions documented): **PASS**. Probes confirm
  `dataclasses.fields` order/names exactly
  `[camera_id, track_id, timestamp, bbox_xyxy, detection_confidence, keypoints, image_width, image_height]`,
  `frozen=True`, `frame_id` rejected as unexpected kwarg, no `pose_confidence_summary` attribute,
  both omissions documented in module docstring (`observation.py:22-31`).
- AC-P3-002b (pure/order-preserving/deterministic boundary; zero-person → `()`; `None` explicit): **PASS**.
  Probed: multi-person index order preserved, repeat calls `==`, zero-person → `()`,
  `track_id=None` in → `None` out both end-to-end and by direct construction; positional-call
  correctly rejected (keyword-only `camera_id`/`timestamp`).
- AC-P3-002c (bit-exact preservation): **PASS**. Probed: bbox/detection-conf/dims/camera/timestamp/IDs
  (incl. `2**40`), all-17 confidences bit-exact incl. `0.0`/`1e-12`/`1e-300`/`1.0`
  (re-probe returned `True`; first probe run had a reviewer-side expectation bug — the probe
  replaced index 7 with a missing keypoint but compared against the un-replaced list),
  missing-keypoint semantics (`None` coords, `present=False`, conf `0.0` preserved).
- AC-P3-002d (fail-closed per-field, naming errors, no fabrication/threshold/reorder): **PASS**.
  21 reviewer-chosen malformed cases all rejected with `(TypeError, ValueError)`; error message
  spot-checked to name the field (`track_id` in message for `-3`); non-`TrackedFrame` input
  rejected with `TypeError` naming the expected type.
- AC-P3-002e (zero framework leakage; downstream grouping from observation fields alone): **PASS**.
  See checks (e)/(f) below.
- AC-P3-002f (compactness ≤ 30, no duplicated internals, CPU-only): **PASS**. 25 unit + 3 integration
  = 28 new tests; hand-built fakes, zero sleeps, no GPU/network/downloads; CPU-only confirmed by
  reading both test files in full (numpy use in integration is array scaffolding, not compute).
- AC-P3-002g (ruff + full pytest green, additive-only `__init__`, no dep changes): **PASS**.
  Gates above; `__init__.py` diff is one import block + two `__all__` entries; `pyproject.toml` untouched.

## 4. REVIEWER-CRITICAL checks a–h (with live probes)

a. **Schema vs ARCHITECTURE §5 + omission judgment — SOUND, no finding.**
Field-by-field: `camera_id`→`camera_id`, `track_id`→`track_id`, `timestamp`→`timestamp`,
`bbox`→`bbox_xyxy`, `keypoints[17]`→`keypoints` (reused Phase 2 `Keypoint` verbatim, length pinned
to imported `KEYPOINT_COUNT`), `keypoint_confidence[17]`→`keypoints[i].confidence` (no parallel
array; single-source-of-truth documented at `observation.py:15-18`).
Two additions beyond the §5 sketch — `detection_confidence` and `image_width`/`image_height` —
are explicitly required by the brief, justified (raw-confidence preservation per AI rules;
pixel-coordinate meaning from `TrackedFrame`), and introduce no policy. Both omissions judged
sound: `pose_confidence_summary` has no aggregation policy in any spec and stays computable
downstream from the preserved 17 raw confidences; `frame_id` appears in the §5 *frame*
observation, not the *track* observation, and history is keyed `(camera_id, track_id)` per
AI_SPEC §5. Both are documented in the module docstring with reasons.

b. **17-keypoint/confidence preservation — PASS, no drift risk.**
Bit-exact incl. `0.0`/`1e-12`/`1e-300`, missing passthrough, index order, no `keypoint_confidences`
attribute (parallel-array drift structurally impossible). No threshold/filter/reorder anywhere in
the module (grep for `threshold|filter|reorder` hits only the "no thresholding"/"no filtering"
docstring statements).

c. **Unassigned IDs explicit end-to-end — PASS.** `None` in → `None` out through the converter;
direct construction with `None` accepted; never defaulted (field is required, no default value).

d. **Malformed fail-closed with naming errors — PASS (reviewer's own 21-case sample).**
Bad camera (`123`, `""`), track (`True`, `-1`, `7.0`, `"7"`-class), timestamp (`nan`, `"12.5"`,
negative), bbox (wrong length, `x1>x2`, `nan`, bool coord), confidence (`1.5`, `nan`, `True`),
keypoints (16, 18, dict entries, non-tuple), dims (`0`, `True`, `"640"`), non-`TrackedFrame`,
missing kwargs — all raise `TypeError`/`ValueError`; messages name the offending field
(spot-checked `track_id`, `camera_id`, `timestamp`, bbox/conf/keypoint/dims patterns in tests).

e. **No framework leakage; lazy-import absence — PASS (module has NONE, as required).**
Reviewer AST scan (all import sites incl. function-nested): `observation.py` imports only
`__future__`, `math`, `operator`, `dataclasses`, `typing`, `eldercare.*`; zero function-nested
imports at all. Both test files: no `torch`/`ultralytics`/`cv2` at any nesting level
(integration imports `numpy` for fixture scaffolding only — permitted; brief forbids only
`ultralytics`/`torch`/`cv2`). `sys.modules` delta probe across the conversion path introduced
none of the forbidden modules. (`observation.py` imports `TrackedFrame` from `tracker.py` at
runtime — explicitly permitted reuse-by-import; the `sys.modules` probe proves it pulls no
framework with it.)

f. **Downstream consumability without tracker knowledge — PASS.**
Both grouping blocks (unit `test_consumer_grouping_uses_only_observation_fields`,
integration `_group`) key solely on `(obs.camera_id, obs.track_id)` — the AI_SPEC §5 history key —
and read only `TrackObservation` fields (`timestamp`, `bbox_xyxy` for assertions).
`PoseTracker`/scripted backends appear only as `TrackedFrame` fixture builders, never in the
consumer path. Grouping helpers are test-local; no history logic in `src`.

g. **Scope discipline + duplication judgment — PASS.**
`observation.py` grep hits for history/temporal/velocity/angle/smoothing/fall/FSM/alert/MQTT/export
are docstring-only (contract context + the "what is NOT here" exclusion list, `observation.py:50-52`);
zero implementation of forbidden logic. No `tracker.py`/Phase 2/existing-test/config changes
(footprint table §2). Duplication judgment: new tests pin only the NEW contract + boundary
(schema, per-field rejection, order/bit-exactness/`None`/determinism, framework freedom,
consumer grouping); `Keypoint` invariants, IoU math, backend protocol are used as fixtures, not
re-asserted — the one index-alignment spot-check is within the brief's explicit allowance.

h. **Numeric-string acceptance in `_as_float` — judged ACCEPT (FYI, not a finding).**
`observation.py:100-108` is byte-identical to the Phase 2 adapter's `_as_float`
(`adapter.py:78-86`, verified by read), so `"0.5"` → `0.5` for `detection_confidence`/bbox
mirrors established precedent deliberately, is disclosed in the report's Assumptions, and all
fail-closed properties (bool rejection, NaN/±Inf rejection, `[0,1]` range, ordering) still hold.
Strictness is non-uniform by design, each path mirroring its upstream precedent:
`timestamp` rejects strings (mirrors `pipeline._check_capture_timestamp`, verified
`pipeline.py:87-96`), `track_id`/dims reject strings (mirror `tracker._check_track_id`/
`_check_image_dims`, verified `tracker.py:91-114`), `camera_id` mirrors
`pipeline._check_camera_id` verbatim. Consistency-with-precedent is the right call for a
boundary whose inputs are already-validated value objects; tightening beyond the adapter would
be invented strictness. No fix requested.

## 5. Probes and counts

- Reviewer live-probe script (TEMP, outside repo, deleted after run): 43 assertions —
  42/43 first run, the single FAIL proven to be a probe-side expectation bug and re-probed to
  `True` via a corrected one-liner (`[0.0, 1e-12, 1e-300, 0.5, 1.0]` bit-exact confirmed).
  Effective result: **43/43**.
- New tests: **25 unit + 3 integration = 28 (≤ 30 cap)**; pytest collects exactly 28 focused.
- Full suite: **550 passed** (522 prior unmodified + 28 new).
- Ruff 0.16.8 (isolated): check clean, format clean (127 files).

## 6. Findings

- Critical: **0**.
- Important: **0**.
- Minor: **0**.
- FYI-1: Ruff format file count `127` vs report's `126` — both pass; recorded for accuracy, no action.
- FYI-2: `_as_float` accepts numeric strings for bbox/detection-confidence while
  timestamp/track_id/dims reject them — each mirrors its upstream precedent (see check h);
  judged correct, no action.

No unresolved Critical/Important findings exist, so no scoped fix is prescribed.

## 7. Final verdict

**APPROVE** — P3-002 meets all acceptance criteria AC-P3-002a..g with green gates
(28 focused / 550 full / ruff check + format clean), an additive-only `__init__.py` diff,
exact allowed-file footprint, and sound judgment on both deliberate omissions.
