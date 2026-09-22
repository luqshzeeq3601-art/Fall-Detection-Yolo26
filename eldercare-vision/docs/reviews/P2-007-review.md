# P2-007 Review — Official-API review and Phase 2 gate (fresh reviewer)

- Task: P2-007 "Official-API review and Phase 2 gate" (brief `docs/task-briefs/P2-007.md`, AC-P2-007a..g).
- Reviewer role: fresh VISION/API reviewer, no prior implementation context. All implementer reports treated as CLAIMS, verified against actual files.
- Date (UTC): 2026-09-22.
- Snapshot: outer repo HEAD `d69033252c39186ab54a50efe05926decd335a89`, tree clean except the coordinator's untracked `docs/task-briefs/P2-007.md` (`git status --short` shows only that file; `git diff --stat` / `--name-only` empty).
- Scope reviewed (full reads): `src/eldercare/vision/pose/adapter.py` (378 lines), `inference.py` (103), `pipeline.py` (298), `timing.py` (121), `scripts/dev/verify_pose_model.py` (180, read-only, never executed), `docs/environment/P2-001-environment.md`, `docs/task-reports/P2-002.md` (§3 acceptance record), P2-003/P2-004/P2-005/P2-006 reports, `docs/reviews/P2-004-review.md`, `P2-005-review.md`, `P2-006-review.md` (open ledger), pack `AI_SPEC.md` §§2–6, `CONSTRAINTS.md` §§2/5/8, `ACCEPTANCE_CRITERIA.md` §§2–3, `.gitignore`.
- Only file written by this review: this one. No `src/`/`tests/`/`scripts/`/config edit; no commit; no Phase 3 start; no pip install of heavy deps; no weight download.

## Verdict: APPROVE

0 Critical, 0 Important, 1 Minor (new, non-blocking), 3 FYI (1 new, 2 carried). Every Ultralytics-facing assumption traces to recorded installed-package source (ultralytics 8.4.142, P2-001/P2-002 evidence chain) or to duck-typed defensive code that needs no version pin; zero UNSUPPORTED assumptions remain. All gates freshly green. CUDA/model verification NOT EXECUTED with concrete reason (see §5). All P2-006 carryovers re-judged still non-material at the Phase 2 boundary.

## 1. Verification performed

### 1a. Freshly executed by this reviewer (from `eldercare-vision/`, project venv Python 3.10.8)

| # | Command | Observed result |
|---|---|---|
| 1 | `git rev-parse HEAD` / `git status --short` / `git diff --stat` | `d690332` / only `?? docs/task-briefs/P2-007.md` / empty |
| 2 | `pytest tests/unit/test_pose_adapter.py -q -p no:cacheprovider` | `38 passed in 0.23s` |
| 3 | `pytest tests/unit/test_pose_pipeline.py -q -p no:cacheprovider` | `50 passed in 0.30s` |
| 4 | `pytest tests/unit/test_pose_timing.py -q -p no:cacheprovider` | `75 passed in 0.40s` |
| 5 | `pytest tests/integration/test_pose_pipeline.py -q -p no:cacheprovider` | `3 passed in 0.19s` |
| 6 | `pytest tests/ai_regression/test_pose_regression.py -q -p no:cacheprovider` | `23 passed in 0.57s` |
| 7 | `pytest -q -p no:cacheprovider` (full) | `492 passed in 2.16s` (469 prior + 23 new; reconciles with P2-006 re-review) |
| 8 | `pip install --target <temp>/ruff-isolated ruff` (isolated, per brief) | `ruff-0.16.8` installed to temp dir only; venv untouched |
| 9 | `python -m ruff --version` (with `PYTHONPATH=<temp>/ruff-isolated`) | `ruff 0.16.8` |
| 10 | `python -m ruff check . --no-cache` | `All checks passed!` |
| 11 | `python -m ruff format --check . --no-cache` | `114 files already formatted` |
| 12 | `find_spec(torch/ultralytics/cv2)` in venv | `torch None`, `ultralytics None`, `cv2 present` (headless, expected) |
| 13 | `nvidia-smi` | not found on this machine (no GPU tooling here) |
| 14 | `%APPDATA%\Ultralytics` / `~/.cache/ultralytics` scan | only `settings.json` (2026-08-09); no cached `*.pt` anywhere checked |
| 15 | `git ls-files \| Select-String '\.pt$'` + `Get-ChildItem -Recurse -Filter '*.pt'` | both empty: no weights in repo |
| 16 | `git check-ignore -v yolo26s-pose.pt` | `eldercare-vision/.gitignore:33:*.pt` (ignored by existing rule, untouched) |
| 17 | `Get-ChildItem -Recurse -Filter 'bus.jpg'` | empty: no image in repo |
| 18 | Import sweep: `Select-String` over pose files for `ultralytics/torch/cv2` code imports | only `inference.py:86` lazy `from ultralytics import YOLO` (+ docstring prose); repo-wide code-import sweep hits only that line + pre-existing `stream/capture.py:52 import cv2`; zero `torch` imports in `src/` |
| 19 | Import-line dump per pose file | adapter: `math/operator/dataclasses/typing` only; pipeline: stdlib + `numpy` + first-party only; timing: `math/dataclasses` only; inference top: `__future__/typing` only |
| 20 | `pyproject.toml` dep grep | `pydantic/pydantic-settings/opencv-python-headless/numpy` only; no ultralytics/torch |
| 21 | Instantiate `UltralyticsPosePredictor()` in venv (no predict call) | `UltralyticsPosePredictor(model_name='yolo26s-pose.pt', device=0, imgsz=640)`; `cv2/torch/ultralytics` all absent from `sys.modules` after import |
| 22 | `pytest --version` / `numpy` | `pytest 9.1.1`, `numpy 2.2.6` |
| 23 | Regression-file audit: `^def test_` count, `_imported_roots`/`ast.walk`, `_is_monotonic`, `images[0] is frame.image`, fresh-interpreter script | 23 tests; AST scanner + self-check + non-monotone fixture guard + handoff identity assert all present |

Ruff note: venv lacks ruff, system has none; per brief used isolated `--target` install (ruff 0.16.8 vs historical 0.16.6 — tool-only drift, no code impact). `114 files` vs historical `111/112/113` is untracked-file count drift (this review file + brief); all clean.

### 1b. Historical evidence NOT re-executed (claims from P2-001/P2-002, accepted as recorded evidence)

- P2-001 (2026-09-20, Python 3.10.11, torch 2.5.1+cu121, ultralytics 8.4.142, RTX 3070, CUDA proven): `cfg/models/26/` listing incl. `yolo26-pose.yaml` (`kpt_shape: [17, 3]`, `s` scale, `Pose26` head), task-registry YOLO26-pose entries, CUDA smoke transcript, TensorRT-absent non-blocker. This reviewer could not re-probe any of it here (no torch/ultralytics/GPU on this machine); versions recorded as stated.
- P2-002 (2026-09-20): installed-source citations (`YOLO.__init__`, `Model.predict` signature, `Keypoints` layout, `Model.device` semantics, `attempt_download_asset` weights resolution, `ASSETS_URL`), final green transcript (`yolo26s-pose.pt`, `model_task: pose`, `cuda:0` keypoint device, 4 persons, `(4,17,2)`/`(4,17)`, `orig_shape_hw: (1080,810)`, `RESULT: PASS`), weights sha256 + outside-repo cache path, hygiene proof. Live re-run NOT EXECUTED here (see §5).
- P2-003/004/005 RED→GREEN logs and P2-006 RED probe + fix-loop mutation tables: not re-executable (probe edits gone); corroborated by fresh green counts + line-reference spot checks (all cited `adapter.py`/`pipeline.py`/`timing.py`/`inference.py` lines verified to hold in HEAD).

## 2. Official/runtime API findings (assumption → evidence → verdict)

Environment constraint: `torch`/`ultralytics` are NOT importable in this venv (`find_spec` → `None` for both), there is no CUDA tooling and no cached `*.pt`. Therefore no installed-package source could be re-probed live. Every verdict below grounds in the P2-001/P2-002 recorded installed-source evidence (ultralytics **8.4.142**) plus the defensive shape of the code itself. No verdict relies on memory alone.

| # | Assumption (where used) | Evidence | Verdict |
|---|---|---|---|
| A1 | `from ultralytics import YOLO`; `YOLO("yolo26s-pose.pt")` bare-name construction (`inference.py:86-89`, `verify_pose_model.py:119-121`) | P2-002 §1: `YOLO.__init__(self, model="yolo26n.pt", task=None, verbose=False)` in `ultralytics/models/yolo/model.py`, `YOLO.__module__ == "ultralytics.models.yolo.model"`; bare `"yolo26s-pose.pt"` is the documented usage pattern. P2-001 §2-Area 10: `yolo26s-pose.pt` is an official checkpoint (docs `models/yolo26`, `tasks/pose`). | SUPPORTED (ultralytics 8.4.142, recorded) |
| A2 | `model.predict(source=..., device=0, imgsz=640, verbose=False)` kwargs pass through (`inference.py:90-92`, `verify_pose_model.py:127`) | P2-002 §1: `Model.predict(self, source=None, stream=False, predictor=None, **kwargs)` (`ultralytics/engine/model.py`); `device`/`imgsz`/`verbose` pass through `**kwargs` into predictor cfg merge; config key is `device`, default `imgsz` 640 (`ultralytics/cfg`, `DEFAULT_CFG_DICT`). | SUPPORTED (8.4.142, recorded). Forwarding itself unpinned by suites → explicit I04 verdict below (unpinned, non-material) |
| A3 | `device=0` means `cuda:0` at inference (`inference.py:50,90`) | P2-002 §3 transcript: `predict(device=0)` → asserted `keypoints_device: cuda:0` (script asserts exact `f"cuda:{args.device}"`, lines 170-173). `CONSTRAINTS §2 device: 0`. | SUPPORTED (8.4.142 + measured record) |
| A4 | `predict` returns a list; `results[0]` is the single `Results` (`inference.py:90-97`, `verify_pose_model.py:127-128`); empty list fails closed | `verify_pose_model.py:127-128` + P2-002 PASS transcript exercised exactly this; `inference.py:93-96` raises `ValueError` on empty. List-of-`Results` return is the `Model.predict` contract cited in P2-002 §1. | SUPPORTED (8.4.142, recorded + exercised in P2-002 run) |
| A5 | `len(results)` == person count (`verify_pose_model.py:130`) | P2-002 §3: `person_count: 4` via `len(r)` on the `bus.jpg` record; `Results.__len__` is the detection-count protocol. | SUPPORTED (8.4.142, recorded) |
| A6 | `results.keypoints is None` ⇔ no detections (`adapter.py:285-286`, `verify_pose_model.py:144-147,160-161`) | P2-002 §1: `Keypoints.conf` is `None` when no visibility dim; P2-002 §3 hard-fails on `kpts is None` for the positive image; adapter zero-person contract (`keypoints is None → persons == ()`) pinned by 0-person tests (38/50/75/23 suites green). Absence-shape, not version-sensitive syntax. | SUPPORTED (8.4.142, recorded + contract-tested) |
| A7 | `results.keypoints.xy` is `(N, 17, 2)` pixel coords (`adapter.py:288-290,297,334-342`) | P2-002 §1: `Keypoints(BaseTensor).xy → (N, K, 2)` pixel coords (`ultralytics/engine/results.py`); P2-002 §3 measured `(4, 17, 2)`. Adapter enforces inner-17 per person (`adapter.py:337-342`) and is shape-tested incl. 16/18 fail-closed. | SUPPORTED (8.4.142, recorded + measured) |
| A8 | `results.keypoints.conf` is `(N, 17)` when present (`adapter.py:291-296,298`) | P2-002 §1: `.conf → (N, K)` when `has_visible` (last dim == 3), else `None`; P2-002 §3 measured `(4, 17)`. Adapter treats `None`/missing as fail-closed `ValueError` (defensive; `yolo26s-pose.pt` always emits conf per P2-002). | SUPPORTED (8.4.142, recorded + measured) |
| A9 | `results.boxes.xyxy` is `(N, 4)` pixel boxes; `results.boxes.conf` is `(N,)` detection confidences (`adapter.py:314-325`) | P2-002 §3 measured `boxes_shape: (4, 6)` via `r.boxes.data` (the stacked `xyxy+conf+cls` tensor), consistent with per-row 4-box + scalar-conf views; `Boxes.xyxy`/`Boxes.conf` are the standard `Boxes(BaseTensor)` views in `ultralytics/engine/results.py` (same file family as the cited `Keypoints` class). Adapter additionally tolerates `(N,1)` conf nesting (`_as_confidence_list`) and fails closed on count mismatch. No live re-probe possible here; duck-typed reads degrade to naming `ValueError`s, never silent misreads. | SUPPORTED (8.4.142, recorded family + measured `boxes.data (4,6)`; defensive reads) |
| A10 | `results.orig_shape` is `(h, w)` ints (`adapter.py:101-121,280`, `verify_pose_model.py:140`, `pipeline.py:224-233`) | P2-002 §3 measured `orig_shape_hw: (1080, 810)`; adapter parses `(h,w)→(w,h)` via `operator.index` (positive-int enforced); pipeline cross-checks parsed dims against `image.shape[0:2]`; two non-square shapes pinned (`(1080,810)→(810,1080)`, `(480,640)→(640,480)`), so a swap cannot hide. | SUPPORTED (8.4.142, recorded + measured + double-shape tested) |
| A11 | `keypoints.data.device` is the inference device (`cuda:0`) while `model.device` may report `cpu` (`verify_pose_model.py:151,170-173`, lines 136-138) | P2-002 §1: `Model.device` returns `next(self.model.parameters()).device` (allocation site after `map_location="cpu"` load), NOT the inference device; P2-002 §3 transcript shows `model_device: cpu` alongside asserted `keypoints_device: cuda:0`. `Keypoints.data` is a `torch.Tensor` carrying `.device` (P2-002 §1). | SUPPORTED (8.4.142, recorded + measured) |
| A12 | `YOLO` checkpoint introspection: `model.ckpt_path` basename == `yolo26s-pose.pt`, `model.task == "pose"` (verify script only, lines 123-125, 136) | P2-002 §3 transcript prints both (`model_name`, `model_task: pose`, `weights_cache_path`); script hard-fails on basename mismatch. Never touched by production code. | SUPPORTED (8.4.142, recorded; script-only) |
| A13 | `.tolist()` materialization covers torch Tensors, numpy arrays, nested lists (`adapter.py:89-98,241-262`); `len()`/`.shape` duck-typing in script (lines 152-153, 163-169) | `tolist()` is stable std API on both `torch.Tensor` and `ndarray`; adapter falls back to plain sequences when absent; `TorchLikeTensor` fakes + list-only stubs pinned in unit suites. Not version-sensitive. | SUPPORTED (framework-stable API + tested fakes) |

UNSUPPORTED assumptions: **none**. Zero findings in this table.

**Explicit I04 verdict** (brief item 2 requires it): `UltralyticsPosePredictor.predict()` kwarg forwarding (`source/image`, `device=self._device`, `imgsz=self._imgsz`, `verbose=False`, `inference.py:90-92`) is exercised by **no suite** — instantiating the class only validates/stores args (constructor never imports ultralytics), and calling `predict` needs the real package + weights + CUDA, which CPU CI never has. Recorded as **explicitly unpinned** (matches P2-006 FYI-R3/I04). Still non-material at the Phase 2 boundary because: (a) defaults ARE pinned (`model_name/device/imgsz` mutation-killed by the regression predictor-defaults test, I01–I03); (b) the exact call pattern is byte-identical to the P2-002 measured record (`verify_pose_model.py:127` vs `inference.py:90-92`); (c) pinning it would require injecting a fake `ultralytics` module, outside every Phase 2 brief's scope. Carried as FYI, not a finding against the gate.

## 3. AC-by-AC verdicts (AC-P2-007a..g)

| AC | Verdict | Basis |
|---|---|---|
| AC-P2-007a: every Ultralytics-facing attribute/kwarg/device assumption traced; zero unsupported | PASS | Table §2: 13/13 SUPPORTED (8.4.142 recorded evidence + measured P2-002 transcript + defensive code shape); 0 UNSUPPORTED. Live re-probe impossible here — explicitly recorded, not hidden (§5) |
| AC-P2-007b: full contract re-verified end-to-end (13 items) | PASS | Checklist §4: 13/13 PASS on fresh code reads + green suites |
| AC-P2-007c: all P2-006 carryovers re-judged | PASS | §6: Minor-1, Minor-A, FYI-R1, FYI-R2, FYI-R3/I04, P06 each re-judged still non-material with reason |
| AC-P2-007d: gates green, freshly executed in project venv | PASS | §1a rows 2-7, 10-11: 38 + 50 + 75 + 3 + 23 focused, 492 full, `ruff check` + `ruff format --check` clean (ruff 0.16.8 isolated; pytest 9.1.1; Python 3.10.8) |
| AC-P2-007e: CUDA/model verification executed or not-executed with reason; no new downloads/training | PASS (not-executed path) | §5: NOT EXECUTED — no torch/ultralytics importable, no CUDA tooling, no cached weights, no local image; zero installs of heavy deps, zero downloads, zero weight writes |
| AC-P2-007f: review file exists; zero unresolved Critical/Important; fix loop if triggered | PASS | This file; 0 Critical / 0 Important; no fix loop triggered (nothing to fix) |
| AC-P2-007g: PROGRESS/commit bookkeeping | N/A for reviewer | Coordinator owns `PROGRESS.md` + commits per brief §Files-allowed; reviewer wrote only this file and made no commit |

## 4. Full-contract checklist (brief items 1–13)

1. **Model identity** — PASS. Production default exactly `yolo26s-pose.pt` (`inference.py:49`, verified live: `model_name='yolo26s-pose.pt'`); fallback `yolo26n-pose.pt` untouched (no reference in `src/` besides docs); verify script `MODEL_NAME = "yolo26s-pose.pt"` (`verify_pose_model.py:30`) with basename hard-assert (lines 123-125). Matches CONSTRAINTS §2 / AI_SPEC §2 / AC-010.
2. **Defaults + kwarg forwarding** — PASS (with explicit I04 record). Defaults `model_name="yolo26s-pose.pt"`, `device=0`, `imgsz=640` (`inference.py:47-62`) match CONSTRAINTS §2 + P2-002 record; regression test pins all three (I01–I03 killed). Forwarding pattern matches the P2-002 measured call; unpinned-by-suites recorded as unpinned per §2/I04 — brief allows "actually exercised or explicitly recorded as unpinned".
3. **Shapes + COCO order** — PASS. `(N,17,2)`/`(N,17)` measured in P2-002 `(4,17,2)`/`(4,17)`; adapter enforces 17-per-person on both xy and conf rows (`adapter.py:337-348`); `KEYPOINT_NAMES` full-tuple equality pinned (`adapter.py:51-69` vs regression `:199-202`); `KEYPOINT_COUNT=18`/name-swap mutants killed (A01/A02 per P2-006 review).
4. **0/N-person, alignment, order** — PASS. `keypoints is None → persons == ()` (`adapter.py:285-286`); empty-rows → `()` (`:308-309`); boxes/person count mismatch fails closed (`:326-331`); index-aligned loop preserves order (`:333-377`); permuted non-monotone 4P fixture + `_is_monotonic` guard verified present (`test_pose_regression.py:188-211,287-313`); x1/area sorts killed (A12b/A12d per P2-006 re-review).
5. **Confidence preservation, no hidden thresholding** — PASS. Bit-for-bit `==` incl. exact `0.0`/`1e-6`/`2.5e-6` (adapter `:356`, regression `:225/:238/:274/:289-304`); floor/round/threshold/float32 mutants killed (A04a/A04b/A05/A13/A15/A17). Only defect class is non-measurement NaN/Inf conf → `ValueError` (fail-closed, documented).
6. **NaN/Inf missingness, no fabrication** — PASS. Non-finite x or y → `(None, None, conf, present=False)`, conf preserved (`adapter.py:357-360`); NaN-only/Inf-kept/x-only/y-only/fabrication mutants killed (A06/A07/A08/A09). `Keypoint` invariant `present ⟺ both-set` enforced (`adapter.py:139-166`).
7. **`orig_shape` (h,w)→(w,h)** — PASS. Parser (`adapter.py:101-121`) + pipeline cross-check naming both shapes (`pipeline.py:224-233`); two non-square shapes pinned; h-to-w-swap mutant killed (A03). P06 (cross-check unit-owned) re-judged §6.
8. **Leakage-free domain objects** — PASS. `PoseFrame`/`PersonPose`/`Keypoint` are frozen dataclasses of plain floats/strings/bools (`adapter.py:124-238`); adapter imports stdlib only (§1a row 19); `ultralytics` imported lazily inside `predict` only (`inference.py:86`); live probe: constructing the predictor imports no forbidden module (§1a row 21).
9. **CUDA/model isolation; CPU CI clean** — PASS. Only `inference.py` mentions ultralytics (lazy); no `torch` import anywhere in `src/`; no `cv2` outside pre-existing `stream/capture.py:52`; `pipeline.py`/`timing.py` stdlib+numpy only; `pyproject.toml` has no ultralytics/torch; regression fresh-interpreter + AST-scan guards verified present (§1a row 23).
10. **Timing non-interference** — PASS. Stamps only around predict+adapt (`pipeline.py:212-223`); `timings_from_stamps` pure (`timing.py:91-121`); default-vs-programmed pose/identity equality + timer-dependent-drop mutant killed (P03) per P2-006 review; 75 timing tests green fresh.
11. **Regression protection** — PASS. 23-test cross-module layer present and green; focused layers 38/50/75/3 green; full 492 green; P2-006 mutation evidence (both Important findings resolved, verified by re-review kills) stands — no `src/` drift since (`git diff --stat -- src` empty at P2-006 re-review; `git diff --stat` empty now).
12. **CPU-safe CI + weights outside Git** — PASS. No sleep/network/GPU in pose modules or regression file (sweeps clean; regression file imports stdlib+numpy+pytest+eldercare only); `verify_pose_model.py` never collected (`--collect-only` proof in P2-006 review, file still outside `tests/`); `*.pt` ignored (`.gitignore:33`), zero `.pt` tracked, zero on filesystem, zero `bus.jpg` in repo (§1a rows 15-17).
13. **P2-006 carryovers re-judged** — PASS (all still non-material). See §6.

## 5. CUDA/model verification (verify_pose_model.py): NOT EXECUTED with reason

- `torch`: `find_spec` → `None` (not installed in this venv).
- `ultralytics`: `find_spec` → `None` (not installed in this venv).
- CUDA tooling: `nvidia-smi` not recognized on this machine.
- Cached weights: `%APPDATA%\Ultralytics` holds only `settings.json`; `~/.cache/ultralytics` absent; no `*.pt` found repo-wide on filesystem; no local `--image` candidate exists in repo (no `bus.jpg`).
- Action taken: none — per brief, never pip-install heavy deps or download weights to satisfy the gate. Script was read (not run); its call pattern matches `inference.py` (§2/A2). No training, no downloads, no new files introduced by this review except this file.

## 6. Carryover re-judgment (P2-006 ledger at the Phase 2 boundary)

| Carryover | Re-judgment | Reason |
|---|---|---|
| Minor-1 (overlap with existing suites; brief-mandated) | Still non-material | Unchanged by design: 23 ≤ 30 tests; overlap is inherent to the regression-pinning brief (areas 1,3,6,7,8 prescribe the checks); several repeats add a new dimension (golden 4P, Inf, tiny values, second shape). Policy call, not a defect. No action. |
| Minor-A (person order not pinned against keypoint-derived sort keys, A12m/A12n) | Still non-material | An adapter whose contract is verbatim pass-through has no plausible reason to sort by keypoint statistics; every box/detection-confidence key (both directions + width + centre-x) is killed; fixtures are brief-mandated `arange`/`linspace`. Optional hardening only (permute xy/conf rows). No action. |
| FYI-R1 (non-literal dynamic imports on unexecuted paths survive: F12/F17) | Still non-material | Documented limit of both guards (AST cannot resolve non-literals; child does not execute those paths); limits stated in the regression module docstring. Non-literal imports on executed paths ARE caught (F11/F18). A hidden cv2 import in dead code changes no runtime behavior. No action. |
| FYI-R2 (`parents[2]/"src"` path trust in fresh-interpreter test) | Still non-material | False-confidence probe (TM5) analyzed in P2-006 re-review: committed path derivation matches the tree under test; without an editable install a wrong path fails loudly (`ImportError`, returncode asserted). No action. |
| FYI-R3/I04 (`predict()` kwarg forwarding unpinned) | Still non-material | Explicit I04 verdict in §2: unpinned, recorded, out of every Phase 2 brief's scope; defaults pinned + call pattern matches measured record. No action. |
| P06 (`orig_shape` cross-check protected only by existing unit tests) | Still non-material | Two existing unit tests (`test_process_frame_orig_shape_mismatch_*`) kill the mutant; the regression layer's spot-check role is brief-limited and its contract holds (adapter still fails closed independently). Cross-phase ownership is legitimate layering. No action. |

No carryover became material. Nothing was promoted to Important/Critical.

## 7. Findings

### Critical

None.

### Important

None.

### Minor

- **Minor-P2-007-1 (new, non-blocking): official-docs side of "installed source first, docs second" could not be re-fetched live.** All Ultralytics citations rest on the P2-001/P2-002 recorded evidence (live on 2026-09-20, version-pinned 8.4.142) rather than a fresh package read or docs re-fetch from this machine (no ultralytics installed, no network fetch performed for the gate). Accepted because: versions are recorded, the measured transcript (shapes/device/task) is the stable contract, and the code reads defensively (duck-typed + fail-closed). Recommendation (Phase 9 / next CUDA-bearing task, not a gate condition): re-probe `ultralytics/engine/results.py` (`Keypoints`/`Boxes`) and re-run `verify_pose_model.py` on a CUDA machine and append the transcript.

### FYI

- **FYI-P2-007-1 (new): tool/count drift only.** Ruff 0.16.8 (isolated) vs 0.16.6 historical; `ruff format --check` 114 files vs 111/112/113 historical (untracked brief + this review); full suite 2.16s vs 0.86–2.04s historical. All green; no semantic meaning.
- **FYI-P2-007-2 (carried): two OpenCV distributions coexisted at P2-001** (`opencv-python 4.9.0.80` + `opencv-python-headless 5.0.0.93`); irrelevant to Phase 2 (inference decodes via Ultralytics' loader; `orig_shape (1080,810)` confirms decode). This venv resolves `cv2` (headless). No action.
- **FYI-P2-007-3 (carried): `model.device == cpu` vs keypoint tensor `cuda:0`** is expected per `Model.device` source (allocation site), not a defect; CUDA execution is proven by the asserted keypoint tensor device (P2-002 record). Restated so Phase 3+ readers do not "fix" it.

## 8. Counts

- Fresh gates: adapter 38/38; pipeline unit 50/50; timing 75/75; integration 3/3; regression 23/23; full 492/492; `ruff check` clean; `ruff format --check` clean (114 files).
- API assumptions: 13 SUPPORTED, 0 UNSUPPORTED.
- AC-P2-007: a PASS, b PASS, c PASS, d PASS, e PASS (not-executed path), f PASS, g N/A (coordinator-owned).
- Contract items 1–13: 13 PASS.
- Carryovers: 6 re-judged, 0 promoted.
- Findings: Critical 0, Important 0, Minor 1 (new, non-blocking), FYI 3 (1 new + 2 carried).
- Fix loop: not triggered (no Critical/Important). No `src/`/`tests/` change needed or made.
- `verify_pose_model.py`: NOT EXECUTED (no torch/ultralytics, no CUDA tooling, no cached weights — each checked and stated).

**Final: APPROVE.** Phase 2 rests on no unsupported Ultralytics/PyTorch API assumptions within what a CPU-only gate can verify; the CUDA-live remainder is explicitly recorded (§5) and is the only residual, owned by the next CUDA-bearing task (re-probe + script re-run), not by this gate.
