# P7-002 — Review (fresh Reviewer)

## Scope
Versioned MQTT publisher/topics vs EVENT_SCHEMA.md §§1/2/4/5 and the P7-002 brief.

## Findings
- Critical: none.
- Important: none.
- Minor:
  - M1: Camera-less events publish under the literal `system` camera segment
    (envelope allows null `camera_id`; topics require a segment). Documented
    behavior, not a contract deviation — acceptable.
- FYI:
  - F1: `incident.*`/`service.*` route to the `health` topic by documented
    mapping (no dedicated incident topic exists in EVENT_SCHEMA §4).
  - F2: Production paho adapter is specified by protocol, not implemented —
    correct call while paho-mqtt stays out of the locked environment.
  - F3: QoS 2 accepted by validation though defaults never exceed 1.

## Checks
- Topic strings byte-match EVENT_SCHEMA roots; QoS defaults inside allowances;
  determinism + safety probes verified in tests; settings change is additive
  (defaults + summary + example only).

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P7-003.
