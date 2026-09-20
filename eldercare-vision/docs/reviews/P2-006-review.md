# P2-006 Review — Pose regression tests (fresh reviewer)

- Task: P2-006 "Pose regression tests" (TEST-ONLY; brief `docs/task-briefs/P2-006.md`, AC-P2-006a..g).
- Reviewer role: fresh, independent Reviewer (no prior implementation context; the implementer report was treated as a CLAIM, not evidence).
- Date: 2026-09-21
- Snapshot: outer repo HEAD `7204021` (working tree clean before and after this review; imported snapshot, so old inner-repo SHAs do not exist and that is not a defect).
- Scope reviewed: `tests/ai_regression/test_pose_regression.py` (474 lines, 21 tests) against the production modules it pins (`src/eldercare/vision/pose/{adapter,pipeline,timing,inference}.py`), `scripts/dev/verify_pose_model.py` (read only, never executed), the four existing pose suites, the P2-004 / P2-005 reviews, and `docs/task-reports/P2-006.md`.
- Only file written by this review: this one. No `src/`, `tests/`, pack, or `PROGRESS.md` edit; no git add/commit; no install; no network; `verify_pose_model.py` not run. Mutation work was done on a throwaway copy under the session scratchpad, which was deleted afterwards.

## Verdict: NOT APPROVE

> **Superseded:** this is the first-pass verdict, kept as history. After the fix loop, the scoped `## Re-review` at the end of this file issued **Re-review verdict: APPROVE** (0 Critical, 0 Important).

0 Critical, 2 Important, 3 Minor, 6 FYI. Everything the report claims as green reproduces (21/21 new, 490/490 full, ruff clean), but two brief-listed contracts are not actually protected:

1. The source-level import-absence test (AC-P2-006e) can never fail: its regex has no `re.MULTILINE`, so it matches nothing in any of the three files. Nothing else in the repo guards `cv2` either (mutation-proven).
2. The golden 4-person fixture cannot detect a person-ordering regression that sorts by bbox x1 or area (mutation-proven), although "in order" is an explicit AC-P2-006a requirement.

Both are small, test-only fixes. Details and evidence below.

## Verification performed

### Freshly executed by this reviewer (2026-09-21, from `eldercare-vision/`, project venv Python 3.10.8, pytest 9.1.1, `-p no:cacheprovider`)

| # | Command | Observed result |
|---|---|---|
| 1 | `git rev-parse --short HEAD` / `git status --short` | `7204021` / empty (clean) |
| 2 | `.\.venv\Scripts\python.exe -m pytest tests/ai_regression/test_pose_regression.py -v -p no:cacheprovider` | `collected 21 items` ... `21 passed in 0.22s` (all 21 names listed PASSED) |
| 3 | 4 related suites together (`tests/unit/test_pose_adapter.py tests/unit/test_pose_pipeline.py tests/unit/test_pose_timing.py tests/integration/test_pose_pipeline.py -q`) | `166 passed in 0.55s` |
| 4 | Same suites individually | adapter `38 passed`, pipeline unit `50 passed`, timing `75 passed`, integration `3 passed` (38+50+75+3 = 166, matches brief) |
| 5 | Full `python -m pytest -q -p no:cacheprovider` | `490 passed in 1.60s` (490 = 469 prior + 21 new) |
| 6 | `ruff --version` (throwaway CI-pinned venv) | `ruff 0.16.6` |
| 7 | `ruff check . --no-cache` | `All checks passed!` |
| 8 | `ruff format --check . --no-cache` | `112 files already formatted` |
| 9 | `python -m pytest --collect-only -q -p no:cacheprovider` (filtered for `verify_pose`/`ai_regression`) | 21 `ai_regression` items listed, zero `verify_pose` entries, `490 tests collected` |
| 10 | `importlib.util.find_spec` for `torch`, `ultralytics`, `cv2` in the venv | `torch False`, `ultralytics False`, `cv2 True` |
| 11 | Fresh interpreter: import `pipeline`, `adapter`, `timing`; print `'cv2' in sys.modules` etc. | `cv2 loaded: False | torch: False | ultralytics: False` |
| 12 | Probe of the test's exact import regex against the three production files (scratch script) | see Important-1: `findall` returns `[]` for all three |
| 13 | Mutation runs, 64 distinct mutants (65 runs; one flawed `id()`-keyed probe was discarded and replaced; details in the mutation table) | 45 killed by the new file; 19 survived the new file |
| 14 | `git status --short` after all probes and scratch deletion | empty (clean) |

Mutant isolation proof: every mutation run went through a wrapper that ran `pytest.main(...)` inside the mutant copy (cwd = copy, `PYTHONPATH=<copy>/src`) and then printed `eldercare.vision.pose.adapter.__file__`. The unmutated baseline in the copy printed the copy's path (`...\scratchpad\mut\work\src\eldercare\vision\pose\adapter.py`, `21 passed`), not the original repo (the venv has an editable `.pth` pointing at the original `src`; `pythonpath=["src"]` from the copied `pyproject.toml` plus `PYTHONPATH` put the copy first). All mutation rows except F05 (which failed at collection before the print) reported the copy path.

### Historical evidence NOT re-executed (taken from `docs/task-reports/P2-006.md`, dated 2026-09-20, claims only)

- RED-first evidence (`1 failed, 20 passed` from a deliberately wrong `(4, 18, 2)` probe; then `21 passed in 0.14s`). Not re-executable: the probe edit no longer exists.
- `git diff --stat -- src/` empty; `git diff --name-only` showing only `tests/ai_regression/.gitkeep`; `git status` listing `?? docs/task-briefs/P2-006.md`. These reflect the implementer's working tree against the old inner repo (`c368eed`). This reviewer only has the squashed snapshot (`4581e86` initial + `7204021` "full project source"), so the pre-task diff cannot be reproduced. Substitute evidence is in "Scope and hygiene" below.
- Report figures `111 files already formatted` and `0.86s` full run: my fresh figures are `112` and `1.60s` (see FYI-4).

### Scope and hygiene (what could and could not be verified)

- Verified in HEAD: `tests/ai_regression/` tracks exactly one file, `test_pose_regression.py` (`git ls-files tests`); no `.gitkeep` and no `__init__.py` there. Basename `test_pose_regression.py` is unique repo-wide (`git ls-files | grep -c` = 1); the only duplicated test basename is the pre-existing `test_pose_pipeline.py` (unit + integration, resolved by their `__init__.py` files).
- Verified: `pyproject.toml` dependencies are `pydantic`, `pydantic-settings`, `opencv-python-headless`, `numpy` (no ultralytics/torch), matching the P2-004 review's record; no requirements file was added.
- Verified: fixtures are inline `np.arange` / `np.linspace` / literal arrays; no fixture files; no file reads except reading three production sources and the manual script as text.
- Could not verify from git: that the `.gitkeep` deletion and the zero `src/` diff happened in this task (history is squashed). Corroboration: production line references recorded in the P2-004 and P2-005 reviews still hold exactly (`pipeline.py:180-181` clock/timer defaults, `pipeline.py:190-191` timer guard, `timing.py:37` and `:117-120`, `adapter.py:101-121`, `adapter.py:278-279`, `inference.py:86` and `:93-96`), so `src/` is consistent with the P2-005-reviewed state. File mtimes are all the snapshot-import time and prove nothing.
- Verified: `tests/unit/.gitkeep` remains and `tests/integration/.gitkeep` is gone; both are pre-existing state (P2-004 removed the latter) and not part of this task.

## Checklist verdicts (against real code, file:line in the new test unless noted)

1. **17-keypoint ordering + shapes.** Full COCO tuple equality is pinned at `test_pose_regression.py:199-202` against a literal at `:35-53` that matches AI_SPEC §4 and `adapter.py:51-69`. Shape assertions exist only for the GOLDEN_4P fixture (`:205-211`); the 0-person stub has `keypoints=None` and the 1-person stub's shapes are never asserted directly (17 per person is enforced behaviorally by `PersonPose`, `adapter.py:200-205`, and by the 4P `len(person.keypoints) == 17` at `:234`). Mutants A01 and A02 (names swap, `KEYPOINT_COUNT=18`) are killed. Acceptable; see FYI-1.
2. **Confidence bit-for-bit, `==`.** `:225`, `:238`, `:274`, `:289-304`; exact `0.0` (`conf[0,0]` from `linspace`, det-conf `[2]`), `1e-6`, `2.5e-6`; adapter and pipeline both. Mutants A04a/A04b (0.0 to 1e-9), A05 (floor tiny), A15 (round), A17 (float32) all killed. PASS.
3. **0 / 1 / 4 persons through adapter and `process_frame`.** `:217-250`, `:256-283`. PASS (ordering caveat in Important-2).
4. **Missingness at pipeline level.** `:310-335` drives NaN, +Inf, -Inf through `_process` (real `PosePipeline.process_frame`), asserts `(None, None, False)`, `conf` equality, and untouched siblings. Mutants A06 (fabricate 0,0), A07 (NaN only), A08 / A08b (x only / y only), A09 (drop conf) all killed by this single test. PASS.
5. **Malformed-shape fail-closed, integrated.** `:341-358`, `pytest.raises(ValueError, match="17")` and `match="[Mm]ismatch"`. Could they pass for the wrong reason? Traced: the pipeline wrapper text is `pose adaptation failed for camera_id='cam-01' frame_id=7: ...` (`pipeline.py:218-221`), which contains neither `17` nor `mismatch`, and the image shape equals `orig_shape`, so the pipeline's own `orig_shape/image shape mismatch` error (`pipeline.py:227`) cannot fire; the match text therefore comes from the adapter (or the `PersonPose` 17-check, `adapter.py:202-205`). The assertions are substring-only and layer-agnostic: removing only the adapter row-count checks (A10a, A10c) or only one of the two box-count checks (A11a) survives because a second layer still raises `ValueError`, while removing both layers (A10b, A11b) is killed. That is correct behavior for a "pipeline still fails closed" spot-check, and the brief explicitly limits this area to two spot-checks. Sufficient. PASS.
6. **Frame to predictor to adapter.** Identity propagation (`:246-250`) and (h,w) to (w,h) on the golden `(1080,810)` to `(810,1080)` (`:220`, `:364-366`) and on the non-square `(480,640)` to `(640,480)` (`:259`, `:369-371`) are pinned and mutation-verified (A03, A18). Both shapes are non-square, so a swap cannot hide. Gap: the hand-off itself (`predict` receives `frame.image`) is not pinned (Minor-2).
7. **Timing non-interference + exact ms.** Exact `PoseTiming(10.0, 15.0, 25.0)` at `:260` and `(5.0, 15.0, 20.0)` at `:283` with `==`; default-vs-programmed pose/identity equality at `:377-396`; no `sleep`, no wall-clock assertion (the default-timer arm uses real `perf_counter` but asserts nothing about its values). Mutants T01-T04, P07, P08 killed; P03 (pose depends on timer value, only when the real timer is fast) killed only by this test. PASS.
8. **Determinism.** `:402-420`, `first.pose == second.pose` (dataclass tree equality) with fresh pipelines and the same frame object. Mutant P09b (pipeline mutates its input frame and behaves differently on a repeat) killed by determinism and non-interference. PASS. (Two calls on one pipeline instance are not exercised; the brief allows fresh pipelines.)
9. **Framework independence.** NOT effectively pinned for `cv2`; see Important-1. `torch` / `ultralytics`: the hard `assert ... not in sys.modules` at `:437-438` is real (mutant F04 killed), and neither package is installed here, so a top-level import of either fails collection anyway (F05). `UltralyticsPosePredictor()` at `:193` is safe: `inference.py:47-62` only validates and stores three arguments; the `ultralytics` import is lazy inside `predict` (`inference.py:86`) and is never called; mutant I05 (eager import in the constructor) is killed.
10. **No hidden network/GPU/download.** grep of the new file for `sleep|socket|requests|urllib|http|cuda|monkeypatch|mock|patch|environ|open(` finds only docstring/comment words and the two `sys.modules` string assertions. `verify_pose_model.py` is only `read_text()`-ed (`:472`), never imported or run; fresh `--collect-only` shows it is not collected. PASS.
11. **Compactness.** 21 tests (limit 30, brief target 20-26). Overlap with existing suites is substantial; see Minor-1.
12. **Scope/hygiene.** See section above. PASS with the stated verification limits.

## AC-by-AC verdict

| AC | Verdict | Basis |
|---|---|---|
| AC-P2-006a golden 4P mirrors P2-002, converts end-to-end, order/dims/confs bit-exact | PARTIAL | Shapes, dims, per-person bbox/det-conf, all 17 kp coords+confs (persons 0 and 3), pipeline == adapter are pinned and mutation-verified. "Order" is not discriminating: sorting persons by bbox x1 or area survives (A12b, A12d). Important-2. |
| AC-P2-006b 17 COCO + full tuple; (N,17,2)/(N,17) for 0/1/4; (h,w) to (w,h) on two shapes | PASS | Full tuple (`:199-202`), 17-per-person enforced, two non-square shapes. Explicit shape asserts exist for 4P only (FYI-1). |
| AC-P2-006c confidence preservation incl. 0.0/tiny; NaN/Inf missingness at pipeline level | PASS | Seven mutants across floor/round/threshold/float32/fabrication classes killed; `==` used throughout. |
| AC-P2-006d integrated fail-closed; determinism; timing non-interference | PASS | Traced for wrong-reason passes (none); P09b and P03 killed. |
| AC-P2-006e framework independence (`sys.modules` + source-level absence for adapter/timing/pipeline); manual path decoupled | FAIL | Source-level leg is vacuous (Important-1); `sys.modules` leg cannot detect `cv2`. Manual-path leg passes (S01/S02/S03 killed; collect-only shows no `verify_pose`). |
| AC-P2-006f compactness, cross-module, CPU-only, synthetic inline | PASS (with Minor-1) | 21 <= 30; CPU-only and synthetic-inline confirmed; some tests re-assert already-pinned behavior (brief-mandated overlap). |
| AC-P2-006g ruff + format + pytest green; 469 prior unmodified; zero prod diff; no dep changes | PASS (partly by inference) | Fresh: 21/21, 166/166 related, 490/490 full, ruff clean, format clean. "Unmodified prior tests" and "zero src diff" cannot be diffed from squashed history; counts reconcile (38/50/75/3; 490 = 469 + 21) and src line refs match the P2-004/P2-005 reviews. |

## Mutation probes

Method: 64 distinct deliberate mutations (including 3 multi-edit and 1 file-move variants; 65 runs, counting one discarded probe) applied only to a scratch copy, each run against `tests/ai_regression/test_pose_regression.py` alone; isolation proven as described above. Test labels: T1 predictor_defaults, T2 keypoint_names, T3 golden_stub_shapes, T4 golden_4p_adapter_order_dims, T5 golden_first_last_keypoints, T6 golden_pipeline_matches_adapter, T7 zero_person_pipeline, T8 one_person_pipeline_exact, T9 one_person_timing, T10 conf_adapter, T11 conf_pipeline, T12 nan_inf_pipeline, T13 fail_closed_dim, T14 fail_closed_box, T15 golden_orig_shape, T16 second_shape, T17 timing_non_interference, T18 determinism, T19 sys_modules, T20 source_imports, T21 manual_path.

| ID | Mutation (copy only) | Result |
|---|---|---|
| A01 | swap `nose` / `left_eye` in `KEYPOINT_NAMES` | KILLED: T2 |
| A02 | `KEYPOINT_COUNT = 18` | KILLED: 15 tests incl. T2, T13 |
| A03 | drop the h to w swap (`return height, width`) | KILLED: 12 tests incl. T4, T15, T16, T7 |
| A04a | keypoint conf exactly 0.0 floored to 1e-9 | KILLED: T10, T11, T5, T8 |
| A04b | detection conf exactly 0.0 floored to 1e-9 | KILLED: T10, T11, T4 |
| A05 | tiny keypoint conf (<1e-3) zeroed | KILLED: T10, T11, T5 |
| A06 | fabricate `(0.0, 0.0, present=True)` for a non-finite keypoint | KILLED: T12 |
| A07 | only NaN treated as missing (Inf kept) | KILLED: T12 |
| A08 / A08b | only x / only y checked for finiteness | KILLED: T12 (both) |
| A09 | missing keypoint loses its confidence (forced 0.0) | KILLED: T12 |
| A10a | remove adapter xy-row 17-check only | SURVIVED (conf-row check still raises `ValueError` "17"; contract holds, redundancy) |
| A10b | remove xy-row, conf-row, and `PersonPose` 17-checks | KILLED: T13 |
| A10c | remove both adapter row checks (keep `PersonPose`) | SURVIVED (`PersonPose` still raises "17"; contract holds, redundancy) |
| A11a | remove adapter boxes/person-count check only | SURVIVED (`_as_confidence_list` check still raises; contract holds, redundancy) |
| A11b | remove both box-count checks | KILLED: T14 |
| A12 | reverse person order | KILLED: T10, T11, T4, T5, T12 |
| A12b | sort persons by bbox x1 ascending | **SURVIVED** (also survives all 166 existing tests) |
| A12c | sort persons by det-conf descending | KILLED: T10, T11, T4, T5, T12 (only via the incidental `0.0` then `1e-6` tail) |
| A12d | sort persons by bbox area ascending | **SURVIVED** (also survives all 166 existing tests) |
| A13 | drop persons with det conf < 0.01 (threshold) | KILLED: T10, T11, T4, T5, T12 |
| A14 | keypoint conf < 0.3 becomes missing | KILLED: T5, T12, T8, T9 |
| A15 | round confidences to 4 dp | KILLED: T10, T11, T5, T12 |
| A16 | swap conf rows of persons 1 and 2 | KILLED: T10, T11, T12 |
| A16b | swap xy rows of persons 1 and 2 | KILLED: T12 only (via NaN placement) |
| A16c | swap bboxes of persons 1 and 2 | KILLED: T4 |
| A17 | float32 precision loss in `_as_float` | KILLED: T10, T11, T4, T5, T12, T8 |
| A18 | zero-person path returns swapped dims | KILLED: T7, T19 |
| A19 | transpose x / y for present keypoints | KILLED: T5, T12, T8, T9 |
| P01 | `frame_id + 1` | KILLED: T6 |
| P02 | `capture_timestamp` zeroed | KILLED: T6 |
| P02b | `camera_id` overwritten | KILLED: T6 |
| P03 | pose drops persons when `total_ms < 1.0` (timer-value dependent; only real timer trips it) | KILLED: T17 only |
| P03b | pose drops persons when `total_ms >= 20` | KILLED: T11, T6, T12, T17 |
| P04 | predictor receives `None` instead of `frame.image` | **SURVIVED** (also survives all 166 existing tests) |
| P05 | `predict` called twice | SURVIVED in new file; KILLED by 4 existing tests (`predictor.calls == 1` in `test_pose_pipeline.py` / `test_pose_timing.py`) |
| P06 | drop the `orig_shape` vs image-shape cross-check | SURVIVED in new file; KILLED by 2 existing unit tests (`test_process_frame_orig_shape_mismatch_*`) |
| P07 | stamps mis-ordered `(t0, t2, t2)` | KILLED: T7, T9 |
| P08 | pipeline returns `timing=None` | KILLED: T7, T9 |
| P09b | pipeline mutates the input frame; repeat of same frame gives a different result | KILLED: T18, T17 (an earlier `id()`-keyed variant, P09, was an unreliable probe because object ids are recycled; disregarded and replaced by P09b) |
| P10 | pipeline default timer `time.monotonic` instead of `perf_counter` | SURVIVED (equivalent for this purpose; not a P2-006 contract; listed for completeness) |
| T01 | swap predict_ms / adapt_ms formulas | KILLED: T7, T9 |
| T02 | remove `round(..., 9)` | KILLED: T7, T9 |
| T03 | seconds instead of ms (`_MS_PER_SECOND = 1.0`) | KILLED: T7, T9 |
| T04 | `total_ms` = predict only | KILLED: T7, T9 |
| T05 | backwards clock no longer fails closed | SURVIVED in new file; KILLED by 2 existing timing tests |
| I01 / I02 / I03 | default model / device / imgsz changed | KILLED: T1 (each) |
| I04 | `predict()` hard-codes `imgsz=320` | **SURVIVED** everywhere (no suite exercises `predict`; brief limits T1 to defaults) |
| I05 | constructor eagerly imports `ultralytics` | KILLED: T1 (ImportError; ultralytics not installed) |
| F01 | top-level `import cv2` in `adapter.py` | **SURVIVED** (T20 vacuous; T19 blind; all 166 existing pass too) |
| F02 | lazy `import cv2` inside `adapt_pose_results` | **SURVIVED** in file order (an earlier test already triggers the import, so T19 sees nothing "introduced"); KILLED by T19 only when it runs alone (`-k sys_modules`) |
| F03 | `importlib.import_module('cv2')` at top of `adapter.py` | **SURVIVED** (unfixable by a regex; needs a string/AST rule) |
| F04 | fake `torch` module placed in `sys.modules` by `adapter.py` | KILLED: T19 |
| F05 | top-level `import torch` in `adapter.py` | KILLED as a collection error (torch not installed); not caught by T19/T20 themselves |
| F06 | `import math, cv2` in `pipeline.py` | **SURVIVED** (comma import; even a fixed first-name regex would miss it, an AST check would not) |
| F07 | `from cv2 import imread` in `timing.py` | **SURVIVED** |
| F08 | top-level `import cv2` in `pipeline.py` | **SURVIVED** |
| F09 | aliased lazy `import cv2 as _c` inside `timing.py` | **SURVIVED** |
| F10 | `__import__('cv2')` at top of `timing.py` | **SURVIVED** |
| S01 | `verify_pose_model.py` gains `import pytest` | KILLED: T21 |
| S02 | `verify_pose_model.py` gains a `def test_` | KILLED: T21 |
| S03 | move `verify_pose_model.py` into `tests/` | KILLED: T21 |

Survivor breakdown (19): 8 import-boundary survivors (F01, F02, F03, F06, F07, F08, F09, F10; Important-1), 2 ordering survivors (A12b, A12d; Important-2), 3 redundancy-shadowed checks where the contract still holds (A10a, A10c, A11a), 3 owned by existing suites and killed there (P05, P06, T05), 2 unprotected by any suite but outside the brief (P04, I04; Minor-2, FYI-2), 1 equivalent (P10).

## Findings

### Critical

None.

### Important

**Important-1: the source-level import-absence test is vacuous, and nothing else in the repo guards `cv2` (AC-P2-006e, brief requirement 10).**

- Where: `tests/ai_regression/test_pose_regression.py:443` compiles `r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)"` with no flags; `:451` calls `import_pattern.findall(text)` on the whole file text. Without `re.MULTILINE`, `^` matches only at position 0 of the string, so only a file whose first characters are an import statement could ever match. All three production files start with a docstring, so `findall` returns `[]` and the loop at `:452-455` asserts nothing. The trailing `assert checked == [...]` (`:457-461`) is a tautology (`checked.append(rel)` runs unconditionally for each of the same three strings).
- Evidence (fresh): probing the exact pattern against the real files printed `adapter.py test-regex findall -> []`, `timing.py -> []`, `pipeline.py -> []`, whereas the same pattern with `re.M` returns the real imports (`['__future__', 'math', 'operator', 'dataclasses', 'typing']`, etc.). On a synthetic sample with a docstring first, no-flag `findall` returned `[]` and `re.M` returned `['math', 'cv2']`.
- Failure scenario (mutation-proven): adding `import cv2` at the top of `adapter.py` (F01) or `pipeline.py` (F08), `from cv2 import ...` in `timing.py` (F07), an aliased lazy import (F09), or a comma import (F06) leaves all 21 tests green; the 166 existing tests also stay green. The `sys.modules` proof cannot cover the gap: the snapshot at `:427` is taken after the modules are already imported (module-level imports at `:24-31`), and cv2 is legitimately loaded elsewhere in a full run (`stream/capture.py`), so cv2 is never "introduced" during the test; the hard assertions at `:437-438` cover only `torch` and `ultralytics`. A lazy `import cv2` (F02) is caught only when the `sys.modules` test runs first or alone, not in normal file order. `torch` / `ultralytics` leaks are still caught in practice (hard assertion plus not installed), so the practical exposure is `cv2`, which is installed and is exactly what the brief forbids ("NEVER import `ultralytics`/`torch`/`cv2`").
- Report claim contradicted: report §5 assumption 4 says the regex was "verified by listing every matching line in the three modules"; the regex as committed matches none.
- Suggested fix (test-only): parse with `ast` (walk `Import` / `ImportFrom`, including function-local ones, and check every alias name, which also catches `import math, cv2`), or at minimum add `re.M`; add a non-vacuity assertion (for example that `"dataclasses"` or `"math"` is among the discovered roots for each file); for a real `cv2` guard use a fresh-interpreter check, for example `subprocess.run([sys.executable, "-c", "import sys, eldercare.vision.pose.pipeline; assert 'cv2' not in sys.modules"])`; I verified in a fresh interpreter that this currently prints `cv2 loaded: False`. Dynamic imports (F03, F10) need an explicit string rule (`import_module`, `__import__`) or an accepted exclusion.

**Important-2: the golden 4-person fixture does not discriminate person ordering (AC-P2-006a "order", brief area 2).**

- Where: `_golden_4p_boxes()` (`:127-136`) is strictly ascending in x1, y1, x2, y2 and area across persons 0..3 (x1 = 10, 70, 200, 400; area = 5000, 7200, 15000, 40000), and the checks at `:217-226` compare against that same source order.
- Failure scenario (mutation-proven): a regression that sorts persons by bbox x1 (A12b) or bbox area (A12d) produces exactly the source order for this fixture, so all 21 tests pass (as do all 166 existing tests, whose 3-person fixtures share the property). Reversal (A12), swaps (A16c), and det-conf sort (A12c) are killed; A12c only because det confs `[0.93, 0.61, 0.0, 1e-6]` happen to end ascending.
- Suggested fix (test-only, one line of fixture data): permute the box rows (and keep det confs and keypoint patterns index-aligned) so that source order is non-monotone in x1, y1, and area, for example person 0 = the current person 2's box. Then assert order against the permuted expectation.

### Minor

**Minor-1: substantial overlap with the existing suites; brief-mandated, so not rated Important.**

- Near-verbatim repeats of existing assertions: `test_keypoint_names_full_coco_tuple_and_count` (`:199-202`) equals `tests/unit/test_pose_adapter.py:413-436`, which already asserts full tuple equality (the report's coverage map says the unit suite "spot-checks only"; that is incorrect); `test_zero_person_pipeline_empty_dims_kept_timing_exact` (`:256-260`) equals `tests/unit/test_pose_timing.py:310-322` (same stamps `100.0/100.010/100.025`, same `10.0/15.0/25.0`); `test_one_person_pipeline_exact_bbox_conf_coords` (`:263-275`) equals `tests/unit/test_pose_pipeline.py:231-246` and `test_pose_timing.py:325-342`; the two fail-closed tests (`:341-358`) use the same stubs and `match` strings as `test_pose_pipeline.py:352-371`; `test_timing_non_interference_default_vs_programmed_timer` (`:377-396`) equals `test_pose_timing.py:516-534` (4P instead of 1P). Inside the new file, the dims assertions of `test_golden_orig_shape_normalized_to_width_height` (`:364-366`) and `test_second_shape_normalized_to_width_height` (`:369-371`) are already made at `:220` and `:259`; `test_one_person_pipeline_timing_rides_along_undisturbed` (`:278-283`) is a subset of `:263-275` plus the timing line. `test_golden_4p_adapter_...` and `..._first_and_last_...` (`:217-239`) plus the two 0.0/tiny adapter tests are adapter-only (single module).
- Why not Important: the brief's own area list (items 1, 3, 6, 7, 8) prescribes these checks, so the overlap is inherent to the brief; the count (21) is inside both the hard cap (30) and the 20-26 target; several repeats add a genuinely new dimension (golden 4P, Inf, tiny values, second shape, cross-person siblings). If the Coordinator wants stricter compactness, folding `:364-371` into `:217-226` / `:256-283` and dropping the `:199-202` duplicate would remove three tests. I did not measure which individual mutant kills would be lost by that consolidation. That is a policy call, not a defect.

**Minor-2: the frame-to-predictor hand-off is unpinned (and the fake predictor's counter is dead code).**

- `FakePredictor.predict(self, image)` (`:90-92`) discards `image`, and `FakePredictor.calls` (`:88`, `:91`) is never asserted anywhere in the file (the only `.calls` reads are `FakeTimer`'s own, `:103-106`). Mutant P04 (`predict(None)` instead of `predict(frame.image)`) survives the new file and all 166 existing tests; the repo has no test that the pipeline passes the frame's image to the predictor. The existing unit tests do pin `calls == 1` (P05 killed there). The P2-006 brief does not list this contract, hence Minor, but a regression layer named "Frame to predictor to adapter" is the natural place: record the last `image` in `FakePredictor` and assert `is frame.image` and `calls == 1` in the golden pipeline test.

**Minor-3: a sanity net is missing for the `sys.modules` proof design (cv2 blind spot is documented nowhere).**

- The test docstring (`:7-9`) states the file "NEVER imports ultralytics/torch/cv2 at runtime (proven by the sys.modules test + the source-level import-absence test)". After Important-1 that sentence is false for `cv2`. Once Important-1 is fixed, update the wording; until then the docstring overstates the proof. (Kept separate from Important-1 because it is a documentation correction, not a coverage change.)

### FYI

- FYI-1: `test_golden_4p_stub_shapes_match_p2002_acceptance` (`:205-211`) asserts properties of the test's own fixture only; no production mutation can fail it (none did, across 64 mutants). It is brief-mandated (area 1) and guards fixture drift, which is legitimate. Explicit `(N,17,2)`/`(N,17)` assertions exist for the 4P fixture only; the 0- and 1-person stubs' shapes are not asserted, and 17-per-person is enforced through `PersonPose` (killed by A02, A10b).
- FYI-2: Survivors outside the brief but worth knowing: `UltralyticsPosePredictor.predict()` kwarg forwarding (`device=self._device, imgsz=self._imgsz`, `inference.py:90-92`) is exercised by no suite (I04 survives everywhere); pinning it would need an injected fake `ultralytics` module, which the brief's "defaults and shapes only" scope excludes. P05, P06, T05 are protected by existing unit suites (killed there). A10a/A10c/A11a survive because two independent layers each fail closed; the contract holds.
- FYI-3: Git history is squashed, so "`.gitkeep` deleted by this task" and "zero `src/` diff by this task" are not reproducible here; the committed tree is consistent with both, and `src/` line references match the P2-004/P2-005 reviews.
- FYI-4: `ruff format --check .` now reports 112 files versus 111 in the report, and the full run took 1.60s versus 0.86s (count/timing drift from the snapshot import; both clean and green).
- FYI-5: The report's RED evidence is a self-inflicted wrong expectation on a characterization test, not a failing test against missing behavior. That is inherent to a regression-pinning task and is fine; it is not re-executable here.
- FYI-6: The `sys.modules` idiom (`before` snapshot after imports) is the same in all four existing suites; its `torch`/`ultralytics` leg is sound (hard assertion), its `cv2` leg is order-dependent by construction. Consider a subprocess-based check as the shared pattern for later phases.

## Counts

- Critical: 0 | Important: 2 | Minor: 3 | FYI: 6.
- Fresh gates: new file 21/21; related suites 166/166; full 490/490; `ruff check` clean; `ruff format --check` clean (112 files).
- Mutation probes: 64 distinct mutants (65 runs); 45 killed by the new file; 19 survived (8 import-boundary and 2 ordering survivors are Important; 3 redundancy-shadowed; 3 covered by existing suites; 2 outside brief; 1 equivalent).

Verdict: NOT APPROVE

---

## Re-review

- Scope: scoped re-verification of Important-1, Important-2 and the three Minors after the fix loop. Reviewer role: same fresh, independent Reviewer; the fix agent's appendix in `docs/task-reports/P2-006.md` was treated as a claim and checked against the actual files.
- Date: 2026-09-21. Snapshot: HEAD `7204021` plus working-tree edits (`git status --short` before the re-review: ` M docs/task-reports/P2-006.md`, ` M tests/ai_regression/test_pose_regression.py`, `?? docs/reviews/P2-006-review.md`). `git diff --stat -- src` empty; `git diff --name-only` lists exactly the two modified files above.
- The original sections above are unchanged and remain as history. This section supersedes the earlier verdict.
- Only write: this appended section. Mutation work was done on a scratch copy that has been deleted (the scratchpad again holds only `ruff-venv`).

### Verification performed (fresh, this re-review)

| # | Command (from `eldercare-vision/`, `-p no:cacheprovider`) | Observed result |
|---|---|---|
| 1 | `pytest tests/ai_regression/test_pose_regression.py -v` | `collected 23 items` ... `23 passed in 0.58s` (includes `test_forbidden_frameworks_absent_in_fresh_interpreter`, `test_source_imports_absent_in_adapter_timing_pipeline`, `test_import_scanner_self_check_can_fail`) |
| 2 | 4 related suites (`test_pose_adapter`, `test_pose_pipeline` unit, `test_pose_timing`, integration `test_pose_pipeline`) | `166 passed in 0.55s` |
| 3 | full `pytest -q` | `492 passed in 1.96s` (469 prior + 23 new) |
| 4 | `ruff --version` / `ruff check . --no-cache` | `ruff 0.16.6` / `All checks passed!` |
| 5 | `ruff format --check . --no-cache` | `113 files already formatted` (includes the untracked review file) |
| 6 | `pytest --collect-only -q` filtered for `verify_pose` | no `verify_pose` entry; `492 tests collected` |
| 7 | `grep -c "^def test_"` on the test file | `23` (limit 30) |
| 8 | grep of the test file for `sleep`, `socket`, `requests`, `urllib`, `http`, `cuda`, `monkeypatch`, `mock`, `patch`, `urlopen`, `download` | only comment/docstring words (lines 8, 9, 174, 636); no network/GPU/sleep use |
| 9 | import lines of the test file | stdlib (`ast json math os re subprocess sys pathlib typing`), `numpy`, `pytest`, `eldercare.*` only. The embedded fresh-interpreter script (lines 551-593) imports only `json sys types numpy eldercare.*`. No `ultralytics`/`torch`/`cv2` import anywhere; those names occur only as strings/sets. |
| 10 | `ls tests/ai_regression`, `git ls-files tests/ai_regression`, `find tests -name test_pose_regression.py` | only `test_pose_regression.py` (plus ignored `__pycache__`); no `__init__.py`; basename unique; collection has zero errors, so none is needed |
| 11 | `git status --short -- src pyproject.toml tests/unit tests/integration scripts` | empty (no production, dependency, existing-test or script change) |

`subprocess` use: one local `sys.executable -c` child with a 60 s timeout, no network, no GPU, no sleep. The fix agent's reported figures (23 passed, 166, 492, ruff clean, 113 files) all reproduced.

### Resolution status of the original findings

| Finding | Status | Evidence |
|---|---|---|
| Important-1 (vacuous source-level import check; `cv2` blind spot) | RESOLVED | `_imported_roots` (`test_pose_regression.py:64-89`) uses `ast.walk` over the whole tree: `ast.Import` (all aliases), level-0 `ast.ImportFrom`, plus literal-string `__import__` / `import_module` calls. Applied to adapter/timing/pipeline (`:610-616`) with a non-vacuity guard (`assert roots`). Its self-test (`:619-633`) is not tautological: neutering the scanner in four different ways (module-level only, first alias only, no Call detection, no ImportFrom) each made `test_import_scanner_self_check_can_fail` fail (TM1, TM2, TM3, TM6 below). A fresh-interpreter subprocess test (`:551-607`) is the runtime backstop: it imports adapter/inference/pipeline/timing, calls the adapter (zero and one person) and one `process_frame`, and asserts none of `torch`/`ultralytics`/`cv2` in `sys.modules`. All 8 originally surviving import mutants (F01, F02, F03, F06, F07, F08, F09, F10) are now killed. |
| Important-2 (golden order not pinned) | RESOLVED for every plausible sort key | `_golden_4p_boxes()` / `_golden_4p_box_conf()` (`:188-205`) are non-monotone in x1, y1, x2, y2, area and detection conf (values checked by hand: x1 200,10,400,70; y1 100,20,500,30; x2 300,60,600,130; y2 250,120,700,150; area 15000,5000,40000,7200; det conf 0.61,0.0,0.93,1e-6). The property is asserted (`:293-307`) and can fail: restoring the old monotone boxes/confs (TM4) failed the order test with `golden 4P fixture is monotonic in x1: person order is not pinned`. Sorts by x1 asc/desc, y1, y2, area, width, centre-x, det conf asc/desc and reversal are all killed by 5 tests. See Minor-A for the keypoint-derived sort residual. |
| Minor-1 (overlap with existing suites) | OPEN, accepted (unchanged) | Still 23 tests <= 30; overlap remains brief-mandated. The fix appendix now corrects the false "spot-checks only" claim about `KEYPOINT_NAMES` (its "Corrections" item 1), which was the factual part of that finding. No action required. |
| Minor-2 (predictor hand-off unpinned, dead `calls`) | RESOLVED | `FakePredictor` records images (`:140-153`); `test_golden_4p_pipeline_result_matches_adapter_result` asserts `predictor.calls == 1` and `predictor.images[0] is frame.image` (`:345-347`). `predict(None)` (P04) and `predict` twice (P05) are both killed by that test. |
| Minor-3 (docstring overstated the cv2 proof) | RESOLVED | Module docstring (`:1-26`) and the `sys.modules` test docstring (`:530-536`) now state the bounded claims accurately (in-process test authoritative for torch/ultralytics only; cv2 owned by the fresh-interpreter test and the AST scan). Confirmed empirically: in every cv2 mutant only SUBPROC and/or AST fail while the in-process test stays green, exactly as the docstring says. |
| FYI-1..6 | Unchanged / informational | FYI-1 (golden shape test is fixture-only) and FYI-2 (survivors I04, P06) still apply and are re-listed below. |

### Mutation probes against the FIXED file

Method: scratch copy of the fixed tree, one mutation per run applied only to the copy, run with `cwd=<copy>` and `PYTHONPATH=<copy>/src`; after each pytest run the harness printed `eldercare.vision.pose.adapter.__file__`. The unmutated baseline printed the copy's path and `23 passed`; every one of the 58 mutation runs also reported the copy path (`workcopy=True`), never the original repo (the venv's editable install points at the original). 58 mutants: 51 production-source mutants and 7 mutants of the test file itself (TM1 to TM7). Labels: SUBPROC = `test_forbidden_frameworks_absent_in_fresh_interpreter`, AST = `test_source_imports_absent_in_adapter_timing_pipeline`, SELFCHK = `test_import_scanner_self_check_can_fail`, ORDER = `test_golden_4p_adapter_order_dims_and_detection_confs`, HANDOFF = `test_golden_4p_pipeline_result_matches_adapter_result`.

| ID | Mutation (copy only) | Result on the fixed file |
|---|---|---|
| F01 | top-level `import cv2` in `adapter.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F02 | lazy in-function `import cv2` in `adapt_pose_results` | KILLED: SUBPROC, AST (was SURVIVED) |
| F06 | `import math, cv2` in `pipeline.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F22 | `import math, cv2` in `adapter.py` | KILLED: SUBPROC, AST |
| F07 | `from cv2 import imread` in `timing.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F08 | top-level `import cv2` in `pipeline.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F09 | aliased lazy `import cv2 as _c` in `timings_from_stamps` | KILLED: SUBPROC, AST (was SURVIVED) |
| F10 | `__import__('cv2')` at top of `timing.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F03 | `importlib.import_module('cv2')` at top of `adapter.py` | KILLED: SUBPROC, AST (was SURVIVED) |
| F04 | fake `torch` placed in `sys.modules` by `adapter.py` | KILLED: SUBPROC, `test_sys_modules_free_across_golden_matrix_run` |
| F11 | NON-literal `__import__('cv' + '2')` at top of `adapter.py` | KILLED: SUBPROC only (AST cannot resolve it; runtime backstop works) |
| F18 | aliased `from importlib import import_module as _im; _im('cv2')` at top of `timing.py` | KILLED: SUBPROC only |
| F21 | top-level `import cv2` in `inference.py` | KILLED: SUBPROC only (AST excludes `inference.py` by design; the child imports it) |
| F13 | literal `import cv2` in the rarely executed NaN branch of the adapter | KILLED: AST only (not executed by the child) |
| F14 | `import cv2` inside the `TYPE_CHECKING` block of `pipeline.py` | KILLED: AST only |
| F15 | literal `import cv2` in never-called `PoseTiming.to_dict` | KILLED: AST only |
| F16 | literal `__import__('cv2')` in never-called `to_dict` | KILLED: AST only |
| F12 | NON-literal dynamic import in the rare NaN branch | SURVIVED (neither static nor runtime path sees it; documented limit, see FYI-R1) |
| F17 | NON-literal dynamic import in never-called `to_dict` | SURVIVED (same limit) |
| A12b | persons sorted by bbox x1 ascending | KILLED: 5 tests (ORDER, first/last keypoints, both confidence tests, NaN/Inf) (was SURVIVED) |
| A12d | persons sorted by bbox area ascending | KILLED: same 5 (was SURVIVED) |
| A12c | persons sorted by detection conf descending | KILLED: same 5 |
| A12e / A12f / A12g | sorted by x1 desc / y1 asc / y2 asc | KILLED: same 5 each |
| A12h | sorted by detection conf ascending | KILLED: same 5 |
| A12j / A12k | sorted by bbox width asc / bbox centre-x asc | KILLED: same 5 each |
| A12 | reverse person order | KILLED: same 5 |
| A16c | swap bboxes of persons 1 and 2 | KILLED: ORDER |
| A12m | persons sorted by mean keypoint confidence ascending | **SURVIVED** (Minor-A) |
| A12n | persons sorted by first-keypoint x ascending | **SURVIVED** (Minor-A) |
| P04 | `predict(None)` instead of `predict(frame.image)` | KILLED: HANDOFF (was SURVIVED everywhere) |
| P05 | `predict` called twice | KILLED: HANDOFF |
| A20 | `adapt_pose_results` raises `RuntimeError` at entry | KILLED: SUBPROC (fails with the child's traceback, proving the child really executes the adapter) plus 16 others |
| A01 | swap `nose`/`left_eye` | KILLED: names test |
| A03 | drop h to w swap of `orig_shape` | KILLED: 13 tests incl. SUBPROC |
| A04a | keypoint conf exactly 0.0 floored to 1e-9 | KILLED: 4 tests |
| A06 | fabricate `(0,0,present=True)` for a non-finite keypoint | KILLED: NaN/Inf pipeline test |
| A07 | only NaN treated as missing | KILLED: NaN/Inf pipeline test |
| A13 | drop persons with det conf < 0.01 | KILLED: 5 tests |
| A17 | float32 precision loss | KILLED: 6 tests |
| P01 | `frame_id + 1` | KILLED: HANDOFF |
| P03 | pose depends on timer value (only the real timer trips it) | KILLED: timing non-interference test |
| P07 | timing stamps mis-ordered | KILLED: 2 timing tests |
| P09b | pipeline mutates its input frame; repeat call differs | KILLED: determinism, timing non-interference |
| T02 / T03 | remove ms rounding / seconds instead of ms | KILLED: 2 timing tests each |
| I02 | predictor default `device=1` | KILLED: predictor-defaults test |
| P06 | drop the `orig_shape` vs image cross-check | SURVIVED in this file (unchanged; killed by 2 existing unit tests) |
| I04 | `predict()` hard-codes `imgsz=320` | SURVIVED everywhere (unchanged; outside the brief) |
| TM1 | TEST mutant: scanner walks module-level nodes only | KILLED: SELFCHK |
| TM2 | TEST mutant: scanner keeps only the first alias | KILLED: SELFCHK |
| TM3 | TEST mutant: scanner drops dynamic-import detection | KILLED: SELFCHK |
| TM6 | TEST mutant: scanner ignores `ImportFrom` | KILLED: SELFCHK |
| TM4 | TEST mutant: fixture boxes and det confs reverted to the old monotone values | ORDER fails with `golden 4P fixture is monotonic in x1: person order is not pinned` (the two confidence tests also fail because they index the permuted positions) |
| TM5 | TEST mutant: `PYTHONPATH` pointed at a nonexistent dir, plus top-level `cv2` in the copy's adapter | SUBPROC PASSES (the child falls back to the editable install, i.e. the original tree); only AST kills. See FYI-R2. |
| TM7 | TEST mutant: child script only imports (no adapter/pipeline calls), plus lazy `cv2` in `adapt_pose_results` | SUBPROC PASSES; only AST kills. Shows the child must execute the code; the committed script does (F02 and A20 are killed by SUBPROC). |

Survivor breakdown (6 of 51 production mutants): 2 keypoint-derived sort keys (A12m, A12n; Minor-A), 2 non-literal dynamic imports on paths the child does not execute (F12, F17; FYI-R1), 2 unchanged out-of-scope items (P06 covered by existing suites; I04 no suite, outside brief). All original survivors that mattered (8 import-boundary, 2 ordering, plus P04) are now killed.

### False-confidence checks on the new tests

- Can SUBPROC pass with a wrong `PYTHONPATH`? Yes, but only in a harness that also relocates the source: TM5 shows a nonexistent `PYTHONPATH` makes the child import the editable-install tree instead. In the committed test the path is `Path(__file__).resolve().parents[2] / "src"`, the same derivation the AST test and the manual-path test use, and in this repo it resolves to the tree under test; in an environment without an editable install a wrong path would fail loudly with an `ImportError` (non-zero return code asserted at `:605`). Not a defect.
- Does SUBPROC really run the adapter? Yes: A20 (raise inside `adapt_pose_results`) and F02 (lazy import inside it) are both killed by SUBPROC, so the child executes `adapt_pose_results` and `process_frame`. Its assertions cannot pass on empty stdout (`json.loads` of the last line would raise) or a failed child (`returncode == 0` asserted first).
- Does the fixture-property assertion actually fail on the old boxes? Yes (TM4, message above). It checks each of six keys in both directions, ties counted as monotone.
- Is the AST scan vacuous? No: `assert roots` per file plus a self-test that fails under four independent scanner regressions.
- Could the AST test false-positive on the current tree? No: it passes on all three files, and the `TYPE_CHECKING`-only first-party imports are not forbidden names.

### New findings

**Critical:** None.

**Important:** None.

**Minor**

- **Minor-A: person order not pinned against keypoint-derived sort keys.** A12m (sort by mean keypoint confidence ascending) and A12n (sort by first-keypoint x ascending) survive: the keypoint arrays remain per-person ascending `arange`/`linspace`, so their natural sort equals source order. The fix agent disclosed this in its "Residual notes". Not raised to Important: an adapter whose contract is verbatim pass-through has no plausible reason to sort by keypoint statistics, every box/detection-confidence key (both directions, plus width and centre-x that I added) is killed, and the brief mandates `arange`/`linspace` fixtures. Optional hardening: permute the person rows of `xy`/`conf` so the source order is non-monotone in those too.

**FYI**

- FYI-R1: non-literal dynamic imports (`__import__('cv' + '2')`) in code paths that neither the AST scan (cannot resolve non-literals) nor the child process (does not execute the path) reaches survive (F12, F17). Both limits are stated in the module docstring (`:18-22`) and the fix appendix. Non-literal imports on executed paths are caught (F11, F18).
- FYI-R2: the fresh-interpreter test trusts the `parents[2] / "src"` path (see false-confidence checks above).
- FYI-R3: previously listed FYI items remain: the golden-shape test is fixture-only (brief-mandated); `predict()` kwarg forwarding (I04) is unpinned by any suite; the `orig_shape` cross-check (P06) is protected only by existing unit tests; overlap with existing suites (Minor-1) is brief-mandated.
- FYI-R4: the fix appendix's `113 files` figure includes the untracked review file (my earlier 112 was without it), consistent with my fresh count.

### Fix-loop hygiene

- Only `tests/ai_regression/test_pose_regression.py` and the report appendix changed; `src/`, `pyproject.toml`, existing tests and `scripts/` are untouched (`git status`/`git diff --stat` above). 23 tests (limit 30); no `__init__.py` added or needed; synthetic inline fixtures only; no network, GPU or sleep; the test file imports no `ultralytics`/`torch`/`cv2`; `scripts/dev/verify_pose_model.py` is still only read as text and not collected.
- Previously killed mutants (names, orig_shape swap, confidence floors/rounding/float32, fabrication, NaN-only, threshold drop, identity, timer dependence, timing math, determinism, predictor default) are still killed, so the fix did not weaken existing protections.
- Counts after re-review: Critical 0, Important 0, Minor 1 new (Minor-A) plus 1 carried (Minor-1, accepted), FYI 4 new plus carried.

**Re-review verdict: APPROVE** (supersedes the earlier "Verdict: NOT APPROVE"; both Important findings are resolved and verified by mutation, and no Critical or Important issue was introduced).
