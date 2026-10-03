# P6-WORKFLOW-REFERENCE — Browser and visual verification

Date: 2026-10-03. Scope: How it works and Results only, following the user's clarification. Hero, auth and privacy edits were preserved.

## Final browser evidence

Installed Chrome, bundled Playwright, Vite 8.3.0 dev preview on localhost port 5175. Local script `.task-assets/workflow-reference/verify.cjs`; screenshots and structured evidence under `frontend/output/playwright/workflow-reference/`. Screenshot artifacts remain local, outside shipped source.

- 1904, 1440, 1366, 1024, 768, 390 and 320px widths: PASS for horizontal overflow, loaded illustrations, text clipping, and artwork/text separation.
- Artwork collision checks use PNG opaque bounds (alpha >=128), natural image dimensions, object-fit containment and browser text range rectangles; transparent padding does not count as painted artwork. Final desktop/laptop/mobile screenshots were visually inspected by coordinator.
- Both navigation anchors, report destination, report keyboard focus and existing signup CTA route: PASS.
- Dark preference retains navy headings on the explicit light reference canvas. Reduced-motion preference used; no new animation added.
- No JavaScript exceptions or unexpected failed HTTP responses. Auth response was synthetically intercepted with 401 to exercise signed-out state without an account.

## Readability

Computed foreground colours checked against conservative light background bounds: #d7e8fa/#e1f6f0 for narrative and #f4f8ff for near-white cards. Minimum body/note/kicker ratio: 4.78:1; card body ratio: 5.61:1; large blue emphasis: 4.03:1. These pass the 4.5:1 ordinary-text and 3:1 large-text thresholds documented by [W3C](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). This is a scoped contrast check, not a claim of a full WCAG audit.

## Reference comparison

Reproduces the two-row composition, connected workflow, numbered colour-coded icons, isolated 3D art, navy/blue heading emphasis, pale blue/mint canvas, left evaluation narrative and three right metric cards. Desktop workflow paragraphs fit two lines; metric cards are 265px tall. Smaller screens adapt the illustration row and stack cards. Generated illustrations and locally bundled font are interpretations of the reference, not pixel-identical image copies.

## Assets and prompts

Built-in imagegen, transparent outputs, original generation files preserved. Bundled assets: `frontend/src/assets/workflow-camera.png`, `workflow-movement.png` and `workflow-review.png`.

Prompt set: match the supplied screenshot's (1) glossy white/periwinkle cylindrical camera with navy lens and blue disc; (2) layered translucent blue video frames with synthetic cyan articulated figure and white play symbol; (3) two frosted white avatar/pulse tiles and mint check. Each prompt requested an isolated transparent object, soft studio lighting, no outer card, text, watermark, real person or actual detector evidence. Full prompts are recorded in the tool calls. ASSETS.md records each selected asset's generation brief and provenance.

Result-card waves are decorative CSS shapes, excluded from the accessibility tree. All benchmark values, the qualification paragraph and report destination remain sourced from existing BENCHMARK data. No backend, model, dataset or dependency change was made by this task. No commit, push or deployment.

## Concurrent workspace activity

Other workspace activity changed signin-art.png and added screen_fullhd.png/screen_mobile.png during execution. These files were not created or edited by this task and were preserved. Existing frontend/auth changes remain uncommitted.
