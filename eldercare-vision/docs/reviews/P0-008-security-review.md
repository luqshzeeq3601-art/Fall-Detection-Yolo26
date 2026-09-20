# P0-008 Security Review — Phase 0 gate (fresh reviewer)

- **Reviewer stance:** fresh Security Reviewer; prior implementation conversations NOT seen. Read-only execution only (greps, `git log -p` archaeology, ephemeral-env `docker compose config`, two adversarial logger probes with dummy values only). No files modified except this review. No `.env` created, no secrets written anywhere.
- **Scope inputs read:** brief `eldercare-vision/docs/task-briefs/P0-008.md` (Security Reviewer scope, §Requirements items 1–4); pack `AGENTS.md` §§11–12 (security + git rules); pack `CONSTRAINTS.md` §9 (security constraints); pack `ACCEPTANCE_CRITERIA.md` §§2–3 (Definition of Done + MVP acceptance; camera/pose/fall/persistence/dashboard items noted N/A — Phase 0 contains no such code, verified below).
- **Prior evidence cross-checked (read, re-verified live where cheap):** `docs/reviews/P0-004-review.md`, `P0-005-review.md` (+Re-review appendix), `P0-006-review.md`, `P0-007-review.md` (+Re-review appendix); `docs/task-reports/P0-004.md`, `P0-005.md`, `P0-007.md`.
- **Git:** HEAD `cd309d8` confirmed via `git rev-parse HEAD` (matches brief dependency). `git status --short` at review time: only `?? docs/task-briefs/P0-008.md` (coordinator input, pre-existing pattern). No commit by reviewer.

## Verdict: APPROVE

Zero Critical and zero Important findings. Secret hygiene is clean across tree and history, the committed attack surface is minimal and fail-closed, and the settings→redaction→logger boundary composes correctly under adversarial probe. All items below are Minor/FYI logistics for later phases — recorded, not fixed, per the brief's severity bar.

## Findings

### Critical — 0

None. No committed secret, no hardcoded credential, no live leak path reproduced.

### Important — 0

None. Both P0-005 Important findings (regex userinfo leak, `redact_mapping` TypeError) were fixed and re-reviewed to APPROVE; re-probed here against current HEAD — both stay resolved (see probe log).

### Minor (2, non-blocking, later-phase logistics)

- **[Minor] `JsonFormatter` emits `record.name` unsanitized while `service` is sanitized (carryover of P0-006 M1, not escalated).**
  `src/eldercare/common/logger.py:153` (`"logger": record.name`) vs `:154` (`"service": _sanitize_value(...)`); name built at `:266` (`getLogger(f"{ROOT_LOGGER_NAME}.{service}")`). A credential-bearing `service` string would be masked in `service` yet raw in `logger`. Exploitability stays low (service names are code constants, not external input). Follow-up for a later phase: route `record.name` through `sanitize_exception_message` at format time. Does not block Phase 0.
- **[Minor] `json.dumps` has no fail-closed guard; NaN/Infinity extras emit non-strict JSON (carryover of P0-006 M2, not escalated).**
  `src/eldercare/common/logger.py:169`. Values are pre-flattened by `_sanitize_value` (`:121-133`), so throws/circularity are unreachable, but `float("nan")`/`inf` extras serialize as bare `NaN`/`Infinity`, breaking strict downstream `json.loads`. Reachable only via explicit hostile/odd caller value; stdlib `emit` routes format errors to `handleError` without echoing the record, so no secret path opens. Follow-up: normalize non-finite floats in `_sanitize_value` and/or wrap `json.dumps` with a fail-closed fallback. Does not block Phase 0.

### FYI (5, no action for Phase 0)

- **[FYI] Mosquitto `1883:1883` with no auth and no healthcheck — accepted skeleton state.** `docker-compose.yml:107-115`. No in-image probe exists without custom scripts; broker conf/auth is explicitly later-phase scope (brief forbidden scope: "Do NOT write MQTT configs"). Disclosed in P0-004 report Limitations. Later phase must add `deployment/mosquitto/mosquitto.conf` bind (read-only), auth, and a `mosquitto_pub`-based healthcheck before any non-loopback exposure.
- **[FYI] Image tags are brief-mandated major pins, not digests.** `docker-compose.yml:87` (`postgres:16`), `:108` (`eclipse-mosquitto:2`). No `:latest` anywhere (grep-verified). Digest-pinning is a build-hardening consideration, out of Phase 0 scope.
- **[FYI] CONSTRAINTS §9 required items with no Phase 0 surface — N/A, tracked for later phases.** CORS allowlist, file-path validation for evidence access, TLS verification, shell-from-API-input, dependency auditing: no API/DB/MQTT/agent/vision-loop code exists yet (only docstring `__init__.py` + `.gitkeep` in `src/eldercare/{vision,fall_engine,api,db,mqtt,agents,incidents}/`, verified by tree listing), so there is nothing to harden. Boundary-level input validation that *does* exist (settings validators, `hide_input_in_errors=True`) verified sound. `npm ci` rehearsal recorded 0 vulnerabilities; no lockfile/digest or audit CI step is required at this gate.
- **[FYI] `redact_token` partial reveal (first2+last2 for len ≥ 8) is spec-mandated.** `src/eldercare/common/redaction.py:130-138`. Brief-mandated format; acceptable, recorded for awareness. No full token ever reaches logs via mapping path (`redact_mapping` masks fully).
- **[FYI] `__pycache__` / `.pytest_cache` / `.ruff_cache` present on disk, correctly untracked.** Ignored via `.gitignore:2,7,8`; `git status --short` shows neither as untracked. Local interpreter artifacts only, not committed.

## 1. Secret hygiene (whole tree + history)

| Check | Result |
|---|---|
| `.env` on disk (`Test-Path .env`) | `False` — absent, never created |
| `*.pem` / `*.key` / `.env` files anywhere (`Get-ChildItem -Recurse -Include`) | Zero hits |
| `.env.example` contents | Placeholders only: `CHANGEME` ×3 (requireds), safe literals (`mosquitto`, `1883`, `INFO`), empty for `DATABASE_URL`/`RTSP_URL`/`VLM_API_KEY`; only `<password>`/`<user>` placeholder tokens in comments. Byte-matches `Settings.model_fields` (9 keys) |
| Hardcoded credentials in compose/configs/workflows/tests | Clean: all 9 compose credential refs are fail-closed `${VAR:?…}` interpolations (`docker-compose.yml:61-64,80-83,95-97`); `DATABASE_URL` is interpolation-only construction; healthcheck uses correct `$${…}` escaping (`:101`); `config/logging.yaml` is comments-only (no parser, no secrets); `ci.yml` has zero `secrets.` refs; tests use `dummy-*` values in-process only (scan for `sk-\|ghp_\|AKIA\|prod-\|real` over unit tests: zero hits) |
| Secret-pattern grep over `src/` (`sk-…\|AKIA…\|ghp_…\|rtsp://user:pass@`) | Zero hits |
| `git log -p -- .env` | Empty — no `.env` content ever committed |
| `git log --all` filename scan for `.env/.pem/.key/secrets` additions | Zero committed files of those kinds |
| `git log -p -S "POSTGRES_PASSWORD="` / `-S "sk-"` archaeology | Sole `POSTGRES_PASSWORD=` hit is prose inside `docs/reviews/P0-005-review.md` (review text, no value); `sk-` history scan empty. No real secret value ever committed |
| `git show HEAD:.env.example` vs worktree | Identical placeholders; history shows only P0-001 skeleton → P0-005 rewrite commits |

## 2. Attack surface of committed definitions

- **Compose (`docker-compose.yml`, 136 lines):** 6 services render (`mosquitto, vision, postgres, api, web, agent-worker`); `config --quiet` exit 0, warning-free; Compose v5.2.0. Published ports minimal per brief — `api 8000:8000` (`:55-56`), `mosquitto 1883:1883` (`:112-113`), `web 80:80` (`:124-125`); postgres internal-only (ports only as commented debug override `:92-93`); `vision`/`agent-worker` publish none. Single bridge network `eldercare` (`:130-132`), all six attached. Named volumes only (`pgdata`, `mosquitto-data`, `:134-136`) — zero bind mounts. No `privileged` / `network_mode: host` / `cap_add` / `docker.sock` (grep clean; `user:`-pattern hits are only `POSTGRES_USER` env names, not compose directives). GPU reservation (`driver: nvidia`, `count: 1`, `[gpu]`) under `vision` only (`:40-46`). `restart: unless-stopped` on all six. `depends_on` sound (`api`/`agent-worker`→`postgres` `service_healthy` with `pg_isready` healthcheck `:100-105`; `vision`→`mosquitto` / `web`→`api` `service_started`, correctly no healthcheck where no in-image probe exists). No obsolete `version:` key, no `:latest`.
- **CI (`.github/workflows/ci.yml`, 99 lines):** triggers `push` + `pull_request` unfiltered (master-safe, no `main:`/`branches:` filter); `permissions: contents: read` (`:28-29`); `concurrency` group + `cancel-in-progress` (`:32-34`); `timeout-minutes: 10` both jobs (I1/M1 fix verified present `:39,:71`); pinned tool-install step `ruff==0.16.6 pytest==9.1.1` (`:57-58`, after install, before gates); first-party actions only, full semver (`checkout@v4.2.2`, `setup-python@v5.3.0`, `setup-node@v4.1.0`); CPU-only, no services/containers/GPU/datasets/credentials; grep clean for `continue-on-error`, `|| true`, `secrets.`, `docker`, `gpu`, `services:`.
- **`.gitignore` coverage:** `.env` (`:17`) + `.env.*` (`:18`), `*.log` (`:19`), `*.pem`/`*.key` (`:20-21`), coverage (`.coverage`, `coverage.xml`, `htmlcov/`, `:24-26`), `node_modules/`+`dist/`+`build/` (`:12-14`), weights (`*.pt/*.onnx/*.engine`, `weights/`, `:33-36`), datasets raw (`datasets/raw/`, `:29`), evidence (`evidence/`, `:39`), caches (`.pytest_cache/`, `.ruff_cache/`, `:7-8`). Spot `git check-ignore -v` confirms `.env`, `.env.local`, `*.log`, `coverage.xml`, `htmlcov/`, `node_modules/`, `dist/`, `*.pt`, `weights/`, `datasets/raw/`, `evidence/`, both caches all ignored.

## 3. Redaction/logging boundary (integration level + adversarial probe)

- **Composition verified by read:** `Settings.redacted_summary()` (`settings.py:90-112`) masks `POSTGRES_PASSWORD`/`VLM_API_KEY` via `redact_mapping` and strips userinfo from both URLs — so the summary object is safe to log. `JsonFormatter` routes message (`:171-191`, pre/post-`%` sanitize, mapping + positional args), extra/bound values (`:193-205`, `redact_mapping` key-mask then per-value sanitize), and exception text (`:207-218`, sanitized `{type, message}`, traceback object discarded) through the P0-005 sanitizer. Sole sink is `StreamHandler(sys.stderr)`; grep confirms no `print(`/file/network handlers/`basicConfig` in `src/`. `hide_input_in_errors=True` (`settings.py:30-34`) keeps `ValidationError` text secret-free (P0-005 FYI probes corroborated).
- **Adversarial probe 1 — sanitizer vs special-char password (P0-005 Important-1 regression):** `sanitize_exception_message('conn failed url=rtsp://admin:p@ss/w?d#x y@camera01.local:554/stream1 retry=3')` → `'conn failed url=rtsp://***@camera01.local:554/stream1 retry=3'` — `LEAK_PW: False`, `LEAK_USER: False`, `HOST_OK: True`. `redact_mapping({1:'x','password':'y'})` → `{1:'x','password':'***'}` — no throw (Important-2 stays fixed).
- **Adversarial probe 2 — end-to-end through the logger (dummy values only):** `configure_logging('INFO')` + `get_logger('vision','test-probe')`, logged `frame failed url=%s` with `rtsp://dummyuser:dummy-pw-p@ss/w?d#x@camera01.local:554/stream1` plus `extra={'event':'camera.offline','token':'dummy-token-value-xyz','password':'dummy-pass-123'}`. Captured stderr line: `{"timestamp": "…Z", "level": "INFO", "logger": "eldercare.vision", "service": "vision", "component": "test-probe", "event": "camera.offline", "message": "frame failed url=rtsp://***@camera01.local:554/stream1", "extra": {"token": "***", "password": "***"}}` — asserts held: password, username, token, and mapping password all absent; `camera01.local` preserved. **PROBE_RESULT: PASS.**

## 4. Open-items ledger reconciliation

| Item | Expected state | Verified |
|---|---|---|
| P0-001 `.gitignore` hardening gaps (P0-001 Minor) | Closed in P0-002 | **Closed, confirmed:** P0-002 review §3 verifies additive-only diff (`.env.*`, `*.log`, `.coverage`, `coverage.xml`, `htmlcov/`); current `.gitignore` (48 lines) retains all of them plus `*.pem`/`*.key`/weights/evidence/caches |
| MIT-license placeholder | Must still be OPEN, tracked for P12 | **Open, confirmed:** `pyproject.toml:6` still `license = { text = "MIT" }`; no `LICENSE` file on disk (`Get-ChildItem LICENSE*` empty); P0-003 brief §17 explicitly orders "do NOT add a LICENSE file… remains a tracked non-blocking follow-up for P12". Correctly untouched |
| P0-002 minors/FYIs (license placeholder; asyncio_mode note; format-count; LF→CRLF) | None escalated | **None escalated:** no new license file, no async tests added (`async def` count 0 per P0-007 re-review), no scope impact |
| P0-003 Minor (weak `toBeDefined` smoke assertions) + FYIs (lockfile, typecheck flags, eslint coverage, favicon 404) | None escalated | **None escalated:** frontend scaffold untouched by later tasks; no secret grep hits over `frontend/src` |
| P0-004 Minors (compose-version citation; web port-choice comment) + FYIs (mosquitto auth, digest pins, DB special-char edge) | None escalated | **None escalated:** compose semantics unchanged since P0-004 (only P0-005-owned `.env.example` and tooling evolved); special-char edge still disclosed and now covered by fixed sanitizer |
| P0-005 Minors (IPv6 bracket loss in `_strip_userinfo`, whitespace-only requireds, raw `DATABASE_URL` interpolation, generic RTSP scheme check) | None escalated | **None escalated:** `redaction.py:96-107` still rebuilds netloc from `hostname` (fail-closed direction preserved); settings validators unchanged; no bypass demonstrated |
| P0-006 Minors (M1 logger-name, M2 NaN guard) | None escalated | **None escalated:** carried above as the only two Minors of this review, still defense-in-depth non-blockers |
| P0-007 I1 (tool install) + M1 (timeouts) | Resolved, re-reviewed APPROVE | **Resolved, confirmed at HEAD:** `pip install "ruff==0.16.6" "pytest==9.1.1"` present (`ci.yml:57-58`), `timeout-minutes: 10` on both jobs |

## Acceptance-criteria note (AC §§2–3)

- **DoD "no secret or dataset binary was added":** met — secret archaeology clean; no `*.pt`/`*.onnx`/`*.engine`/dataset binaries tracked (`git ls-files` shows none; weights/datasets paths gitignored).
- **MVP camera / pose-tracking / fall-engine / persistence-API / dashboard items:** N/A at Phase 0 by design — verified no such code exists (packages under `src/eldercare/` hold only docstring `__init__.py` files plus `.gitkeep` placeholders; `deployment/docker/` and `deployment/mosquitto/` hold only `.gitkeep`; no Dockerfiles; no RTSP/API/DB/MQTT/agent logic). No Phase 1+ scope leakage found.

## Re-verification note

Independent, read-only; no source/config/workflow files modified. Live checks executed at HEAD `cd309d8`: `git rev-parse`/`log --oneline`/`status --short`; `Test-Path .env` → False; recursive `*.pem/*.key/.env` search → zero; `git log -p -- .env` → empty; `-S` pickaxe scans for `POSTGRES_PASSWORD=` (only review prose) and `sk-` (empty); secret-pattern greps over `src/`, unit tests, `frontend/src` → zero true hits; `git check-ignore -v` for secrets/logs/coverage/Node/weights/evidence/caches → all ignored; ephemeral dummy-env `docker compose config --quiet` (exit 0) + `--services` (6/6) + `docker compose version` (v5.2.0); two adversarial probes with dummy values only (sanitizer-level and end-to-end logger, both PASS with host context preserved). To reproduce: re-run the probe commands in §3 and the `check-ignore`/grep scans in §§1–2; expected result is zero leaks and full ignore coverage. Full test/lint suite re-execution belongs to the Phase Reviewer scope (AC-P0-008a), not duplicated here.

## Finding counts

- Critical: 0 · Important: 0 · Minor: 2 · FYI: 5
