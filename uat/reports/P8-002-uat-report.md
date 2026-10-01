# UAT Execution Report — P8-002 (critical cases UAT-01…UAT-20)

> Executable evidence: `tests/system/test_uat_critical.py` (20/20 PASS).
> Case authority: `uat/cases/UAT-CASES.md` ← `UAT_PLAN.md` (verbatim).
> Lab/synthetic results only — NOT clinical or real-world validation.

## Environment
- Date: 2026-09-23
- Commit (execution baseline): `c6ce4cf` (P8-001 closure; UAT code added after)
- Config: `config/fall_detection.yaml` (frozen development calibration, P4-008)
- Model/runtime: `yolo26s-pose.pt` as configured detector identity; weights NOT
  loaded in CI (no torch/CUDA/GPU on this machine) — pose input is synthetic
- Camera/source: synthetic fixtures (`tests/fixtures/synthetic_fall_fixtures.py`),
  sqlite memory/FILE, FakeMqttTransport, TestClient — no real infrastructure

## Results

| ID | Scenario | Expected | Actual | Verdict | Evidence / notes |
|---|---|---|---|---|---|
| UAT-01 | Normal walking | no fall incident | 0 events, NORMAL | PASS | `test_uat_01_normal_walking` |
| UAT-02 | Sitting normally | no fall incident | 0 events, NORMAL | PASS | `test_uat_02_sitting_normally` |
| UAT-03 | Standing up | no fall incident | 0 events, NORMAL | PASS | reverse-sit interpolation harness |
| UAT-04 | Bending/picking object | no fall incident | 0 events, not confirmed | PASS | `test_uat_04_bending_picking_object` |
| UAT-05 | Kneeling | no fall incident | 0 events, not confirmed | PASS | bend-apex hold (zero descent velocity) |
| UAT-06 | Intentional slow lying down | no rapid-fall classification; record behavior | no confirm; final non-confirmed state recorded in assertion | PASS | `test_uat_06_intentional_slow_lying_down` |
| UAT-07 | Controlled fall | candidate then confirmed | DESCENT_CANDIDATE → FALL_CONFIRMED, exactly 1 event | PASS | transition order asserted |
| UAT-08 | Person remains down | one incident; no storm | 1 event + 0 extra over 30 down frames | PASS | `test_uat_08_person_remains_down_single_incident` |
| UAT-09 | Person recovers | recovery/normal | RECOVERY/NORMAL | PASS | fall-with-recovery sequence |
| UAT-10 | Partial occlusion | no crash; uncertainty | no crash, no confirm (gaps + low-conf) | PASS | uncertainty-penalty unit-covered in P4 |
| UAT-11 | Two people | separate tracks | track1 clean, track2 confirms, independent | PASS | manager-level |
| UAT-12 | Low light (non-critical) | stable; degraded AI measured | stable, no confirm at conf 0.25 | PASS | low-confidence proxy; rationale: photometric loss ≈ keypoint-confidence loss per AI_SPEC §8 |
| UAT-13 | Camera disconnected | offline + reconnect attempts | OFFLINE + attempts=1 | PASS | health poll + controller |
| UAT-14 | Camera restored | auto reconnect | attempt True, counters reset, ONLINE | PASS | scripted capture opens |
| UAT-15 | MQTT unavailable | core continues | persisted (score intact), delivery False | PASS | dead-broker incident flow |
| UAT-16 | VLM unavailable | core continues | flow completes, enrichments empty, detector intact | PASS | structural: no provider path in build |
| UAT-17 | Dashboard closed | backend continues | record + query OK, 0 WS connections | PASS | TestClient, manager count 0 |
| UAT-18 | Backend restart | recovers; incidents remain | FILE DB reopen, score intact, /health ok | PASS | tmp_path sqlite |
| UAT-19 | Human review | saved, detector unchanged | 6-field snapshot identical, 1 review | PASS | service-level compare |
| UAT-20 | Extended runtime (bounded CI edition) | no crash/leak beyond bounds | 300 updates + 60 persists, 0 exceptions, bounded stores, <120 s | PASS | full soak in P8-004 |

## Summary
- Critical cases: 19/19 PASS. Non-critical: 1/1 PASS. FAIL: 0.
- No FAIL → no fix loop triggered. Full soak evidence deferred to P8-004 (owned).
