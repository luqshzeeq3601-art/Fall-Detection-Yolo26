# Real Dataset Acquisition & Ingestion Guide (Stage 1 / V6)

This guide specifies the acquisition protocol, directory structure, file naming conventions, and integrity verification requirements for authentic real-world fall detection datasets.

---

## 1. UP-Fall Detection Dataset (Real Optical Video)

### 1.1 Dataset Summary & Official Source
* **Source:** UP-Fall Detection Dataset (Universidad Panamericana / MDPI Sensors 2019)
* **Dataset Identifier:** `doi:10.17632/7w7fccng7m.1` (Mendeley Data) or Official Repository
* **Subjects:** 17 healthy young adults (Subjects 1 to 17)
* **Cameras:** Camera 1 (Frontal / Lateral view) and Camera 2 (High-angle / Ceiling perspective)
* **Trials:** 3 repetitions per activity
* **Total Clips Expected:** $17 \times 11 \times 3 \times 2 = 1,122$ genuine optical video sequences

### 1.2 Activity Taxonomy
| Activity Code | Activity Name | Class Type | Ingestion Label |
| :--- | :--- | :--- | :--- |
| **Activity 1** | Falling forward using hands | **Fall** | `fall_forward_hands` |
| **Activity 2** | Falling forward on knees | **Fall** | `fall_forward_knees` |
| **Activity 3** | Falling backwards | **Fall** | `fall_backward` |
| **Activity 4** | Falling sideways | **Fall** | `fall_sideways` |
| **Activity 5** | Falling sitting in empty chair | **Fall** | `fall_from_chair` |
| **Activity 6** | Walking | **ADL** | `walking` |
| **Activity 7** | Standing | **ADL** | `standing` |
| **Activity 8** | Simple sitting | **ADL** | `sitting` |
| **Activity 9** | Picking up an object | **ADL** | `picking_up_object` |
| **Activity 10** | Jumping | **ADL** | `jumping` |
| **Activity 11** | Laying down on bed/couch | **ADL** | `lying_down` |

### 1.3 Local Storage Target
Place all downloaded optical videos directly in:
```
datasets/raw/upfall_real/
```

### 1.4 File Naming Convention
The ingestion engine parses files matching:
* `Subject{N}Activity{A}Trial{T}Camera{C}.mp4` (or `.avi`, `.mkv`)
* Examples:
  * `Subject1Activity1Trial1Camera1.mp4` $\rightarrow$ Subject 1, Fall 1, Trial 1, Camera 1
  * `Subject12Activity6Trial2Camera1.mp4` $\rightarrow$ Subject 12, Walking, Trial 2, Camera 1
  * Subfolder structures (e.g. `Subject1/Activity1/Trial1/Camera1.mp4`) are also automatically resolved.

---

## 2. Continuous Longform ADL Dataset (False Alert Testing)

### 2.1 Dataset Summary & Official Sources
To rigorously measure False Alerts per Camera-Hour without short-clip truncation artifacts, continuous longform video is required.
* **Primary Source:** **Charades Dataset** (Allen Institute for AI) — Publicly accessible: `https://prior.allenai.org/projects/charades`
* **Alternative Source:** **Toyota Smarthome** (Inria) — Institutional research license: `https://project.inria.fr/toyotasmarthome/`
* **Target Volume:** $\ge 20$ camera-hours of continuous optical video (containing zero falls).

### 2.2 Local Storage Target
Place downloaded continuous video files in:
```
datasets/raw/longform_adl/
```

---

## 3. Partitioning Strategy (V6 Master Manifest)

| Partition | Composition | Subjects / Cameras | Purpose |
| :--- | :--- | :--- | :--- |
| **Dev Split** | URFD (all 70) + UP-Fall Subjects 1–11 | Subjs 1–11 (Camera 1 & 2, all trials) | Model training, temporal feature extraction, GroupKFold cross-validation |
| **Test-A Split** | UP-Fall Subjects 12–17 | Subjs 12–17 (Camera 1, Trials 1 & 2) | Primary held-out deployment evaluation (disjoint subject) |
| **Test-X Split** | UP-Fall Subjects 12–17 | Subjs 12–17 (Camera 2, Trials 1 & 2) | Cross-camera viewpoint generalization disclosure (never tuned on) |
| **Test-B Split** | UP-Fall Subjects 12–17 (Trial 3) | Subjs 12–17 (Camera 1 & 2, Trial 3) | Reserve benchmark partition held back for future post-Stage 4 evaluation |
| **Longform ADL** | Charades / Toyota Smarthome | Various non-fall human activities | True continuous False Alerts per Camera-Hour measurement |

---

## 4. Ingestion Command

Once video files are placed into `datasets/raw/upfall_real/` and `datasets/raw/longform_adl/`:
```bash
python scripts/dataset/ingest_v6.py --verify-authenticity --generate-manifest
```
The ingestion engine executes `OpticalAuthenticityValidator` on every clip, extracts precise frame counts and durations, locks SHA-256 hashes, and outputs `datasets/manifests/v6_master_manifest.json`.
