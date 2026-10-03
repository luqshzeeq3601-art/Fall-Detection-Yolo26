# API Specification — ElderCare Vision

Base path:

```text
/api/v1
```

## 1. Health

### `GET /health`

Liveness.

Response:

```json
{"status":"ok"}
```

### `GET /ready`

Readiness of required dependencies.

Example:

```json
{
  "status": "ready",
  "database": "ready",
  "vision_service": "ready"
}
```

Optional services such as MQTT/VLM must be reported but must not necessarily make core readiness fail.

## 2. System status

### `GET /system/status`

Returns:

- service versions,
- model name/version,
- config version,
- camera count,
- vision FPS,
- inference latency summary,
- GPU/RAM summary,
- optional integration status.

No secrets.

## 3. Cameras

### `GET /cameras`

Returns camera metadata and health.

### `GET /cameras/{camera_id}`

Fields:

```json
{
  "id": "cam-01",
  "name": "Demo Camera",
  "status": "online",
  "last_frame_at": "ISO-8601",
  "last_heartbeat_at": "ISO-8601",
  "reconnect_count": 1
}
```

RTSP URL must not be returned.

## 4. Incidents

### `GET /incidents`

Query:

- `camera_id`
- `status`
- `review_label`
- `needs_review` (completed uncertain/no-fall/unclear enrichment and no human review)
- `from`
- `to`
- `limit`
- `offset` (implemented pagination used by the frontend)
- `cursor`

### `GET /incidents/{incident_id}`

Returns:

- detector decision,
- temporal evidence,
- evidence references,
- human reviews,
- optional enrichment.

### `POST /incidents/{incident_id}/reviews`

Request:

```json
{
  "label": "confirmed_fall",
  "notes": "Controlled test case."
}
```

Allowed labels:

- `confirmed_fall`
- `non_fall`
- `uncertain`

## 5. Evidence

### `GET /incidents/{incident_id}/evidence/{evidence_id}`

Must validate ownership/path mapping through database metadata.

Do not accept arbitrary filesystem paths.

## 6. WebSocket

### `WS /ws/events`

Event envelope:

```json
{
  "event_id": "uuid",
  "event_type": "fall.confirmed",
  "occurred_at": "ISO-8601",
  "camera_id": "cam-01",
  "incident_id": "uuid",
  "payload": {}
}
```

## 7. Error model

All API errors use a consistent structure:

```json
{
  "error": {
    "code": "INCIDENT_NOT_FOUND",
    "message": "Incident not found",
    "request_id": "uuid"
  }
}
```

Do not expose stack traces to clients.

## 8. Security requirements

- validate all identifiers,
- CORS allowlist,
- redact secrets,
- evidence routes cannot traverse filesystem,
- review input length limits,
- authentication can be added post-MVP but API must be structured so auth middleware can be introduced without breaking contracts.
