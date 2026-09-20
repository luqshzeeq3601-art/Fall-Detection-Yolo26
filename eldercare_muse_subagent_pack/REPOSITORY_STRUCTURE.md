# Repository Structure — ElderCare Vision

```text
eldercare-vision/
├── AGENTS.md
├── SKILL_SOURCES.md
├── SUBAGENT_ORCHESTRATION.md
├── TASK_SKILL_MATRIX.md
├── PROGRESS.md
├── METHODOLOGY.md
├── README.md
├── PROJECT_BRIEF.md
├── PRD.md
├── CONSTRAINTS.md
├── ACCEPTANCE_CRITERIA.md
├── RISK_REGISTER.md
├── ARCHITECTURE.md
├── AI_SPEC.md
├── DATASET_PLAN.md
├── MODEL_EVALUATION.md
├── BENCHMARK_PLAN.md
├── TEST_STRATEGY.md
├── UAT_PLAN.md
├── FAILURE_TESTS.md
├── IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── src/
│   └── eldercare/
│       ├── vision/
│       │   ├── stream/
│       │   ├── pose/
│       │   ├── tracking/
│       │   └── telemetry/
│       ├── fall_engine/
│       │   ├── features/
│       │   ├── state_machine/
│       │   └── config/
│       ├── incidents/
│       ├── agents/
│       ├── mqtt/
│       ├── api/
│       ├── db/
│       └── common/
│
├── frontend/
│   ├── src/
│   └── ...
│
├── config/
│   ├── cameras.example.yaml
│   ├── fall_detection.yaml
│   └── logging.yaml
│
├── datasets/
│   ├── README.md
│   ├── manifests/
│   └── derived/
│
├── benchmarks/
│   ├── scripts/
│   └── results/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── system/
│   ├── fixtures/
│   └── ai_regression/
│
├── uat/
│   ├── cases/
│   └── reports/
│
├── deployment/
│   ├── docker/
│   └── mosquitto/
│
├── scripts/
│   ├── dataset/
│   ├── benchmark/
│   └── dev/
│
└── docs/
    ├── adr/
    ├── architecture/
    ├── api/
    └── reports/
```

## Principles

- Python package code lives under `src/`.
- Fall logic is independent from FastAPI.
- Dataset binaries are outside Git.
- Derived cache is reproducible and ignored when large.
- Benchmark raw output is preserved where reasonable.
- ADRs document architectural changes.
