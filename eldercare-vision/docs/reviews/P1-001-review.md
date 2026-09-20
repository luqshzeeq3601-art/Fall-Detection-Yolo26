# P1-001 Security Review — Camera config model (fresh reviewer, read-only)

- Target: `eldercare-vision/src/eldercare/vision/stream/camera.py` (new, 121 lines),
  `eldercare-vision/src/eldercare/vision/stream/__init__.py` (new, docstring-only),
  `eldercare-vision/tests/unit/test_camera_config.py` (new, 344 lines)
- Base: git HEAD `70066f2`; working tree reviewed read-only (no files modified by reviewer).
- Brief: `eldercare-vision/docs/task-briefs/P1-001.md` (criteria a–g, forbidden scope).
- Spec: pack `AGENTS.md` §§9/11/12, `CONSTRAINTS.md` §9, `PRD.md` NFR-020/021.
- Evidence: `eldercare-vision/docs/task-reports/P1-001.md` + tester verdict PASS (139 tests).
- Reviewer re-verification: static read of all three target files + `redaction.py`,
  `git status`, cv2 grep re-run, and live read-only probes (`PYTHONDONTWRITEBYTECODE=1`,
  dummy creds only, no test-suite execution to avoid touching the tree).

## Verdict: REQUEST CHANGES

One Important finding (residual credential-leak path via pydantic's `__rich_repr__`,
trivial in-scope fix). All brief acceptance paths themselves are clean. No Critical findings.

## Findings

### [Important] `__rich_repr__` bypasses the `__repr__`/`__str__` redaction — raw userinfo leaks
- Paths: `src/eldercare/vision/stream/camera.py:50-53` (`CameraConfig`, no
  `__rich_repr__` override) vs `camera.py:93-102` (redacted `__repr__`/`__str__`).
- Re-verification (live probe, pydantic 2.13.4): `str(list(cfg.__rich_repr__()))`
  contains BOTH the dummy username and password, while `repr(cfg)`/`str(cfg)` do not.
- Impact: anything rendering via `rich` (e.g. `rich.print(cfg)`, rich tracebacks logging
  locals, a future rich-based log handler) emits the raw `rtsp_url`, violating NFR-021
  ("RTSP URLs containing credentials must be redacted in logs") despite AC-P1-001d
  passing on the enumerated paths. No `rich` dependency exists today, so this is latent,
  not actively exploited — hence Important, not Critical.
- Fix (in-scope, ~5 lines + 1 test): override `__rich_repr__` yielding the redacted URL,
  e.g. yield `("rtsp_url", redact_rtsp_url(self.rtsp_url))` alongside the other fields;
  add a test asserting `str(list(cfg.__rich_repr__()))` is credential-free (mirrors the
  existing `test_repr_redacts_credentials` at `tests/unit/test_camera_config.py:184-189`).
- Note: `copy.copy(cfg)` is safe (uses `__repr__`, probed clean); only the
  `__rich_repr__` dunder is exposed.

### [Minor] `model_copy(update=...)` bypasses validation on the frozen model
- Paths: `camera.py:53` (`ConfigDict(frozen=True, ...)`); no `model_copy` override.
- Re-verification (live probe): `cfg.model_copy(update={"rtsp_url": "http://evil-host/x"})`
  succeeds (wrong scheme accepted); `update={"camera_id": "bad id!!"}` succeeds
  (pattern bypassed); `update={"name": 123}` coerces to int without validation.
  Direct attribute assignment IS blocked (`ValidationError`, probed) — the existing
  `test_model_is_frozen` (`test_camera_config.py:71-74`) covers only that path.
- Impact: integrity, not confidentiality. Not attacker-reachable (requires deliberate
  developer call), but the "frozen = safe config" impression overstates the guarantee:
  P1-002 manager code could silently derive invalid configs (e.g. empty/non-rtsp URL)
  that fail late at connection time. Recommend documenting "never use
  `model_copy(update=...)`; reconstruct via `CameraConfig(...)` / `model_validate`" or
  overriding `model_copy` to re-validate. Not a blocker for this task (brief requires
  only frozen assignment semantics, which hold).

### [Minor] Exception chaining (`from exc`) keeps the urlsplit error as `__cause__`
- Paths: `camera.py:82`, `camera.py:90` (`raise ValueError(<generic>) from exc`).
- Re-verification (live probe): `str(ValidationError)` / `.errors()` / `.json()` are all
  credential-free on every tested path (bad port, bad scheme, adversarial
  `p@ss/w?x#y z` shape, nearby-field failure) — `hide_input_in_errors=True` honored on
  pydantic 2.13.4, and custom messages are generic literals. The chained cause message
  itself contains only the port token (`"Port could not be cast to integer value as
  'badport'"`), no userinfo, on this interpreter; NFKC-echo candidates tried by the
  reviewer were all shape-accepted, so no live leak was demonstrated.
- Residual: `traceback.format_exc()` renders the `__cause__` chain, so ANY future input
  whose urlsplit error echoes the netloc (which includes userinfo) would surface the
  secret in full tracebacks. One-word hardening: `raise ... from None` in both validator
  sites. Optional; defense-in-depth only.

### [Minor] Unencoded-delimiter passwords accepted with a urlsplit-derived wrong host (P1-002 handoff)
- Paths: `camera.py:79-91` (shape-only `urlsplit` validation, no percent-encoding rule).
- Re-verification (live probe): `rtsp://user:p@ss/w?x#y z@host/stream` is ACCEPTED with
  `urlsplit(...).hostname == 'ss'` — the validated host is an attacker-influenced
  fragment, not the real connection target. The existing test
  (`test_camera_config.py:297-307`) asserts leak-freedom only, per brief area 6.
- Impact in THIS task: none (no connections opened; brief explicitly scopes semantic /
  reachability checks out "by design"). Handoff requirement for P1-002: the capture
  layer must not trust `urlsplit`-derived host for dialing this class of URL — either
  reject unencoded `@`/`/`/`?`/`#`/space in userinfo at the boundary or percent-encode
  before parsing/connecting, otherwise credentials could be sent to the wrong host.
  Flagged here so the P1-002 brief carries it.

### [FYI] Raw dumps retain the secret by design — future API code must use the safe path
- Paths: `camera.py:104-108` (`model_dump_safe`); brief area 8 mandates raw retention.
- Re-verification (live probe): `cfg.model_dump_json()` and `cfg.__dict__` contain the
  raw password (intended — the capture layer needs it); `model_dump_safe()` returns an
  isolated redacted copy (mutating it does not affect `cfg.rtsp_url`, probed).
- Note for later phases: any FastAPI/log serialization must call `model_dump_safe()`,
  never `model_dump()`/`model_dump_json()`. Consider a lint/grep guard when the API
  layer lands (out of scope for this task).

### [FYI] Validation soundness — confirmed clean
- `camera_id` regex `^[A-Za-z0-9_-]+$` (`camera.py:55`): anchored, single character
  class, no nested quantifiers — linear, no ReDoS surface. 10k-char inputs rejected via
  `max_length` without crash (tested `test_camera_config.py:269-283`, fail-closed).
- `StrictBool` (`camera.py:57`): truthy-string/int/None/float coercion rejected
  (tested `test_camera_config.py:161-165`).
- Port handling (`camera.py:87-90`): non-numeric AND out-of-range (`99999`) ports both
  rejected fail-closed with the generic message (live-probed); malformed IPv6
  (`rtsp://[::1/stream`) rejected; uppercase scheme + mixed-case host accepted and
  normalized per brief (`RTSP://H1.Local:554/s` → host `h1.local`, probed).
- `name` strip validator (`camera.py:62-70`): rejects whitespace-only incl. `\u2003`,
  generic message, no input echo.
- `ensure_unique_camera_ids` (`camera.py:111-121`): no logging, names only the
  duplicate id; `camera_id` charset makes the id log/JSON-injection-safe. Non-secret
  by design (report assumption accepted).
- `hide_input_in_errors` behavioral claim re-confirmed: `str(exc)`, `.errors()`,
  `.json()` all password-free on credentialed-failure paths. (Trivia: `.errors()` still
  carries an `input` key for the non-secret failing field itself, e.g. the bad
  `camera_id` — harmless since `camera_id` is constrained charset, non-secret.)

### [FYI] Scope and report completeness — confirmed clean
- cv2-free: `Select-String -Pattern "cv2|opencv"` over `src/` → 0 hits (re-run by
  reviewer, matches report). No stream/health/queue/DB/persistence code in `camera.py`;
  imports are stdlib + pydantic + `common.redaction` only (`camera.py:39-45`) — no new deps.
- `stream/__init__.py` is docstring-only (1 line); `stream/.gitkeep` deletion staged
  (`D` in `git status`); `src/eldercare/common/*`, `pyproject.toml`, CI/compose/frontend/
  config untouched — working tree shows ONLY the allowed new files
  (`stream/camera.py`, `stream/__init__.py`, `tests/unit/test_camera_config.py`,
  `docs/task-reports/P1-001.md`) plus the coordinator-owned brief artifact.
- No `.env` (`Test-Path` → False); tests use dummy `dummyuser`/`dummy-pass-123`
  in-process only. No secrets committed (NFR-020).
- Report completeness: contract table ✓, reuse list (import-not-reimplement ✓),
  RED→GREEN evidence ✓, cv2 proof ✓, P0-005 deliberate differences (scheme narrowing,
  empty-rejected, frozen-vs-mutable) documented in both report and module docstring
  (`camera.py:20-29`) ✓. `model_dump()`-raw vs `model_dump_safe()` both-sides assertion
  present (`test_camera_config.py:335-344`) ✓.

## Re-verification note

Reviewer did not re-run the pytest suite (read-only mandate; avoids writing
`.pytest_cache`/`__pycache__` into the tree) and takes the 139-test PASS on the
tester's authority. All security-relevant behavioral claims the review depends on
(redaction paths, `hide_input` on `str`/`errors`/`json`, frozen assignment,
fail-closed ports/hosts, `__rich_repr__` leak, `model_copy` bypass, cause-chain
content) were re-probed live by the reviewer with dummy credentials as recorded above.

## Counts

- Critical: 0 | Important: 1 | Minor: 3 | FYI: 2
- Verdict: REQUEST CHANGES (sole blocker: `__rich_repr__` redaction gap + test).

## Re-review

- Verdict: **RE-REVIEW: APPROVE — Important finding resolved.**
- Re-verification is live-probed on the fixed tree (pydantic 2.13.4, dummy
  `dummyuser`/`dummy-pass-123` in-process only, read-only; focused pytest run
  per task mandate):
  1. `__rich_repr__` on a credentialed config yields
     `('rtsp_url', 'rtsp://camera01.local:554/stream1')` (redacted): `str(pairs)`
     contains neither dummy user nor password, host retained. `repr(cfg)` /
     `str(cfg)` still redacted (host retained); raw value retained only in
     `cfg.rtsp_url` (by design, capture layer needs it).
  2. Regression tests exist and pass:
     `test_rich_repr_redacts_credentials`
     (`tests/unit/test_camera_config.py:198-204`) and
     `test_rich_repr_and_repr_stay_redacted_together` (`:207-211`);
     `pytest tests/unit/test_camera_config.py -v` → **66 passed** (64 prior + 2 new).
  3. Sibling probes: f-string / `{!r}` / `%r` (all via `__str__`/`__repr__`)
     clean; `copy.copy(cfg)` repr clean; `__rich_repr__` yields exactly the 6
     public fields, no private attrs, no angle-bracket exposure.
     `model_dump()` / `model_dump_json()` retain the raw URL **by design**
     (brief area 8, pre-existing FYI — not a leak). `str/repr(ValidationError)`
     clean on bad-port, bad-scheme, nearby-field paths (as originally covered).
  4. Scope: `git status --short` shows only the expected new files
     (`stream/camera.py`, `stream/__init__.py`, `tests/unit/test_camera_config.py`,
     `docs/task-reports/P1-001.md`, brief + this review) plus the staged
     `stream/.gitkeep` deletion; `git diff HEAD --stat` shows no tracked-source
     modification. Fix + tests + report `## Fix loop` appendix only.
- New residual findings (both **Minor**, non-blocking, follow-up only):
  - [Minor] `__repr_args__()` / `__repr_str__()` / `__pretty__()` still yield the
    raw URL (pydantic helpers bypassing the custom `__repr__`; live-probed leak
    on all three). Reachable only via direct calls or `devtools` pretty-print;
    no `rich`/`devtools` dependency in the tree and all normal paths
    (`repr`/`str`/f-string/logging/`copy`) are clean — hence Minor, not Important.
    Suggest overriding or documenting "never pretty-print configs with devtools".
  - [Minor] `ValidationError.errors()` / `.json()` echo the raw credentialed input
    when `rtsp_url` itself fails validation (live-probed: bad-port-creds and
    bad-scheme-creds leak user+pass via `json`/`errors` while `str`/`repr` stay
    clean; `hide_input_in_errors` suppresses display only, not structured data).
    This corrects the original "all credential-free" overclaim, which holds for
    `str`/`repr` only (existing tests pin `str` only). No in-tree code serializes
    structured errors today — hence Minor. Suggest documenting "never log/return
    `.errors()`/`.json()` raw; prefer `str(exc)`" alongside the existing
    `model_dump_safe()` rule, with a test pinning it.
- Counts after re-review: Critical: 0 | Important: 0 | Minor: 3 carried + 2 new
  (residual, non-blocking) | FYI: 2 carried.
