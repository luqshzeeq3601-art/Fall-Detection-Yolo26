# ElderCare Vision

Privacy-preserving, edge-based fall detection for elderly care — research/portfolio proof of concept.

> **Safety disclaimer:** This system is a research/portfolio POC, not a certified medical device
> and not a guaranteed emergency service. Do not use it as a sole means of detecting falls or
> summoning help.

## Outcomes

> In progress (Phase 3 of the Phase 0–12 plan): these outcomes describe the current build; accuracy and latency benchmarks come later.

- Integrated a YOLO26s-pose detector on CUDA that normalizes every frame into 17 COCO keypoints per person, failing closed on malformed or non-finite model output.
- Assigned stable per-person IDs with ByteTrack and bounded each track's history to 60 observations, keyed by camera and track ID so identities never cross cameras.
- Hardened RTSP capture with a 2-frame drop-oldest queue, exponential reconnect backoff from 1 s to 30 s, and credential redaction across logs and telemetry.
- Validated crossing, occlusion, gap-return, and multi-camera scenarios with a 626-test pytest suite that runs in under 5 s without a GPU.

## Planning

Authoritative planning inputs live in the sibling planning pack
(`eldercare_muse_subagent_pack/`): PRD, architecture, AI spec, dataset plan,
benchmark plan, test strategy, and implementation plan (Phases 0–12).

## Status

Phases 0–2 complete (camera capture, pose inference); Phase 3 tracking awaits its phase review. No benchmark
numbers, API contracts, or detection thresholds are claimed yet. All results will be recorded from measured runs only.

## Layout

Per `eldercare_muse_subagent_pack/REPOSITORY_STRUCTURE.md`. See `AGENTS.md` for agent rules.
