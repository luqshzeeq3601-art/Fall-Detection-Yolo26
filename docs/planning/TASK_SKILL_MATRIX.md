# Task → Skill → Subagent Matrix — ElderCare Vision

## Account settings reference follow-up (2026-10-04)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-SETTINGS-REFERENCE | Match the supplied Account settings section with Full HD/mobile readability | User-selected frontend-design, image-to-code, design-taste-frontend; preview-only imagegen; direct browser verification/review | COORD | Separate reference panels; truthful identity and capability states; desktop/mobile/contrast/keyboard checks; settings regressions and complete frontend gates pass |

Task brief: docs/task-briefs/P6-SETTINGS-REFERENCE.md. User prohibited subagents. Reuse the approved Phase 6 frontend scope and existing uncommitted checkout; no backend/model/dataset/dependency changes, commits or publication. Final visual QA uses synthetic account context after the live preview requested sign-in.

## Review queue reference follow-up (2026-10-04)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-REVIEW-REFERENCE | Match review queue screenshot with Full HD/mobile support | User-selected frontend-design, image-to-code, design-taste-frontend; preview-only imagegen; direct browser verification/review | COORD | Reference layout, readable colours, bounded real evidence, R/F/U/S decisions, note/skip/error checks, responsive verification and frontend gates |

Task brief: docs/task-briefs/P6-REVIEW-REFERENCE.md. Explicit no-subagent instruction overrides dispatch requirements. Reuse the existing uncommitted checkout; preserve other edits. No backend/model/dataset changes, commits or publication.

## Live Monitor reference follow-up (2026-10-04)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-LIVE-MONITOR-REFERENCE | Match Live Monitor screenshot with Full HD/mobile support | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct browser verification/review | COORD | Reference layout, readable light/dark colours, no overflow, controls and API values retained, frontend tests/typecheck/lint/build pass |

Task brief: docs/task-briefs/P6-LIVE-MONITOR-REFERENCE.md. User prohibited subagents. Reuse approved frontend skill sources and existing uncommitted checkout. Preserve workspace edits; no backend/model/dataset changes, commits or publication.

## Incidents reference follow-up (2026-10-04)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-INCIDENTS-REFERENCE | Match Incidents reference on Full HD and mobile; retain real evidence and review workflows | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct browser verification/review | COORD | Scoped tests, lint/typecheck/build pass; readable contrast; 320–1920px browser layout checks; existing edits preserved |

Task brief: docs/task-briefs/P6-INCIDENTS-REFERENCE.md. Covers existing Phase 6 rows P6-003/004/005/008 only. User prohibited subagents. Preserve the pre-existing uncommitted frontend/backend work.

## 1. Execution Policy

Primary coordinator: **Muse + Spark 1.3 xhigh**.

Primary orchestration framework: **`obra/superpowers`**.

Specialist skill sources:
- **`addyosmani/agent-skills`** for software engineering.
- **`ultralytics/skills`** for YOLO-specific work.
- **`github/awesome-copilot`** for agent evaluation/security.

Do not run Addy's global skill router alongside Superpowers. Addy skills are task-specific only.

## 2. Role Codes

| Code | Role |
|---|---|
| COORD | Muse coordinator; owns plan, dispatch, status and merge decisions |
| IMPL | Scoped implementation subagent |
| TEST | Test/failure-injection subagent |
| REVIEW | Fresh code-review subagent |
| VISION | YOLO/pose/tracking specialist |
| SEC | Security/privacy auditor |
| PERF | Performance/benchmark specialist |
| UI | React/UI specialist |
| OPS | Docker/CI/MQTT/observability specialist |
| EVAL | AI evaluation/data specialist |
| DOC | Documentation/release specialist |

## 3. Phase 0 — Repository & Quality Baseline

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P0-001 | Create repository structure | Superpowers `subagent-driven-development`; Addy `context-engineering` | IMPL | structure matches spec |
| P0-002 | Configure Python project, Ruff, pytest | Addy `source-driven-development`; Superpowers `test-driven-development` | IMPL+TEST | install/lint/tests pass |
| P0-003 | Scaffold React + TypeScript | Addy `frontend-ui-engineering` | UI+TEST | build/typecheck/test pass |
| P0-004 | Docker Compose skeleton | Addy `ci-cd-and-automation` | OPS | compose validates |
| P0-005 | `.env.example`, secret loading/redaction | Addy `security-and-hardening` | SEC+IMPL | no secret leakage |
| P0-006 | Structured logging | Addy `observability-and-instrumentation` | OPS | log tests pass |
| P0-007 | CI baseline | Addy `ci-cd-and-automation` | OPS+TEST | CI runs required checks |
| P0-008 | Phase review | Superpowers `requesting-code-review`, `verification-before-completion` | REVIEW | no blocking findings |

## 4. Phase 1 — RTSP Stream Manager

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P1-001 | Camera config model | Addy `api-and-interface-design`, `security-and-hardening` | IMPL+SEC | schema/redaction tests |
| P1-002 | RTSP capture abstraction | Addy `source-driven-development` | IMPL | source opens/closes cleanly |
| P1-003 | Bounded latest-frame queue | Superpowers `test-driven-development` | IMPL+TEST | no unbounded backlog |
| P1-004 | Stall/health state machine | Superpowers `test-driven-development` | IMPL+TEST | state transitions pass |
| P1-005 | Reconnect/backoff | Superpowers `test-driven-development` | IMPL+TEST | disconnect/reconnect pass |
| P1-006 | Capture telemetry | Addy `observability-and-instrumentation` | OPS | FPS/drop/reconnect metrics |
| P1-007 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 5. Phase 2 — YOLO26s-Pose

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P2-001 | Verify CUDA/PyTorch/Ultralytics/RTX 3070 environment | Ultralytics `yolo-models`; Addy `source-driven-development` | VISION | environment report saved |
| P2-002 | Load `yolo26s-pose.pt` | Ultralytics `yolo-inference` | VISION | prediction succeeds |
| P2-003 | Normalize 17-keypoint result contract | Ultralytics `yolo-inference`; Addy `api-and-interface-design` | VISION+IMPL | confidences preserved |
| P2-004 | Integrate pose into live pipeline | Ultralytics `yolo-inference` | VISION+IMPL | observations flow end-to-end |
| P2-005 | Add inference timing metrics | Addy `observability-and-instrumentation` | PERF | timings recorded |
| P2-006 | Pose regression tests | Superpowers `test-driven-development` | TEST+VISION | deterministic shape tests |
| P2-007 | Official-API review | Addy `source-driven-development`; Superpowers `requesting-code-review` | REVIEW+VISION | no unsupported API assumptions |

## 6. Phase 3 — ByteTrack

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P3-001 | Configure ByteTrack | Ultralytics `yolo-inference` | VISION | track IDs produced |
| P3-002 | Define `TrackObservation` interface | Addy `api-and-interface-design` | IMPL+VISION | schema tests pass |
| P3-003 | Bounded per-track history | Superpowers `test-driven-development` | IMPL+TEST | bounded/order correct |
| P3-004 | Track expiry/cleanup | Superpowers `test-driven-development` | IMPL+TEST | stale tracks removed |
| P3-005 | Multi-person/occlusion test | Ultralytics `yolo-inference` | TEST+VISION | no state leakage |
| P3-006 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 7. Phase 4 — Temporal Fall Engine

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P4-001 | Synthetic pose/track fixtures | Superpowers `test-driven-development` | TEST | normal + fall cases exist |
| P4-002 | Temporal feature extraction | Superpowers `test-driven-development` | IMPL+TEST | geometry/motion tests pass |
| P4-003 | Fall state machine | Superpowers `test-driven-development` | IMPL+TEST | transition matrix covered |
| P4-004 | Confidence score, persistence, cooldown | Superpowers `test-driven-development` | IMPL+TEST | explainable/no alert storm |
| P4-005 | Dataset manifests/eval runner | Ultralytics `yolo-datasets`; Addy `source-driven-development` | EVAL+VISION | sequence split respected |
| P4-006 | Cache derived keypoints | Ultralytics `yolo-inference`, `yolo-datasets` | VISION | metadata traceable |
| P4-007 | Calibrate thresholds on development set only | Addy `performance-optimization` | EVAL | calibration/config saved |
| P4-008 | Freeze split/config | Addy `documentation-and-adrs` | EVAL+DOC | hashes/version saved |
| P4-009 | Algorithm/leakage review | Superpowers `requesting-code-review`; Addy `doubt-driven-development` | REVIEW+VISION | no leakage/single-frame shortcut |

## 8. Phase 5 — Persistence + FastAPI

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P5-001 | PostgreSQL models + Alembic | Addy `api-and-interface-design`, `source-driven-development` | IMPL | migration tests pass |
| P5-002 | Incident repository/service | Superpowers `test-driven-development` | IMPL+TEST | immutable detector output |
| P5-003 | Evidence storage + SHA256 | Addy `security-and-hardening` | IMPL+SEC | path/storage tests pass |
| P5-004 | Health/system/camera APIs | Addy `api-and-interface-design` | IMPL+TEST | contract tests pass |
| P5-005 | Incident list/detail APIs | Addy `api-and-interface-design` | IMPL+TEST | filter/pagination/404 pass |
| P5-006 | Append-only review API | Superpowers `test-driven-development` | IMPL+TEST | detector record unchanged |
| P5-007 | WebSocket events | Addy `api-and-interface-design` | IMPL+TEST | schema/disconnect tests |
| P5-008 | Backend security audit | Addy `security-and-hardening` | SEC | blocking findings resolved |
| P5-009 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 9. Phase 6 — React Dashboard

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P6-001 | Typed API client/state boundary | Addy `frontend-ui-engineering`, `api-and-interface-design` | UI | typecheck/tests |
| P6-002 | Camera-health view | Addy `frontend-ui-engineering` | UI | status renders correctly |
| P6-003 | Incident list/filter | Addy `frontend-ui-engineering` | UI | interaction tests |
| P6-004 | Incident detail/evidence | Addy `frontend-ui-engineering` | UI | detector evidence shown |
| P6-005 | Human-review UI | Addy `frontend-ui-engineering` | UI+TEST | submit/error tests |
| P6-006 | WebSocket live updates | Addy `frontend-ui-engineering`, `api-and-interface-design` | UI | reconnect/duplicate tests |
| P6-007 | Telemetry panel | Addy `frontend-ui-engineering`, `observability-and-instrumentation` | UI+OPS | real metrics only |
| P6-008 | Browser/accessibility QA | Addy `browser-testing-with-devtools` | TEST+UI | runtime/a11y checks |
| P6-009 | Phase review | Addy `code-review-and-quality`; Superpowers `requesting-code-review` | REVIEW | gate passes |

## 10. Phase 7 — MQTT + Observability

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P7-001 | Mosquitto config | Addy `ci-cd-and-automation`, `security-and-hardening` | OPS+SEC | broker starts safely |
| P7-002 | Versioned MQTT publisher/topics | Addy `api-and-interface-design` | OPS+TEST | topic/schema tests |
| P7-003 | FPS/latency/queue/reconnect metrics | Addy `observability-and-instrumentation` | OPS | metrics available |
| P7-004 | CPU/RAM/GPU/VRAM telemetry | Addy `observability-and-instrumentation`, `source-driven-development` | OPS+PERF | target-PC metrics |
| P7-005 | Broker outage/recovery | Superpowers `systematic-debugging`, `verification-before-completion` | TEST+OPS | detector continues |
| P7-006 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 11. Phase 8 — Reliability/UAT

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P8-001 | Execute failure tests | Superpowers `systematic-debugging`, `verification-before-completion` | TEST | report saved |
| P8-002 | Execute critical UAT | Superpowers `verification-before-completion` | TEST | critical cases pass |
| P8-003 | Security/privacy audit | Addy `security-and-hardening` | SEC | Critical/High fixed |
| P8-004 | Soak/resource test | Addy `observability-and-instrumentation`, `performance-optimization` | PERF+OPS | trend report saved |
| P8-005 | Fix reliability defects | Superpowers `systematic-debugging`, `test-driven-development` | IMPL+TEST | regressions covered |
| P8-006 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 12. Phase 9 — RTX 3070 Optimization

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P9-001 | Reproducible benchmark harness | Addy `performance-optimization` | PERF | fixed input/config/output |
| P9-002 | PyTorch baseline | Ultralytics `yolo-inference`; Addy `performance-optimization` | PERF+VISION | >=3 runs saved |
| P9-003 | ONNX export/validation | Ultralytics `yolo-export` | VISION+PERF | validated + benchmarked |
| P9-004 | TensorRT FP16 export/benchmark | Ultralytics `yolo-export`; Addy `performance-optimization` | VISION+PERF | benchmark saved |
| P9-005 | Nano fallback only if gate fails | Ultralytics `yolo-models`, `yolo-export` | VISION+PERF | trade-off table if triggered |
| P9-006 | Runtime decision ADR | Addy `documentation-and-adrs` | PERF+DOC | evidence-backed decision |
| P9-007 | Benchmark integrity review | Superpowers `requesting-code-review`, `verification-before-completion` | REVIEW | no cherry-picking |

## 13. Phase 10 — Agent/VLM

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P10-001 | Async enrichment job/state | Addy `api-and-interface-design` | IMPL+TEST | detector independent |
| P10-002 | Evidence/privacy boundary | Addy `security-and-hardening` | SEC+IMPL | only approved evidence leaves |
| P10-003 | Provider client timeout/retry | Superpowers `test-driven-development`; Addy `security-and-hardening` | IMPL+TEST | outage tests pass |
| P10-004 | Structured prompt/output/versioning | Addy `api-and-interface-design` | IMPL | validation tests pass |
| P10-005 | Separate enrichment persistence/events | Superpowers `test-driven-development` | IMPL+TEST | detector unchanged |
| P10-006 | Agent quality evaluation | GitHub `agentic-eval` | EVAL | rubric report |
| P10-007 | Agent security audit | GitHub `agent-owasp-compliance`; Addy `security-and-hardening` | SEC | agent risks assessed |
| P10-008 | Phase review | Superpowers `requesting-code-review` | REVIEW | gate passes |

## 14. Phase 11 — Final Evaluation

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P11-001 | Freeze commit/model/runtime/config/splits | Superpowers `verification-before-completion`; Addy `documentation-and-adrs` | EVAL+DOC | manifest immutable |
| P11-002 | URFD final evaluation | Ultralytics `yolo-inference` | EVAL+VISION | raw TP/FP/TN/FN saved |
| P11-003 | UP-Fall robustness run | Ultralytics `yolo-datasets`, `yolo-inference` | EVAL+VISION | results saved |
| P11-004 | Local camera UAT | Superpowers `verification-before-completion` | TEST | report saved |
| P11-005 | Precision/Recall/F1/confusion/false-alert/time-to-alert | Addy `performance-optimization` | EVAL | reproducible metrics |
| P11-006 | Error/limitations analysis | Addy `doubt-driven-development` | EVAL+VISION | failure categories documented |
| P11-007 | Integrity review | Superpowers `requesting-code-review` | REVIEW | no final-test tuning |

## 15. Phase 12 — Portfolio Release

| ID | Task | Skill(s) | Owner | Done when |
|---|---|---|---|---|
| P12-001 | README from measured state only | Addy `documentation-and-adrs` | DOC | accurate setup/results |
| P12-002 | Architecture/flow/operator/dev docs | Addy `documentation-and-adrs` | DOC | docs match implementation |
| P12-003 | Reproducible demo procedure | Addy `shipping-and-launch` | DOC+TEST | fresh-run checklist |
| P12-004 | Final test/security/release gates | Addy `shipping-and-launch`, `security-and-hardening`; Superpowers `verification-before-completion` | REVIEW+SEC+TEST | all gates recorded |
| P12-005 | Evidence tables | Addy `documentation-and-adrs` | DOC+EVAL | results link to artifacts |
| P12-006 | Resume bullets from measured results | Addy `documentation-and-adrs` | DOC | no invented metrics |
| P12-007 | Whole-branch review | Superpowers `requesting-code-review`, `finishing-a-development-branch` | REVIEW | release decision |
| P12-008 | Final `PROGRESS.md` closure | Superpowers `verification-before-completion` | COORD | status/evidence final |

## 16. Universal Task Loop

```text
COORD reads task row + PROGRESS
→ create scoped task brief
→ dispatch implementer/specialist
→ dispatch focused tester/evaluator
→ dispatch fresh reviewer
→ fix Critical/Important findings
→ verification-before-completion
→ COORD updates PROGRESS.md
→ atomic commit
→ next task
```

## 17. Parallelism

Parallelize only independent tasks with disjoint files/interfaces.

Never run concurrent agents:
- editing the same state machine,
- changing the same DB/API contract,
- benchmarking the same RTX 3070 simultaneously.

## 18. Approved Phase 6 redesign follow-up (2026-10-01)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-REDESIGN-DATA | Typed demo/live boundary, query filters and socket lifecycle | frontend-ui-engineering, test-driven-development, Superpowers review/verification | IMPL+TEST+REVIEW | Boundary/socket/provider regressions pass |
| P6-REDESIGN-OVERVIEW | Shared visual system, routing shell and Overview checkpoint | User-approved frontend specialists, imagegen, browser verification | UI+TEST+REVIEW | Desktop/mobile screenshot comparison and keyboard checks |
| P6-REDESIGN-PAGES | Public/auth, operations, benchmarks/telemetry and demo settings | Same scoped frontend specialists plus deterministic logic tests | UI+TEST+REVIEW | All ten routes usable; supported API behavior and demo provenance retained |
| P6-REDESIGN-GATE | Full frontend checks, fresh review, UI docs/progress | Superpowers requesting-code-review and verification-before-completion | COORD+TEST+REVIEW | No unresolved Important/Critical issues; evidence recorded |

User instruction: leave changes uncommitted. No Python/backend/model/dataset changes. Task briefs: docs/task-briefs/P6-REDESIGN.md and P6-REDESIGN-PAGES.md.

### Approved hero reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-HERO-REFERENCE | Match the user-supplied landing hero reference | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; Superpowers implementation, fresh review and verification | UI+TEST+REVIEW | Desktop/mobile visual inspection, working auth/anchor links, typecheck/lint/tests/build pass |

Task brief: docs/task-briefs/P6-HERO-REFERENCE.md. Existing auth edits preserved; targeted Phase 6 continuation stays uncommitted.

### Approved workflow/results reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-WORKFLOW-REFERENCE | Match How it works and Results to the supplied screenshot; preserve hero | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; project implementation/review/verification workflow | UI+TEST+REVIEW | Desktop/mobile visual inspection, readable contrast, anchors, typecheck/lint/tests/build pass |

Task brief: docs/task-briefs/P6-WORKFLOW-REFERENCE.md. Scoped Phase 6 continuation reuses the existing uncommitted checkout; no commits or publication.

### Approved privacy/CTA reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-PRIVACY-REFERENCE | Match Privacy & Evidence, final CTA and notice to the supplied screenshot | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct coordinator verification | COORD | Desktop/mobile reference review, contrast/links, production source lint, typecheck/tests/build pass; unrelated lint failures reported |

Task brief: docs/task-briefs/P6-PRIVACY-REFERENCE.md. User explicitly prohibited further subagents; coordinator performs all work directly. Preserve prior edits and leave changes uncommitted.

### Approved sign-in reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-SIGNIN-REFERENCE | Match `/signin` to the supplied camera/phone/form screenshot | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct coordinator verification/review | COORD | Desktop/mobile visual checks, readable contrast, keyboard/form controls, tests/typecheck/lint/build pass |

Task brief: docs/task-briefs/P6-SIGNIN-REFERENCE.md. User explicitly prohibited subagents. Preserve existing checkout and unrelated edits; leave changes uncommitted. Google option must explain its unavailable state without authentication requests.

### Approved responsive typography follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-RESPONSIVE-TYPE | Landing/sign-in typography for Full HD desktop and mobile | Existing scoped frontend design/browser verification workflows; direct coordinator review | COORD |1920x1080 and mobile320–430px font/render checks, operable controls, typecheck/lint/tests/build pass |

Task brief:docs/task-briefs/P6-RESPONSIVE-TYPE.md. No subagents, new assets/dependencies, auth behaviour changes or commits.

### Sign-in Full HD/mobile follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-SIGNIN-RESPONSIVE | Adapt current sign-in to Full HD desktop and mobile | Existing user-selected frontend design skills; direct browser verification/review | COORD | Full HD/mobile visual review, no clipping/overflow, validation/keyboard checks, sign-in tests/lint/build pass |

Task brief: docs/task-briefs/P6-SIGNIN-RESPONSIVE.md. Preserve Google removal and existing workspace edits. No subagents or commits.

### Sign-up reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-SIGNUP-REFERENCE | Match signup to supplied screenshot with Full HD/mobile support | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct verification/review | COORD | Reference/Full HD/mobile visual and contrast checks; existing auth behavior preserved; tests/typecheck/lint/build pass |

Task brief: docs/task-briefs/P6-SIGNUP-REFERENCE.md. User prohibited subagents. Preserve existing signup API and consent defaults, signin/landing edits, and uncommitted checkout.

### Full HD sign-in reference follow-up (2026-10-03)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-SIGNIN-FULLHD-REFERENCE | Restore sign-in to supplied 1920x1080 reference; retain mobile compatibility | User-selected frontend-design, image-to-code, design-taste-frontend; reuse matching generated artwork; direct verification/review | COORD | Reference geometry, mobile containment/text contrast, focused auth checks, lint/typecheck/build pass |

Task brief: docs/task-briefs/P6-SIGNIN-FULLHD-REFERENCE.md. No subagents. Preserve recent setup gating and account-link variants, Google removal and unrelated workspace work. Leave uncommitted.

### Approved Overview reference follow-up (2026-10-04)

| ID | Task | Skills | Owner | Done when |
|---|---|---|---|---|
| P6-OVERVIEW-REFERENCE | Match Overview screenshot with Full HD/mobile readability | User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen; direct browser verification/review | COORD | Responsive/reference checks, truthful live/evidence states, tests/typecheck/lint/production build and direct review pass |

Task brief: docs/task-briefs/P6-OVERVIEW-REFERENCE.md. No subagents as explicitly requested. Preserve existing source edits and leave changes uncommitted; no backend/model/dataset/auth changes.
