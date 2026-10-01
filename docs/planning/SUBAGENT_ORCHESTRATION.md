# Subagent Orchestration — Muse + Spark 1.3 xhigh

## 1. Coordinator

Use **Muse with Spark 1.3 at xhigh effort** as the single project coordinator.

Coordinator responsibilities:
- read requirements and current progress,
- choose the current task,
- load only required skills,
- dispatch fresh subagents,
- resolve dependency conflicts,
- collect test/review evidence,
- update `PROGRESS.md`,
- decide when a task/phase is complete.

## 2. Primary Orchestration Framework

Use **`obra/superpowers`**.

It is selected because its GitHub documentation explicitly includes:
- native Muse plugin support,
- `subagent-driven-development`,
- task-by-task fresh implementers,
- fresh code-review subagents,
- worktree isolation,
- verification-before-completion.

### Verified Muse installation

```bash
git clone https://github.com/obra/superpowers.git
cd superpowers
muse plugins install ./
muse plugins approve superpowers
```

Restart Muse after installation.

## 3. Router Rule

Superpowers is the only global orchestration/router framework.

Do not simultaneously enable Addy's `using-agent-skills` router.

Use Addy/Ultralytics/GitHub skills only when assigned by `TASK_SKILL_MATRIX.md`.

## 4. Required Subagent Pattern

### Normal task

```text
Coordinator
→ Implementer
→ Test Engineer
→ Fresh Reviewer
→ Coordinator verification
```

### AI/CV task

```text
Coordinator
→ Vision Specialist
→ Test/Evaluation Specialist
→ Fresh Reviewer
→ Coordinator
```

### Security-sensitive task

```text
Coordinator
→ Implementer
→ Test Engineer
→ Security Auditor
→ Fresh Reviewer
→ Coordinator
```

### Benchmark task

```text
Coordinator
→ Performance + Vision Specialist
→ Benchmark verification
→ Independent Reviewer
→ Coordinator
```

## 5. Fresh Context

A reviewer receives only:
- task ID,
- task brief,
- relevant spec/acceptance criteria,
- diff/base/head commit,
- test/benchmark evidence.

Do not give the reviewer the implementer's reasoning transcript.

## 6. Task Brief

Before dispatch, create:

```text
docs/task-briefs/<TASK-ID>.md
```

Template:

```md
# TASK-ID — Name
## Purpose
## Requirements
## Allowed files
## Inputs/interfaces
## Expected outputs
## Skills to use
## Acceptance criteria
## Tests required
## Forbidden scope
## Report path
```

## 7. Implementation Report

Every implementation subagent writes:

```text
docs/task-reports/<TASK-ID>.md
```

It must contain:
- files changed,
- behavior implemented,
- tests/commands run,
- PASS/FAIL,
- assumptions,
- known limitations,
- unresolved decisions.

## 8. Review Report

Reviewer writes:

```text
docs/reviews/<TASK-ID>-review.md
```

Severity:
- Critical — blocks.
- Important — blocks.
- Minor — non-blocking improvement.
- FYI — informational.

A task cannot complete with unresolved Critical or Important findings.

## 9. Fix Loop

```text
finding
→ fresh fix subagent
→ focused regression test
→ scoped re-review
→ verification
```

Do not let the reviewer implement its own fix.

## 10. Concurrency

Recommended maximum:
- 2 independent implementation subagents,
- plus tester/reviewer roles.

Avoid excessive parallelism because this project has many shared contracts.

## 11. Worktrees

Use Superpowers `using-git-worktrees`.

Example:

```text
main
├─ worktree/task-P2-003
└─ worktree/task-P6-002
```

Tasks touching the same subsystem must not run concurrently.

## 12. Skill Selection

For each task:
1. locate ID in `TASK_SKILL_MATRIX.md`,
2. load listed skill(s),
3. do not add unrelated skills,
4. document any mapping change.

## 13. Spark 1.3 / Effort

The coordinator remains **Spark 1.3 xhigh**.

Use fresh Spark 1.3 child agents for implementation/review. If Muse exposes per-child effort controls, reserve the highest reasoning for architecture, fall-algorithm logic, security, benchmark interpretation and final review. Do not assume such override exists unless Muse exposes it.

## 14. Progress Ownership

Only the coordinator updates `PROGRESS.md`.

After every accepted task:
1. verify reports,
2. mark task complete,
3. update phase percentage,
4. record evidence,
5. set next task,
6. commit progress with the accepted change.

## 15. Stop Conditions

Mark `BLOCKED` when:
- requirements conflict,
- official API differs materially from plan,
- data/license is unresolved,
- required test is unreliable,
- security boundary unresolved,
- hardware unavailable for a mandatory benchmark,
- Critical review issue remains unresolved.
