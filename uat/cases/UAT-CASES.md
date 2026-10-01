# UAT Cases — frozen from `UAT_PLAN.md` (P8-002)

> Authority: `docs/planning/UAT_PLAN.md`. This table is verbatim
> plus the deterministic harness used in `tests/system/test_uat_critical.py`.
> No cases added, removed, or reworded. Lab/synthetic results are NOT clinical
> or real-world validation.

| ID | Scenario (verbatim) | Expected result (verbatim) | Critical | Harness |
|---|---|---|---|---|
| UAT-01 | Normal walking | no fall incident | Yes | walking sequence → machine |
| UAT-02 | Sitting normally | no fall incident | Yes | sitting sequence → machine |
| UAT-03 | Standing up | no fall incident | Yes | seated→standing interpolation → machine |
| UAT-04 | Bending/picking object | no fall incident | Yes | bending sequence → machine |
| UAT-05 | Kneeling | no fall incident | Yes | sustained bend-apex hold → machine |
| UAT-06 | Intentional slow lying down | no rapid-fall classification where temporal evidence is absent; record behavior | Yes | slow-liedown sequence → machine, final state recorded |
| UAT-07 | Controlled safe simulated fall/video | fall candidate then confirmed incident | Yes | fall sequence → candidate transition then confirm + event |
| UAT-08 | Person remains down | one incident; no alert storm | Yes | fall + extended down frames → exactly 1 event |
| UAT-09 | Person recovers | transition to recovery/normal | Yes | fall-with-recovery → RECOVERY/NORMAL |
| UAT-10 | Partial occlusion | no crash; confidence/evidence reflects uncertainty | Yes | walking with dropped frames + low-confidence keypoints |
| UAT-11 | Two people | separate track IDs where tracker permits | Yes | manager, two tracks, independent states |
| UAT-12 | Low light | system remains stable; degraded AI performance measured | No | low-confidence walking proxy (rationale in report) |
| UAT-13 | Camera disconnected | offline event + reconnect attempts | Yes | health poll → OFFLINE + controller attempts |
| UAT-14 | Camera restored | automatic reconnect | Yes | capture opens → attempt True, counters reset, ONLINE |
| UAT-15 | MQTT unavailable | core detection continues | Yes | incident persists + evidence while broker dead |
| UAT-16 | VLM unavailable | core detection continues | Yes | flow completes, no enrichment, detector intact |
| UAT-17 | Dashboard closed | backend/vision continue | Yes | API record/query, zero WS connections |
| UAT-18 | Backend/API restart | service recovers; persisted incidents remain | Yes | sqlite FILE restart, app rebuild |
| UAT-19 | Human review | review saved without changing detector record | Yes | field snapshot compare across review |
| UAT-20 | Extended runtime | no unhandled crash/resource leak beyond accepted bounds | Yes | bounded CI edition (P8-002) + full soak (P8-004) |
