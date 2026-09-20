# Data Flow — ElderCare Vision

## 1. Live frame flow

```text
RTSP packet
→ decoder
→ newest decoded frame
→ YOLO26s-Pose
→ ByteTrack
→ per-person pose observation
→ temporal feature extraction
→ fall state machine
```

Only the newest useful frame should be processed when the pipeline is overloaded.

## 2. Temporal observation flow

For each `track_id`, maintain a bounded sliding history of:

- timestamp,
- bounding box,
- torso/keypoint geometry,
- hip/shoulder centers,
- vertical displacement,
- orientation,
- keypoint confidence.

The history is used to infer change over time rather than classify one image as a fall.

## 3. Confirmed incident flow

```text
FALL_CONFIRMED
→ create incident ID
→ save detector metadata + evidence features
→ save snapshot
→ commit database transaction
→ publish WebSocket event
→ attempt MQTT publish
→ enqueue optional Agent/VLM task
```

Persistence occurs before optional enrichment.

## 4. Agent flow

```text
incident ID
→ load approved evidence snapshot
→ VLM prompt
→ structured enrichment response
→ persist model/provider/prompt/output
→ publish enrichment-complete event
```

Failure:

```text
provider timeout/error
→ persist enrichment failure status
→ emit event
→ no change to original detector decision
```

## 5. Human-review flow

```text
operator opens incident
→ sees detector evidence
→ sees optional generated context
→ labels: confirmed_fall / non_fall / uncertain
→ review record appended
```

Human review does not overwrite detector fields.

## 6. Dataset-improvement flow

```text
uncertain/false-positive/false-negative incident
→ export manifest/reference
→ review/license/privacy check
→ curated evaluation/development set
→ tune fall-engine thresholds or future temporal model
→ rerun fixed benchmark
```

## 7. Sensitive-data rule

Never send full continuous RTSP video to an external VLM.

Only explicitly approved incident evidence may leave the local system.
