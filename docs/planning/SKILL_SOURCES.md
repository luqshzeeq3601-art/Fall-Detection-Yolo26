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

## 8. User-selected hero specialists (2026-10-03)

For P6-HERO-REFERENCE, the user explicitly selected frontend-design, image-to-code and design-taste-frontend. The attached screenshot controls the design, including its three-line heading, supporting paragraph and blue/mint glass artwork. Built-in imagegen creates a local synthetic illustration; it does not supply detector evidence or performance claims. Superpowers remains the orchestration framework.

## 9. User-selected workflow/results specialists (2026-10-03)

For P6-WORKFLOW-REFERENCE, the user explicitly selected frontend-design, image-to-code and design-taste-frontend and clarified that only How it works and Results should change. The supplied screenshot controls composition. Built-in imagegen supplies three local synthetic decorative illustrations. Use the project implementer, verification and fresh reviewer sequence with available native roles; requested Muse/Spark runtime and Superpowers skill files are unavailable in this Codex session. No second global router is enabled.

## 10. Privacy/CTA reference follow-up (2026-10-03)

P6-PRIVACY-REFERENCE uses the same three user-selected design skills and built-in imagegen for an abstract decorative background. No new router or skill source. The user prohibited further subagents; the coordinator implements, tests and reviews directly. The supplied screenshot controls layout; readability and existing privacy/research qualifications remain required.

## 11. Sign-in reference follow-up (2026-10-03)

P6-SIGNIN-REFERENCE uses user-selected frontend-design, image-to-code and design-taste-frontend, plus built-in imagegen for one synthetic scene background. Screenshot composition takes precedence over generic design defaults. Use existing native CSS, local typography and Lucide icons. The user prohibited subagents; coordinator implementation, verification and direct review apply. No new global router or provider integration.
