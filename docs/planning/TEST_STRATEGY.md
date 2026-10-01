# Test Strategy — ElderCare Vision

## 1. Test levels

### Unit

Test pure logic:

- temporal features,
- state transitions,
- cooldown,
- confidence handling,
- event serialization,
- secret redaction,
- validation helpers.

### Component

Test:

- stream health state machine with fake sources,
- vision result adapter,
- tracker/fall-engine integration using recorded observations,
- persistence repository,
- MQTT publisher,
- Agent client with mocked provider.

### Integration

Test:

- API + PostgreSQL,
- migrations,
- WebSocket events,
- incident persistence,
- review append,
- evidence retrieval,
- MQTT broker integration.

### AI/video evaluation

Run recorded videos through the complete vision pipeline.

### System/UAT

Run camera → detector → database → dashboard end-to-end.

### Performance

Run `BENCHMARK_PLAN.md`.

### Failure injection

Run `FAILURE_TESTS.md`.

## 2. Test-first rule

For deterministic business logic:

```text
failing test
→ minimal implementation
→ passing test
→ refactor
```

Especially required for:

- fall state machine,
- cooldown/deduplication,
- API validation,
- event schemas,
- review persistence.

## 3. Test fixtures

Do not duplicate full copyrighted datasets into test fixtures.

Use:

- synthetic keypoint sequences for unit tests,
- tiny locally-created safe fixture clips,
- dataset paths configured externally for full evaluation.

## 4. Synthetic temporal fixtures

Create deterministic examples for:

- standing still,
- walking,
- sitting,
- bending,
- rapid descent then lying,
- missing keypoints,
- ID reset,
- recovery after fall.

Synthetic fixtures validate logic; they do not replace real-video evaluation.

## 5. Required CI checks

At minimum:

- Ruff
- pytest unit/integration excluding GPU-required suite
- frontend lint/typecheck/test
- migration validation
- secret scan/dependency audit if configured

GPU/video benchmarks do not have to run on every CI commit but must have reproducible local commands.

## 6. AI regression tests

Maintain a small approved regression manifest with representative clips.

On significant fall-engine changes:

- run fixed regression set,
- compare TP/FP/FN,
- block unreviewed large regressions.

## 7. Test data separation

- unit fixtures: repository-safe synthetic/local content
- development data: used for tuning
- final test data: frozen
- UAT: deployment-domain scenarios

## 8. Exit criteria

Testing phase completes only when:

- all critical UAT passes,
- final AI metrics generated,
- performance benchmark generated,
- failure tests executed,
- limitations documented.
