# P2-002 Review — Load `yolo26s-pose.pt` (fresh reviewer, read-only)

- Target: `eldercare-vision/scripts/dev/verify_pose_model.py` (178 lines, new, working-tree review — no commit by design).
- Base: git HEAD `5672c0288fe016cbf39be5180f372605ee40a4d1` (reviewer confirmed via `git rev-parse HEAD`; brief-expected `5672c02` prefix confirmed, matches implementer report `docs/task-reports/P2-002.md:4`).
- Brief: `eldercare-vision/docs/task-briefs/P2-002.md` (criteria AC-P2-002a–e, forbidden scope).
- Spec: pack `AGENTS.md` §§3/8/14 (Ultralytics tasks, performance rules, benchmark honesty) + `AI_SPEC.md` §§2–4 (selected model, no-fine-tune, 17-keypoint representation) + `CONSTRAINTS.md` §2 (pose_model/imgsz/device defaults).
- Evidence: implementer report `docs/task-reports/P2-002.md` + independent tester verdict PASS (per task statement: re-run byte-matched, CUDA agreed, hygiene proven — taken on authority, not re-executed by this reviewer).
- Reviewer re-verification: full read-only reads of brief + report + script + pack `AGENTS.md`/`AI_SPEC.md`/`CONSTRAINTS.md` + `.gitignore` + prior review `P2-001-review.md` (format); light git probes only (`git status --short`, `git diff --stat`, `git check-ignore -v`, `git ls-files`, `git rev-parse HEAD`). No downloads, no inference, no file modifications except this review.

## Verdict: APPROVE

No Critical or Important findings. All five acceptance criteria (a–e) are met on the face of the script + report + git state, corroborated by the tester PASS. Assertions are sound and non-vacuous, failure modes are loud, honesty/hygiene/scope are clean, and rerun instructions are usable by P2-003+. Findings below are Minor/FYI only; none block.

## Findings

### [Minor] `--image`-not-found path exits without the `RESULT: FAIL` stdout line

- Paths: `scripts/dev/verify_pose_model.py:54-57` vs `fail()` at `:108-111`.
- Detail: every in-`main` hard failure goes through `fail()` (stderr `FAIL:` + stdout `RESULT: FAIL`, exit 1), but the `resolve_image` guard for a missing `--image` path prints `FAIL:` to stderr and calls `sys.exit(1)` directly without the stdout `RESULT:` line. The failure is still loud and non-zero, and it sits outside the canonical no-args run the Tester diffs — but an automated stdout-diff harness would see a missing `RESULT` line on exactly this path.
- Suggestion (non-blocking, P2-003+ or opportunistically): route this path through `fail()` (or print `RESULT: FAIL` before exit) so all failure exits share one stdout contract. No re-review.

### [Minor] CUDA assertion checks device *type* only, not index `cuda:0`

- Paths: `scripts/dev/verify_pose_model.py:169-171` vs brief `docs/task-briefs/P2-002.md:12` ("keypoint device (must be `cuda:0`)") and AC-P2-002b ("keypoint tensor device is CUDA — asserted").
- Detail: the assertion requires `data_device.type == "cuda"` (correctly fails loudly on CPU: `None`/non-cuda → `fail()`), and the printed record carries the full index (`keypoints_device: cuda:0`, `:150-153`; report transcript confirms `cuda:0`). So the AC wording ("device type is CUDA") is met exactly, and on this single-GPU target with default `--device 0` the distinction is immaterial. Strictly, though, the check is weaker than the brief bullet's "must be `cuda:0`" prose — a hypothetical `--device 1` run printing `cuda:1` would still PASS.
- Accepted as-is: matches the AC as written; default `0` (`:104`) + recorded `cuda:0` close the loop for this task. Optional hardening (compare `str(data_device) == "cuda:<args.device>"`) is P2-003+ polish, not a gate. No re-review.

### [FYI] No `N == person_count` cross-assert — theoretical gap only, not vacuous

- Paths: `scripts/dev/verify_pose_model.py:129` (`person_count = len(r)`) + `:157-168` (independent `≥1`, `(N,17,2)`, conf `(N,17)` asserts).
- Detail: each assertion is independently sound and non-vacuous (shapes require the full 3-D `(N,17,2)` / 2-D `(N,17)` structure, conf-`None` fails loudly, device-`None` fails loudly). The script does not assert `xy.shape[0] == person_count`, so a pathological result (boxes present, zero-row keypoint tensor) could pass shape checks with `N=0`. This behavior does not occur with this pose checkpoint (keypoint rows track detections; tester reproduced 4/4/4), and the brief does not require the cross-check.
- Suggestion: one-line `xy.shape[0] == person_count` assert as P2-003+ hardening. No action.

### [FYI] Weights-download failure is unwrapped — loud via traceback, acceptable for a dev script

- Paths: `scripts/dev/verify_pose_model.py:120` (`YOLO(MODEL_NAME)`, no try/except) vs the wrapped image-download path (`:81-98`, WARN + recorded fallback + loud `FAIL`).
- Detail: first-run `yolo26s-pose.pt` fetch failure surfaces as an uncaught exception (traceback, non-zero exit) rather than the structured `FAIL:` + `RESULT: FAIL` contract. That is still a loud failure, never a silent pass, and the report correctly records the network-once assumption (`docs/task-reports/P2-002.md:113-114`). Wrapping it would be nicer but adds no acceptance value. No action.

### [FYI] `--device type=int` rejects `"cpu"` with argparse exit 2 — correct scope

- Paths: `scripts/dev/verify_pose_model.py:101-105`.
- Detail: `--device` defaults to `0` (= `cuda:0`, per `CONSTRAINTS.md` §2) and only accepts ints; a `--device cpu` invocation dies in argparse (exit 2, usage error — loud, documented in the docstring `:15`). CPU fallback is not reachable and not claimed, which is exactly right for a CUDA load-proof (no CPU performance/accuracy claim exists to police). No action.

### [FYI] Official-workflow fidelity confirmed by read

- Paths: `scripts/dev/verify_pose_model.py:118` (`from ultralytics import YOLO`), `:120` (`YOLO("yolo26s-pose.pt")`), `:126` (`model.predict(source=..., device=args.device, imgsz=IMGSZ, verbose=False)` with `IMGSZ = 640` at `:31`), `:122-124` (checkpoint basename pinned to exactly `yolo26s-pose.pt`).
- Detail: matches the brief's sanctioned call pattern (`device=0`, `imgsz=640`, `verbose=False`) and the report's installed-source citations (report §1: `Model.predict` signature, `device`/`imgsz` via `**kwargs`, `Keypoints.xy/.conf/.data.device` layout, `Model.device` allocation-site semantics). Dependencies are stdlib + `ultralytics` only (`:22-28`; numpy allowed but not even imported — compliant subset). Zero-person / `keypoints is None` / missing-conf / wrong-device all route to loud `fail()` (`:157-171`). No action.

### [FYI] Honesty clean — transcript-only numbers, `model.device=cpu` correctly explained, no extrapolated claims

- Paths: `docs/task-reports/P2-002.md:36-55` (transcript), `:59`, `:121` (`cpu` explanation), `:100-108` (AC verdicts), `:112-124` (assumptions/limitations).
- Detail: every number in the report (4 persons, `(4,17,2)` / `(4,17)`, `cuda:0`, 137,419 B / sha256 image, 24,151,790 B / sha256 checkpoint) comes from the pasted transcript or local-file measurement — no FPS, latency, mAP, or accuracy claims anywhere, so `AGENTS.md` §8's seven-field claim record is vacuously satisfied and §14 holds. `model_device: cpu` is explained via the inspected `Model.device` source (parameter allocation after `map_location="cpu"` load), with CUDA execution proven by the asserted keypoint tensor device — honest and non-misleading. Relocation of the first-run CWD download into the pre-existing global `weights_dir` (settings file untouched, mtime verified) is disclosed rather than hidden (`:74-78`). No action.

### [FYI] Hygiene proven — weights/image outside repo and ignored; script leaks no paths/secrets

- Paths: `scripts/dev/verify_pose_model.py:66` (image → `tempfile.gettempdir()`, outside repo), `:30-36` (only constants: model name, `IMGSZ`, `BUS_JPG_URL` — no user paths, no secrets); `.gitignore:33-36` (`*.pt`, `weights/`); reviewer `git status --short` → exactly `?? docs/task-briefs/P2-002.md`, `?? docs/task-reports/P2-002.md`, `?? scripts/dev/verify_pose_model.py` (consistent with report §6; brief file is coordinator-owned as in prior tasks); `git diff --stat` → empty; `git check-ignore -v yolo26s-pose.pt` → `.gitignore:33:*.pt` (matches report §6); full `git ls-files` → no `.pt`/`bus.jpg`/`verify_pose` entries tracked.
- Detail: absolute cache/image paths appear only in the report (explicitly permitted by the task statement); the script itself hardcodes no user paths. `.gitignore` correctly untouched (extend-only-on-gap; no gap found). The report's `Get-ChildItem` no-`.pt`-in-worktree claim is corroborated by `git status` + `git ls-files`, not rescanned file-by-file per read-only scope, plus the tester hygiene PASS. No action.

### [FYI] Scope clean — load-proof only, no forbidden changes

- Paths: full `scripts/dev/verify_pose_model.py` (178 lines: load → predict → print record → assert; no adapter, tracking, RTSP, benchmark timing, export, tuning, dataset, or pytest code; no `src/` imports); reviewer `git diff --stat` (empty — no tracked files modified: no `src/`, `config/*.yaml`, `pyproject.toml`, CI, `frontend/`, tests); `git ls-files` (no new tracked files — deliverable + report + brief all still untracked, commits owned by coordinator per brief).
- Detail: AC-P2-002e holds. `except Exception` at `:81`, `:87` is reported-then-fallback (with `noqa: BLE001`), not bare/silent — compliant with the spirit of the no-bare-except rule for a dev script. No action.

### [FYI] Reproducibility usable by P2-003+

- Paths: `docs/task-reports/P2-002.md:34` (`python scripts/dev/verify_pose_model.py` from `eldercare-vision/`), `:57` (first-run download vs cache-reuse behavior), `:72-78` (cache path, image provenance with URL + bytes + sha256), `:112-114` (network-once assumption, non-required byte-identical confidences); script docstring `:11-15` (usage, exit-code contract).
- Detail: commands are paste-usable, cache behavior is stated (sanctioned single download, then `weights_dir` reuse with no `Downloading` line), and image provenance is complete. Baseline versions pin via P2-001 (`torch 2.5.1+cu121`, `ultralytics 8.4.142`). No action.

## Re-verification note

Reviewer performed a strictly read-only review: full reads of the 178-line script, 56-line brief, 124-line report, and cited spec sections (`AGENTS.md` §§3/8/14, `AI_SPEC.md` §§2–4, `CONSTRAINTS.md` §2); `git rev-parse HEAD` → `5672c0288fe016cbf39be5180f372605ee40a4d1` (matches report `:4`); `git status --short` → the 3 expected untracked paths (consistent with report §6); `git diff --stat` → empty (no tracked modifications, no dependency/test/config changes); `git check-ignore -v yolo26s-pose.pt` → `.gitignore:33:*.pt` (matches report); full `git ls-files` → no weights/image/script entries tracked. No inference, downloads, test execution, or CUDA allocation were performed — the re-run byte-match, CUDA agreement, and hygiene proof are taken on the independent tester verdict PASS authority (per task statement), corroborated by the static evidence above. To reproduce this review: re-read the four source files at the listed paths and re-run the five git probes; expected result is the state recorded here.

## Counts

- Critical: 0 | Important: 0 | Minor: 2 | FYI: 8
- Verdict: APPROVE (no re-review required; Minor items are advisory polish for P2-003+).

## Re-review (2026-09-20, fresh re-reviewer, read-only — Minors only)

RE-REVIEW: APPROVE — minors closed.

- Minor 1 (missing RESULT:FAIL on --image-not-found): CLOSED. `scripts/dev/verify_pose_model.py:54-58` now prints `FAIL:` to stderr AND `RESULT: FAIL` to stdout before `sys.exit(1)`, matching the `fail()` stdout contract at `:109-112`. Fix-log failure probe corroborates (stdout `RESULT: FAIL`, exit 1).
- Minor 2 (device-type-only assert): CLOSED. `:170-173` now builds `expected_device = f"cuda:{args.device}"` and requires both `data_device.type == "cuda"` AND `str(data_device) == expected_device`, with message `keypoint tensor device=<actual>, expected cuda:<args.device>`. A hypothetical `--device 1` printing `cuda:0` (or vice versa) now fails loudly; default `--device 0` semantics preserved.
- Success path unchanged: `print("RESULT: PASS")` + `return 0` at `:175-176` intact; `git diff HEAD --stat` empty (no tracked files modified) and `git status --short` shows only the 4 expected untracked paths (`docs/task-briefs/P2-002.md`, `docs/task-reports/P2-002.md` incl. `## Fix loop`, `scripts/dev/verify_pose_model.py`, this review) — no other files touched. Fix-log re-run (exit 0, byte-matching record, ruff clean) taken on authority per task statement; not re-executed.
- New issues from fix: none. Changed hunks read fully (one added stdout line + two-line assert/message); no logic, dependency, hygiene, or scope regression. Note (pre-existing FYI, not introduced, non-blocking): the `could not obtain canonical bus.jpg` path at `:98-99` still exits without stdout `RESULT: FAIL` — same class as Minor 1 but untouched by this fix and outside its scope; candidate for P2-003+ polish only.
