# P0-004 Review — Docker Compose skeleton (fresh security/code review)

**Reviewer stance:** fresh reviewer; implementation conversation NOT seen. Reviewed working tree on disk only, read-only (no files modified, no fixes implemented).
**Target:** `eldercare-vision/docker-compose.yml` (136 lines) + implementer report `eldercare-vision/docs/task-reports/P0-004.md` against brief `eldercare-vision/docs/task-briefs/P0-004.md` (criteria a–g) and pack spec (`AGENTS.md` §§11–12, `CONSTRAINTS.md` §9).
**Git:** HEAD `74f0d6d` (P0-003); working tree `M docker-compose.yml` + untracked `docs/task-briefs/P0-004.md` (coordinator input) + untracked `docs/task-reports/P0-004.md`. No commit by reviewer.

## Verdict: APPROVE

All seven acceptance criteria corroborated on disk; no Critical or Important findings. Two Minor and three FYI notes below are non-blocking (report-citation completeness and known later-phase hardening, all already disclosed in the implementer report).

## Findings

### Critical — none (0)

### Important — none (0)

### Minor (2)

- **[Minor] Report validation log omits the Compose tool version.**
  `docs/task-reports/P0-004.md` Validation log cites Docker client 29.6.1 + quoted daemon error but never states the `docker compose version` under which `config` passed warning-free.
  Re-verified independently: `docker compose version` → `v5.2.0` (matches the brief's environment fact), `docker compose config` exits 0 warning-free.
  Recommendation (non-blocking): one-line addition to the report log, e.g. "compose v5.2.0, `config` exit 0, no warnings". Not a file fix for this task — coordinator/report owner may append.
- **[Minor] No `web` port-choice record inside the compose file itself.**
  `docker-compose.yml:117-125` publishes `80:80`; the brief allowed 80 or 3000 with documentation. The choice IS documented in the report (Assumptions: "picked 80 as the served-static default") but the compose file has no comment stating the 80-vs-3000 decision. Non-blocking; a one-line comment would close the loop for future readers.

### FYI (3)

- **[FYI] Mosquitto `1883:1883` published with no auth and no healthcheck — accepted skeleton state.**
  `docker-compose.yml:107-115`. No in-image probe exists without custom scripts, and broker conf/auth is explicitly later-phase scope per the brief's forbidden scope ("Do NOT write MQTT configs"). The implementer report Limitations already discloses this ("no healthcheck and no auth in this skeleton; broker config/auth is later-phase scope"). No action now; later phase must add `deployment/mosquitto/mosquitto.conf` bind (read-only), auth, and a `mosquitto_pub`-based healthcheck.
- **[FYI] Image tags are brief-mandated major pins, not digests.**
  `docker-compose.yml:87` (`postgres:16`), `:108` (`eclipse-mosquitto:2`). No `:latest` anywhere (verified by grep). Matches the brief exactly; digest-pinning can be considered at build-hardening time. Not a finding against this task.
- **[FYI] `DATABASE_URL` special-character edge already flagged by implementer.**
  `docker-compose.yml:64,83` composes `DATABASE_URL` from `${POSTGRES_*}` interpolations (no hardcoded values). Report Limitations correctly notes passwords with special characters may need URL-encoding when services are implemented. No action now.

## Criterion-by-criterion corroboration (a–g)

- **(a) `config` exits 0, six services render — CORROBORATED.**
  Independent re-run (ephemeral in-session dummy env only, nothing written to disk): `docker compose config --services` → `mosquitto, postgres, agent-worker, api, vision, web` (6/6). `config --quiet` exit 0. Compose v5.2.0.
- **(b) Warning-free, no obsolete `version:` — CORROBORATED.**
  No `version:` key in file (grep clean); rendered `config` output scanned for `WARNING|warning|obsolete|deprecated` → zero hits.
- **(c) No hardcoded secret — CORROBORATED.**
  All 9 credential references are `${POSTGRES_USER:?…}` / `${POSTGRES_PASSWORD:?…}` / `${POSTGRES_DB:?…}` fail-closed interpolations (`docker-compose.yml:61-64,80-83,95-97`). `DATABASE_URL` is interpolation-only construction, not a committed value. Healthcheck `:101` correctly uses `$${POSTGRES_USER}` / `$${POSTGRES_DB}` (compose escaping → runtime container-env expansion). No `password:`/`api_key`/`secret:`/`token:` literals; no `.env` on disk (`Test-Path .env` → False).
- **(d) GPU on `vision` only — CORROBORATED.**
  `deploy.resources.reservations.devices` (`driver: nvidia`, `count: 1`, `capabilities: [gpu]`) present at `:40-46` under `vision` only; no other service has a `deploy:` block (grep clean).
- **(e) Postgres internal-only; explicit networks/volumes — CORROBORATED.**
  Postgres `:86-105` has no active `ports:` (only commented `:92-93` debug override). Published ports elsewhere are exactly the brief's minimal set: `api 8000:8000` (`:55-56`), `mosquitto 1883:1883` (`:112-113`), `web 80:80` (`:124-125`); `vision`/`agent-worker` publish none. Single bridge network `eldercare` (`:130-132`), all six services attached (`:33,53,72,89,110,122`). Top-level `volumes: pgdata, mosquitto-data` (`:134-136`) referenced at `:99` and `:115`. No `expose` clutter.
- **(f) Daemon-block honesty — CORROBORATED.**
  Report records `pull`/`up`/`ps` as ENVIRONMENT-BLOCKED with the full `npipe:////./pipe/dockerDesktopLinuxEngine` daemon error quoted, not marked PASS. No faked results; trimmed `config` output is labeled as dummy-value rendering. Consistent with this reviewer's environment (client-side `config` works, daemon calls unavailable).
- **(g) No forbidden-scope leakage — CORROBORATED.**
  `deployment/docker/` and `deployment/mosquitto/` contain only P0-001 `.gitkeep`; recursive `Dockerfile*` search → none. `git status` shows no touch to `.env.example`, `frontend/`, `src/`, `pyproject.toml`, `README.md`. No Dockerfiles, app code, MQTT conf, init SQL, CI, or `.env` created. No invented service APIs or benchmark numbers in file or report.

## Attack-surface checklist (security lens)

| Check | Result | Ref |
|---|---|---|
| Hardcoded credential / default password / committed secret (incl. comments, healthchecks, `DATABASE_URL`, image tags) | Clean — interpolation-only, fail-closed `:?` syntax | `:61-64,80-83,95-97,101` |
| Published ports justification | Minimal set per brief; postgres internal-only | `:55,92-93,112,124` |
| `privileged` / `network_mode: host` / `pid: host` / `cap_add` | Absent (grep clean) | whole file |
| `docker.sock` bind | Absent (grep clean) | whole file |
| Reckless volume binds | None — two named volumes only, no bind mounts at all | `:99,115,134-136` |
| Read-only mounts / `read_only:` / `user:` | Absent — N/A, no bind mounts or config files in this skeleton; revisit when broker-conf bind lands | — |
| Obsolete `version:` / `:latest` | Absent / absent; images pinned per brief | `:87,108` |
| `restart: unless-stopped` | All six services | `:32,52,71,88,109,121` |
| `depends_on` soundness | `api`/`agent-worker` → `postgres` (`service_healthy`, healthcheck exists); `vision` → `mosquitto` (`service_started`, no healthcheck exists — correct); `web` → `api` (`service_started`, `api` has no healthcheck — correct) | `:35-37,57-59,74-78,126-128` |
| Healthcheck soundness | `postgres` `pg_isready` with correct `$${}` escaping, sane intervals (`10s/5s/5x/start_period 10s`); mosquitto/api/web omitted per brief rule (no in-image probe without custom scripts) | `:100-105` |
| Personal paths / RTSP creds / API keys in file | None | whole file |

## Report completeness note

Implementer report is honest and complete: ephemeral-env method documented, dummy values labeled, daemon error quoted verbatim, secret-scan method + result recorded, clean-tree proof (`M docker-compose.yml` only + pre-existing untracked brief), assumptions/limitations/unresolved-decisions explicit, no invented endpoints (only placeholder `DATABASE_URL` shape flagged as such), no fabricated numbers. Sole gap is the Minor tool-citation note above (compose version string missing from the log; re-verified here as v5.2.0).

## Re-verification note (by this reviewer, read-only)

- `git log --oneline -3` → HEAD `74f0d6d`; `git status --short` → `M docker-compose.yml`, `?? docs/task-briefs/P0-004.md`, `?? docs/task-reports/P0-004.md`; `git diff --stat` → only `docker-compose.yml` (+134/−7).
- Greps over `docker-compose.yml`: `privileged|network_mode|cap_add|docker.sock|version\s*:|latest` → 0 hits; `ports:` only at `:55,92(comment),112,124`; `5432` only inside `DATABASE_URL` interpolation + commented override; `image:` only `:87,:108`; `deploy:/nvidia` only under `vision`.
- Live: `docker compose config --quiet` exit 0; `--services` lists 6/6; warning scan clean; `docker compose version` → v5.2.0. Ephemeral dummy env used in-session only.
- No files modified, nothing committed, no images pulled, no containers started.

## Finding counts

- Critical: 0 · Important: 0 · Minor: 2 · FYI: 3
