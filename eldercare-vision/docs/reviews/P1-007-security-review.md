# P1-007 Security Review — Phase 1 gate (fresh reviewer, read-only)

- Scope: P1-007 brief Security Reviewer items 1–4 only. No Phase 2 functionality assessed; no files modified except this review.
- Base: git HEAD `551728b` (confirmed via `git rev-parse HEAD`; log top: `551728b P1-006`, `eef3f31 P1-005`, `5c3d18f P1-004`, `1106a3c P1-003`, `b9431db P1-002`, `e676ec1 P1-001`). Working tree clean except untracked gate-brief input (`?? docs/task-briefs/P1-007.md`); `git diff HEAD --stat` empty.
- Spec inputs read: pack `AGENTS.md` §§9 (Python rules), 11 (Security rules), 12 (Git rules); `CONSTRAINTS.md` §§7 (Architecture), 9 (Security), 11 (Observability).
- Prior evidence read: `docs/reviews/P1-001-review.md` (+Re-review), `P1-002-review.md`, `P1-003-review.md`, `P1-004-review.md`, `P1-005-review.md` (+Re-review), `P1-006-review.md`; `docs/task-reports/P1-001.md`, `P1-002.md`, `P1-005.md`, `P1-006.md`.
- Live sources read in full: `src/eldercare/vision/stream/camera.py` (129 lines), `capture.py` (222), `queue.py` (142), `health.py` (280), `reconnect.py` (330), `telemetry.py` (336); plus `.env.example`, `docker-compose.yml`, `pyproject.toml` deps, `.gitignore`.

## Verdict: APPROVE

No Critical or Important findings. Zero new findings of any severity. The two known-accepted credential edges (structured `.errors()`/`.json()` echo, devtools/pydantic pretty-print helpers) are reconfirmed as the ONLY edges, with no in-tree consumer touching either. Open-items ledger reconciled below: MIT placeholder stays open → P12; no prior minor escalated.

## Findings (new, this gate)

None. No Critical / Important / Minor. FYI confirmations only:

### [FYI-1] The two known-accepted edges remain the ONLY credential edges — reconfirmed live, no in-tree consumers

- Edge A (structured validation payload): `ValidationError.errors()`/`.json()` echo the raw credentialed `rtsp_url` when that field itself fails (bad-port, bad-scheme paths probed LEAK; nearby-field-failure path probed clean — `input` key carries only the non-secret failing field). `str(exc)`/`repr(exc)` clean on every path (P1-001 `hide_input_in_errors=True` honored).
- Edge B (pydantic pretty-print helpers): `__repr_args__()` / `__repr_str__(' ')` yield the raw URL (both probed LEAK); `__pretty__` present. Normal paths (`repr`/`str`/f-string/`copy.copy`/`__rich_repr__`) all probed clean with host retained.
- Confinement (static, `Select-String` over `src/**/*.py`): zero hits for `errors()`/`model_dump`/`repr_args`/`repr_str`/`__pretty__`/`devtools`/`import rich`; zero `rich`/`devtools` entries in `pyproject.toml`. No production code serializes structured errors or pretty-prints configs. Test files pin the clean paths only. Disposition unchanged: document "never log/return `.errors()`/`.json()` raw; prefer `str(exc)`" + "never pretty-print configs with devtools" when the API layer lands (P12-or-later docs touch, not this gate).

### [FYI-2] Raw-by-design surfaces unchanged and justified

- `CameraConfig.model_dump()` / `model_dump_json()` / `__dict__` retain the raw URL (probed); `model_dump_safe()` returns an isolated redacted copy (probed clean). `RtspCapture._config` / `vars(cap)` hold the raw URL (probed) — the capture layer must dial it; `repr` exposes only `camera_id`+`opened` (probed, no `__rich_repr__` present). `ReconnectController` never formats the held config URL; `__repr__` renders `camera_id` (sanitized defense-in-depth) + scalar counters (probed clean). `CaptureTelemetry`/`LatestFrameQueue`/`StreamHealthMonitor` hold no URLs by construction; `snapshot().to_dict()` strict-JSON round-trips with `allow_nan=False` (probed).

### [FYI-3] Non-credential residuals unchanged, still non-blocking

- `model_copy(update=...)` still bypasses validation (probed: `camera_id` swap succeeds) — integrity-only, requires deliberate developer call, same Minor as P1-001. No change.
- Exception cause chain (`raise … from exc`, `camera.py:82,90`): `traceback.format_exception` on the bad-port path probed clean (cause message carries only the port token, no userinfo) on this interpreter — latent defense-in-depth note only (`from None` optional). No change.
- Unencoded-delimiter shape (`rtsp://user:p@ss/w?x#y z@host/…` accepted with derived host fragment): no in-tree host parsing exists — `capture.open()` passes the raw configured URL straight to the factory (`capture.py:118`) and never dials via `urlsplit`-derived host — so the P1-001 handoff concern has no in-tree wrong-host trigger. No change.

## Attack-surface review (item 2)

- Thread-safety claims hold by read: `queue.py:93-102,111-114` (single lock, deque ops only, no-I/O invariant commented `:91-92,:109-110`); `health.py:165-177,196-216` (validation + `clock()` before lock at `:164,:195`, `_log_transition` after release at `:178,:216`); `reconnect.py:219-246` (counters + `delay_for` under lock, logging + `_sleep` outside; `capture.open()` at `:222` outside); `telemetry.py:275-296` (owned-state copy under lock, all component reads after release with discipline comment at `:281`; `note_frame` touches owned state only; zero logging in module). Single non-reentrant lock each, no nesting → deadlock-free by construction. `capture.py:80-84` single-owner contract documented; `read()` snapshots the handle locally (`:165`).
- Exception containment holds: no bare `except` anywhere in `stream/*.py` or `common/*.py` (grep-clean); all guards are `except Exception`, `BaseException` propagates by documented design (`capture.py:27-33`, `reconnect.py` adds no second containment — relies on the seam); no `raise` in `capture.py` (zero chaining surface); `telemetry.py` has no `except` at all; `__repr__`/`snapshot()` never raise on validated state.
- Resource bounds hold: queue strictly `depth <= maxsize` (`queue.py:96-102`, `maxsize >= 1` at `:42-43`); telemetry deque pruned per note + hard-capped at `MAX_FRAME_TIMESTAMPS = 16384` (`telemetry.py:252-260`, single append path at `:255`); reconnect delays capped by `max_delay`, counters plain ints, no collections grow; no unbounded buffers/queues/lists in any stream module (grep for `deque(`/`Queue(`/`maxsize`/`MAX_FRAME`/`append(` reviewed — only the two bounded deques).
- Dependency delta exact and justified: `pyproject.toml:10-11` (`opencv-python-headless>=4`, `numpy>=1`) — precisely the two third-party top-level imports in `capture.py:52-53`; everything else stdlib + first-party. No `rich`/`devtools`/network/DB/MQTT deps. `git log -- pyproject.toml` shows last dep change is P1-002's own commit — Phase 1 added nothing else.

## Archaeology + env/compose (item 3)

- `.env` absence: `Test-Path .env` → False; `.env` never tracked (`git log --all -- .env` empty, `git ls-files` no match, `.gitignore:17` ignores `.env`).
- Git history clean for Phase 1: `git log --all -p -- src/eldercare/vision/stream/` piped through `Select-String dummy-pass` → no matches (only dummy in-process test values exist in working-tree tests, never committed as real secrets; the one `hunter2` token string lives in test fakes as a redaction probe by design). Per-file log confirms each stream module was last touched only by its owning task commit (camera e676ec1, capture b9431db + P1-003 doc-only 1106a3c, queue 1106a3c, health 5c3d18f, reconnect eef3f31, telemetry 551728b) — no post-hoc edits outside the recorded fix loops.
- `.env.example` placeholder-only: `POSTGRES_*=CHANGEME`, `DATABASE_URL=` empty, `RTSP_URL=` empty, `VLM_API_KEY=` empty; only `<user>:<password>` appears inside a format comment. No real values.
- Ephemeral-env compose check (read-only, dummy in-session values only, nothing written): `docker compose config --quiet` → exit 0 (`COMPOSE-EXIT:True`). Phase 1 changed nothing infra-side (compose untouched since P0-004; no Dockerfiles added).

## Adversarial probe outputs (item 1, dummy `dummyuser`/`dummy-pass-123` in-process only)

Probe script lived outside the repo (`Temp/opencode/p1-007-probe.py`, deleted after run); repo untouched (`PYTHONDONTWRITEBYTECODE=1`):

```text
repr-clean: True | host-retained: True
str-clean: True
rich-clean: True
safe-clean: True
raw-by-design: True | json-raw-by-design: True
copy-clean: True
fstring-clean: True
dict-raw-by-design: True
repr_args-LEAK(expected): True
repr_str-LEAK(expected): True
has-pretty: True
badport str-clean: True
badport errors-LEAK(expected): True
badport json-LEAK(expected): True
nearby str-clean: True
nearby errors-has-input-key: True
nearby errors-leak: False
badscheme str-clean: True
badscheme errors-LEAK(expected): True
traceback-clean: True
model_copy-bypass-present: True
open-false: True
last_error-clean: True        (live logger line double-sanitized: "boom rtsp://***@cam01.local:554/s1 token=***")
repr-clean: True (capture + reconnect, "rtsp://" absent)
has-rich: False (capture — no sibling needed)
vars-holds-config-by-design: True
happy-last_error-none: True
attempt-false: True | last_delay-set: True (1.0)
capture-last_error-clean: True
queue/health/telemetry repr-clean: True
snapshot-clean: True | strict-json: True
PROBE-DONE
```

## Open-items ledger reconciliation (item 4)

| Item | Prior state | Current state at 551728b | Escalated? |
|---|---|---|---|
| MIT placeholder (`pyproject.toml:6` `license = { text = "MIT" }`, no `LICENSE` file — P0-002 Minor) | Open → P12 | Still open → P12 (verified: `Test-Path LICENSE` False, `git ls-files` no match, field untouched since P0-002). Non-security-functional; must stay open. | No |
| P1-001 Important (`__rich_repr__` leak) | Closed in Re-review (fix + 2 tests) | Closed, reconfirmed clean live (`rich-clean: True`). | No |
| P1-001 residuals (model_copy bypass; cause-chain; unencoded-delimiter; `__repr_args__`/`__pretty__`; `.errors()`/`.json()` echo) | 3 carried + 2 new Minors, all accepted | All re-probed: identical behavior, no in-tree trigger for any. Remain Minor/FYI. | No |
| P1-002 Minors ×4 (BaseException docs; thread-safety note; `__exit__` sig; cleanup-swallow comment) | All closed via P1-003 + Re-review | Closed; live reads confirm exact-scoped docstrings (`capture.py:12-14,27-33,107-112,158-163`), `TracebackType` signature (`:210-215`), preserving-`last_error` comments (`:134-151`), arming test present. | No |
| P1-003 Minors ×2 (stale bullet; untested arming branch) | Closed in Re-review | Closed; no `stream/queue.py` or `capture.py` change since 1106a3c. | No |
| P1-004 M1 (non-numeric thresholds → `TypeError` not `ValueError`, `health.py:122`) | Open Minor | Still open (no `health.py` change since 5c3d18f; thresholds originate from code defaults, not attacker input). Not security-relevant. | No |
| P1-005 Minor-1 (dual-keyword `max_attempts_override` + `max_attempts`) | Open, deferred (standardize later) | Still open; ruling belongs to the Phase Reviewer per brief item 5. Security stance: no secret impact — both spellings validated (`_resolve_cap`, `reconnect.py:288-303`), disagreement → `ValueError`, logs carry numerics only. | No |
| P1-005 Minor-2 (per-call cap semantics) / Minor-3 (int-vs-float) | Closed in Re-review | Closed; live reads confirm doc line (`reconnect.py:261-262`) and `float(...)` return (`:139`). | No |
| P1-006 Minor-1 (out-of-order prune doc overstatement, `telemetry.py:252-260` vs `:43-44`) | Open Minor | Still open (no `telemetry.py` change since 551728b). FPS always correct (full-scan `snapshot`), memory capped; production (monotonic clock) path exact. No secret impact. | No |

## Re-verification note

Reviewer ran no pytest suite (read-only mandate; full re-run belongs to the Phase Reviewer/Tester per the brief's role split) and takes the 303-test PASS on prior record. Every security-relevant behavioral claim above was verified live at HEAD `551728b` via the dummy-values probe plus read-only greps (`src` edge-consumer scan, bare-`except` scan, bounds/threading scan), `git` archaeology (`rev-parse`, `log`, `status`, `ls-files`, per-file log, `-p` secret scan), `.env`/`LICENSE` absence checks, `.env.example` read, and `docker compose config --quiet` with ephemeral in-session dummy env. No repo file was created or modified except this review. Temp probe script removed after run.

## Counts

- Critical: 0 | Important: 0 | Minor: 0 (new) | FYI: 3 (confirmations, non-blocking)
- Carried open: MIT placeholder (→ P12) + P1-004 M1 + P1-005 Minor-1 + P1-006 Minor-1 — none escalated.
- Verdict: APPROVE (zero blocking findings).
