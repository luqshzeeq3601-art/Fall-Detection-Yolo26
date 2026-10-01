# User Acceptance Test Plan — ElderCare Vision

| ID | Scenario | Expected result | Critical |
|---|---|---|---|
| UAT-01 | Normal walking | no fall incident | Yes |
| UAT-02 | Sitting normally | no fall incident | Yes |
| UAT-03 | Standing up | no fall incident | Yes |
| UAT-04 | Bending/picking object | no fall incident | Yes |
| UAT-05 | Kneeling | no fall incident | Yes |
| UAT-06 | Intentional slow lying down | no rapid-fall classification where temporal evidence is absent; record behavior | Yes |
| UAT-07 | Controlled safe simulated fall/video | fall candidate then confirmed incident | Yes |
| UAT-08 | Person remains down | one incident; no alert storm | Yes |
| UAT-09 | Person recovers | transition to recovery/normal | Yes |
| UAT-10 | Partial occlusion | no crash; confidence/evidence reflects uncertainty | Yes |
| UAT-11 | Two people | separate track IDs where tracker permits | Yes |
| UAT-12 | Low light | system remains stable; degraded AI performance measured | No |
| UAT-13 | Camera disconnected | offline event + reconnect attempts | Yes |
| UAT-14 | Camera restored | automatic reconnect | Yes |
| UAT-15 | MQTT unavailable | core detection continues | Yes |
| UAT-16 | VLM unavailable | core detection continues | Yes |
| UAT-17 | Dashboard closed | backend/vision continue | Yes |
| UAT-18 | Backend/API restart | service recovers; persisted incidents remain | Yes |
| UAT-19 | Human review | review saved without changing detector record | Yes |
| UAT-20 | Extended runtime | no unhandled crash/resource leak beyond accepted bounds | Yes |

## Evidence to capture

For every UAT:

- date,
- Git commit,
- config version,
- model/runtime,
- camera/source,
- pass/fail,
- log/evidence reference,
- notes.

## Safety

Do not create unsafe fall simulations. Public fall datasets are sufficient for fall-event validation when physical simulation would be risky.
