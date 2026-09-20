# AGENTS.md — ElderCare Vision

These instructions are authoritative for AI coding agents working in this repository.

## 1. Read before coding

Required reading order:

1. `METHODOLOGY.md`
2. `PROGRESS.md`
3. `TASK_SKILL_MATRIX.md`
4. `SUBAGENT_ORCHESTRATION.md`
5. `SKILL_SOURCES.md`
6. `PRD.md`
7. `CONSTRAINTS.md`
8. `ARCHITECTURE.md`
9. `AI_SPEC.md`
10. `DATASET_PLAN.md`
11. `TEST_STRATEGY.md`
12. `ACCEPTANCE_CRITERIA.md`
13. `IMPLEMENTATION_PLAN.md`

Do not invent architecture that conflicts with these documents.

## 2. Development methodology and orchestration

Primary environment:

```text
Muse + Spark 1.3 xhigh
```

Use **`obra/superpowers` as the primary orchestration framework**.

Required orchestration skills:

- `subagent-driven-development`
- `using-git-worktrees`
- `test-driven-development`
- `systematic-debugging`
- `requesting-code-review`
- `verification-before-completion`
- `finishing-a-development-branch`

Use Addy Osmani, Ultralytics and GitHub skills only as task-specific specialist workflows defined in `TASK_SKILL_MATRIX.md`.

Do not activate a second global router alongside Superpowers.

## 3. Ultralytics tasks

If installed, use official **Ultralytics Agent Skills** for:

- model selection,
- dataset formatting,
- inference,
- tracking,
- export,
- benchmarking.

Prefer official Ultralytics documentation over third-party snippets.

The fixed default model is:

```text
yolo26s-pose.pt
```

Do not change it without benchmark evidence and ADR update.

## 4. Source-driven development

For version-sensitive library behavior:

1. inspect installed package/version,
2. consult official docs,
3. implement,
4. record version-sensitive assumptions.

Do not rely on remembered API syntax when official documentation is available.

## 5. Scope discipline

Work on one approved phase from `IMPLEMENTATION_PLAN.md` at a time.

Do not:

- prematurely add multi-camera support,
- add face recognition,
- add medical diagnosis,
- add cloud architecture not required by the phase,
- train new models before the baseline is measured.

## 6. AI rules

- YOLO pose is not a single-frame fall classifier.
- Fall detection is temporal.
- Missing keypoints must never be fabricated.
- Preserve raw confidence.
- Thresholds belong in config.
- Store evidence explaining confirmed decisions.
- Never tune on final-test data.
- No dataset leakage.

## 7. Agent/VLM rules

Agent/VLM is asynchronous and optional.

Never:

- place VLM calls in the per-frame loop,
- make core detection depend on provider uptime,
- allow generated text to overwrite detector evidence,
- let generated text claim injury/medical severity,
- send continuous video to a provider.

## 8. Performance rules

Target GPU: RTX 3070.

Optimization path:

```text
PyTorch
→ ONNX
→ TensorRT FP16
```

OpenVINO is optional CPU fallback.

Before optimizing:

- establish correctness,
- save a fixed benchmark source,
- measure baseline.

Every performance claim must record:

- hardware,
- model,
- runtime,
- input resolution,
- commit,
- config,
- raw result artifact.

## 9. Python rules

Required:

- type hints on public APIs,
- small testable core functions/classes,
- Pydantic boundary validation,
- Ruff,
- pytest,
- structured logging.

Forbidden:

- bare `except`,
- silent exception swallowing,
- unbounded queues,
- blocking VLM/database/network calls in frame loop,
- magic fall thresholds scattered through code.

## 10. API/data rules

- `/api/v1` versioned API.
- Database changes require Alembic migration.
- Human review is append-only.
- Original detector output is immutable.
- Evidence file access must map through database IDs; no arbitrary path parameters.
- RTSP credentials must be redacted.

## 11. Security rules

Never commit:

- `.env`
- API keys
- passwords
- RTSP credentials
- private datasets
- local personal paths
- raw sensitive recordings.

Do not disable security checks to make tests pass.

## 12. Git rules

- atomic commits,
- one logical change per commit,
- tests with behavior changes,
- no unrelated formatting churn,
- preserve user edits,
- do not rewrite history unless explicitly requested.

## 13. Definition of completion

Before saying a task is complete:

1. run relevant tests,
2. inspect failures,
3. run lint/type checks required by component,
4. verify acceptance criteria,
5. verify no secret/data leak,
6. update docs if interfaces/architecture changed.

"Looks correct" is not evidence.

## 14. Benchmark honesty

Do not place fabricated or estimated achievement numbers into:

- README,
- report,
- resume bullets,
- screenshots,
- portfolio claims.

Targets may be stated as targets. Results must come from measured runs.

## 15. Safety positioning

This system is a research/portfolio POC, not a certified medical device or guaranteed emergency service.

All user-facing documentation must preserve this boundary.

## 16. Subagent execution

Follow `SUBAGENT_ORCHESTRATION.md`.

For every task:
1. locate its row in `TASK_SKILL_MATRIX.md`,
2. create a task brief,
3. dispatch a fresh implementer/specialist,
4. verify through test/evaluation,
5. dispatch a fresh reviewer,
6. resolve all Critical/Important findings,
7. run verification-before-completion,
8. update `PROGRESS.md`,
9. commit atomically.

Only the coordinator updates project status.

## 17. Skill sources

Only use approved sources in `SKILL_SOURCES.md` unless a new source is explicitly reviewed and added.
