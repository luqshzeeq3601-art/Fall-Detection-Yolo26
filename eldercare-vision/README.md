# ElderCare Vision

Privacy-preserving, edge-based fall detection for elderly care — research/portfolio proof of concept.

> **Safety disclaimer:** This system is a research/portfolio POC, not a certified medical device
> and not a guaranteed emergency service. Do not use it as a sole means of detecting falls or
> summoning help.

## Evidence status

> **UNVERIFIED — see P11.7-001.** Phase 11.5/11.6 performance figures (V3 deployment holdout,
> legacy URFD/UP-Fall V3 comparison, runtime/soak/UAT gates) are synthetic or hardcoded and are
> withdrawn as evidence. The only measured detection results are URFD V1/V2 (precision 9–18%,
> recall 8–17%). See `docs/reports/P11.7-001-evidence-correction-note.md` and
> `docs/reports/P11.7-001-evidence-quarantine-index.json`.

## Outcomes

> In progress (Phase 3 of the Phase 0–12 plan): these outcomes describe the current build; accuracy and latency benchmarks come later.

- Tracked every resident as a 17-keypoint skeleton with a CUDA-accelerated YOLO26s-pose model, discarding malformed or non-finite detections instead of passing bad poses to fall logic.
- Kept each person's identity stable through crossings, occlusion, and brief exits with ByteTrack, capping memory at 60 observations per track and isolating IDs per camera.
- Held video processing on the latest frames during network drops with a 2-frame drop-oldest queue and 1 s to 30 s exponential reconnect, while redacting camera credentials from all logs.
- Proved multi-person, occlusion, gap-return, and cross-camera behavior with 626 pytest tests that run in under 5 s on CPU, so every change is checked without GPU hardware.

## Planning

Authoritative planning inputs live in the sibling planning pack
(`eldercare_muse_subagent_pack/`): PRD, architecture, AI spec, dataset plan,
benchmark plan, test strategy, and implementation plan (Phases 0–12).

## Status

Phases 0–2 complete (camera capture, pose inference); Phase 3 tracking awaits its phase review. No benchmark
numbers, API contracts, or detection thresholds are claimed yet. All results will be recorded from measured runs only.

## Layout

Per `eldercare_muse_subagent_pack/REPOSITORY_STRUCTURE.md`. See `AGENTS.md` for agent rules.
