# Approved GitHub Skill Sources

Verified on **2026-09-20**.

## 1. `obra/superpowers`

Repository: https://github.com/obra/superpowers

Snapshot:
- ~288.7k stars
- ~25.8k forks

Use for:
- Muse-native orchestration
- subagent-driven development
- worktrees
- TDD
- debugging
- review
- verification

**Role:** only global router/orchestrator.

## 2. `addyosmani/agent-skills`

Repository: https://github.com/addyosmani/agent-skills

Snapshot:
- ~96.8k stars
- ~10.2k forks

Use selected individual skills:
- `source-driven-development`
- `api-and-interface-design`
- `frontend-ui-engineering`
- `security-and-hardening`
- `performance-optimization`
- `observability-and-instrumentation`
- `ci-cd-and-automation`
- `documentation-and-adrs`
- `context-engineering`
- `code-review-and-quality`
- `browser-testing-with-devtools`
- `shipping-and-launch`
- `doubt-driven-development`

Do not use its global router alongside Superpowers.

## 3. `ultralytics/skills`

Repository: https://github.com/ultralytics/skills

Official Ultralytics-maintained skills.

Use:
- `yolo-models`
- `yolo-datasets`
- `yolo-inference`
- `yolo-export`

Do not use `yolo-training`/`yolo-tuning` unless pose fine-tuning becomes an approved future task.

## 4. `github/awesome-copilot`

Repository: https://github.com/github/awesome-copilot

Use:
- `agentic-eval`
- `agent-owasp-compliance`

Use these in Phase 10 for Agent/VLM evaluation and security.

## 5. Authority Order

When sources disagree:
1. project PRD/constraints/ADRs define intended behavior,
2. installed runtime + official docs define actual API behavior,
3. official vendor skills define vendor workflow,
4. specialist skills guide engineering process.

Major changes require an ADR update.

## 6. Muse Installation Note

Native Muse installation was explicitly verified only for Superpowers in the checked GitHub documentation.

The Addy, Ultralytics and GitHub repositories provide portable `SKILL.md` content, but a Muse-specific install command was not verified from their checked READMEs. Load/vendor only the required skills through Muse's current supported skill mechanism rather than inventing an install command.

## 7. User-approved frontend specialists (2026-10-01)

For P6-REDESIGN only, the user explicitly selected image-to-code, frontend-design, high-end-visual-design, antislop-ui and frontend-ui-engineering. Their supplied mockups and FRONTEND_PROMPT.md take precedence over generic visual defaults in these skills. Built-in imagegen was approved for local 3D assets. Superpowers remains the sole orchestration framework; these additions are scoped design/accessibility workflows, not additional routers.
