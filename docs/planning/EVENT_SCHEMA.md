# Event Schema — ElderCare Vision

## 1. Common envelope

```json
{
  "event_id": "uuid",
  "event_type": "fall.confirmed",
  "schema_version": "1.0",
  "occurred_at": "2026-09-19T12:00:00Z",
  "source": "vision-service",
  "camera_id": "cam-01",
  "incident_id": "uuid-or-null",
  "payload": {}
}
```

## 2. Event types

### Camera

- `camera.online`
- `camera.degraded`
- `camera.offline`
- `camera.reconnected`

### Fall engine

- `fall.candidate`
- `fall.confirmed`
- `fall.recovered`

### Incident

- `incident.persisted`
- `incident.reviewed`

### Agent

- `agent.enrichment_queued`
- `agent.enrichment_completed`
- `agent.enrichment_failed`

### System

- `service.degraded`
- `service.recovered`

## 3. `fall.confirmed` payload

```json
{
  "track_id": "42",
  "fall_score": 0.87,
  "model_name": "yolo26s-pose.pt",
  "config_version": "fall-config-v1",
  "evidence": {
    "rapid_vertical_drop": true,
    "orientation_change": true,
    "low_pose_confidence": false,
    "ground_posture_persisted": true
  }
}
```

Numbers shown above are schema examples only, not measured project results.

## 4. MQTT topic convention

```text
eldercare/{site_id}/{camera_id}/events/fall
eldercare/{site_id}/{camera_id}/health
eldercare/{site_id}/{camera_id}/agent
```

QoS:

- health: QoS 0 or 1
- confirmed fall event: QoS 1
- do not make detector success dependent on broker acknowledgement

## 5. Versioning

Breaking payload changes require a new schema version.

Consumers must ignore unknown additive fields.
