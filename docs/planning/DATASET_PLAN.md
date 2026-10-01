# Dataset Plan — ElderCare Vision

## 1. Dataset strategy

Use three layers:

```text
Pose pretraining
    COCO-Pose via official YOLO26s-Pose checkpoint

Fall-engine benchmark
    UR Fall Detection Dataset

Robustness / additional activities
    UP-Fall RGB subset

Deployment-domain validation
    controlled local IP-camera clips
```

## 2. COCO-Pose

Purpose:

- source of the pretrained human pose capability,
- not a fall dataset.

No COCO download is required for the MVP unless pose-model validation/fine-tuning is explicitly added.

## 3. UR Fall Detection Dataset — primary

Official source:

`https://www.fenix.ur.edu.pl/~mkepski/ds/uf.html`

Dataset contains:

- 70 sequences,
- 30 fall sequences,
- 40 activities-of-daily-living sequences,
- RGB,
- depth,
- accelerometer data.

This project uses the RGB sequences.

License stated by the official dataset page:

- Creative Commons Attribution-NonCommercial-ShareAlike 4.0
- intended for non-commercial academic use.

### Why selected

- manageable compared with very large multimodal datasets,
- video/sequence data fits temporal fall analysis,
- includes falls and normal activities,
- official source and explicit license.

### Use

- develop temporal feature extraction,
- tune on development sequences,
- hold out complete sequences for final evaluation.

### Split rule

Never split individual frames from one sequence across train/dev/test.

Recommended reproducible approach:

- create a manifest of sequence IDs,
- assign entire sequence IDs to development and test,
- store split manifest in Git,
- keep raw media outside Git.

If subject identities are not reliably exposed in downloaded metadata, do not pretend the split is subject-disjoint.

## 4. UP-Fall — secondary

Official project/data page:

`https://sites.google.com/up.edu.mx/challenge-up-2019/data`

Reference paper:

`https://www.mdpi.com/1424-8220/19/9/1988`

Contains:

- 17 subjects in the published dataset description,
- 11 activities,
- three trials per activity,
- six ADLs,
- five fall types,
- multiple sensor modalities,
- camera data.

The complete consolidated dataset is very large (~812 GB in the publication).

### Project usage

Do not require the entire dataset.

Use only required RGB-camera data / selected subjects or trials sufficient for robustness testing, subject to the source's access structure and terms.

### Split rule

Use subject-disjoint development/final evaluation whenever subject identifiers are available.

## 5. Local deployment-domain set

Purpose:

- validate actual phone/IP camera,
- actual room layout,
- actual compression/lighting,
- actual RTSP path.

Suggested scenarios:

- walking
- sitting
- standing up
- bending
- picking up an object
- kneeling
- lying down intentionally
- partial occlusion
- entering/leaving frame
- controlled safe fall simulation if appropriate

Safety:

- use consenting healthy adults only for any simulation,
- use mats/spotter or avoid physical fall simulation entirely,
- do not ask elderly/vulnerable individuals to perform falls.

## 6. Data manifest

Create:

```text
datasets/manifests/urfd_manifest.csv
datasets/manifests/upfall_manifest.csv
datasets/manifests/local_manifest.csv
```

Suggested fields:

```text
sample_id
source_dataset
sequence_id
subject_id
camera_id
activity
is_fall
fall_type
path_local
split
license
notes
```

`path_local` is ignored by Git if it reveals user-specific local paths.

## 7. Leakage controls

Prohibited:

- random frame-level train/test split,
- tuning thresholds on final-test clips,
- using test metrics to select model thresholds,
- duplicate/near-duplicate clips across splits.

## 8. Annotation strategy

For rule-based temporal engine evaluation, at minimum annotate:

- sequence-level fall/non-fall,
- fall onset/interval when available,
- activity type,
- camera/source,
- scenario notes.

For time-to-alert, create/consume an onset timestamp/frame where supported.

## 9. Derived keypoints

It is allowed to cache derived YOLO keypoints locally for faster experiments.

Derived files must include:

- source sample ID,
- model name,
- Ultralytics version,
- inference config,
- extraction timestamp/version.

Do not treat pseudo-keypoints as human ground-truth pose labels.

## 10. Future custom pose fine-tuning

Only proceed if:

1. pose failures are documented,
2. keypoint ground truth exists or is manually labeled,
3. annotation format is validated against Ultralytics pose format,
4. license permits the intended use,
5. new model is compared against pretrained `yolo26s-pose.pt`.

## 11. Dataset versioning

Git stores:

- manifests,
- split definitions,
- checksums where feasible,
- annotation tooling,
- derived-metadata schema.

Git does not store:

- large raw datasets,
- private raw camera recordings,
- credentials/URLs used to download restricted data.
