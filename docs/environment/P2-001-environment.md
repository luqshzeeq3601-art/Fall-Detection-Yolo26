# P2-001 — Environment Baseline: CUDA / PyTorch / Ultralytics / RTX 3070

- **Date (UTC):** 2026-09-20
- **Repo HEAD:** `773e175e09027175bf3e4c48a23bfdcac720c31b`
- **Inspector:** FRESH VISION subagent (P2-001); inspection + report only
- **Method:** source-driven — installed-package probes first, official Ultralytics docs second, memory flagged as unverified

## 1. Machine table

| Item | Measured value |
|---|---|
| OS | Microsoft Windows 11 Pro, 10.0.26200 Build 26200, x64-based PC (`Windows-10-10.0.26200-SP0`, `AMD64`) |
| Shell / Python | Python 3.10.11, `<python-install-dir>\` |
| WSL | `docker-desktop` — **Stopped** (unchanged; not modified) |
| GPU | NVIDIA GeForce RTX 3070, 8192 MiB, Bus `00000000:07:00.0`, WDDM, Compute Capability (8, 6) |
| Driver | NVIDIA-SMI 616.92, KMD 616.92, CUDA UMD 13.4 |
| PyTorch | `2.5.1+cu121` (built against CUDA 12.1) |
| CUDA available | `True`, 1 device, `cuda:0` = NVIDIA GeForce RTX 3070 |
| cuDNN | available `True`, version `90100` |
| Ultralytics | `8.4.142` (`.../site-packages/ultralytics/__init__.py`) |
| OpenCV (runtime) | `cv2.__version__` = `5.0.0` |
| OpenCV (dists) | `opencv-python-headless 5.0.0.93` (matches runtime) + `opencv-python 4.9.0.80` also installed |
| NumPy | `2.2.6` |
| ONNX | `onnx 1.22.0`, `onnxruntime 1.23.2`, providers `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']` |
| TensorRT | **absent** (`ModuleNotFoundError: No module named 'tensorrt'`, `find_spec('tensorrt')` → `None`) — Phase 9 dependency, **NOT a Phase 2 blocker** |
| `yolo26s-pose.pt` support | **SUPPORTED (by inspection)** — evidence chain in §4; runtime load proof deferred to P2-002 |

## 2. Command log (exact command + output)

All commands run from `<repo-root>` unless noted.

### Area 1 — Python version + OS/WSL identity

Command:

```powershell
python --version; python -c "import platform; print(platform.platform()); print(platform.version()); print(platform.machine())"
```

Output:

```text
Python 3.10.11
Windows-10-10.0.26200-SP0
10.0.26200
AMD64
```

Command:

```powershell
wsl --list --verbose 2>&1
```

Output (UTF-16 console rendering trimmed to content; bytes preserved):

```text
NAME            STATE     VERSION
* docker-desktop  Stopped   2
```

(Coordinator-observed `docker-desktop Stopped` confirmed; WSL state was not changed.)

Host note (`systeminfo`):

```text
OS Name:    Microsoft Windows 11 Pro
OS Version: 10.0.26200 N/A Build 26200
System Type: x64-based PC
```

### Area 2 — NVIDIA driver + GPU + VRAM + nvidia-smi

Command:

```powershell
nvidia-smi
```

Output (timestamp + process table abbreviated to names; GPU/driver lines verbatim):

```text
Sun Sep 20 13:47:39 2026
| NVIDIA-SMI 616.92   KMD Version: 616.92   CUDA UMD Version: 13.4 |
|   0  NVIDIA GeForce RTX 3070  WDDM  |  00000000:07:00.0  On  |  N/A  |
|  0%   45C    P8    16W / 220W  |  865MiB / 8192MiB  |  0%  Default  |
```

Process rows were all `C+G` desktop apps (explorer, chrome, msedgewebview2, vgtray, iCUE, ChatGPT, copilot, etc.) — no compute jobs; full list available via rerun.

### Area 3 — PyTorch version + CUDA runtime build

Command:

```powershell
python -c "import torch; print('torch:', torch.__version__); print('cuda_build:', torch.version.cuda); print('cuda_available:', torch.cuda.is_available()); print('device_count:', torch.cuda.device_count()); print('device0_name:', torch.cuda.get_device_name(0)); print('capability:', torch.cuda.get_device_capability(0))"
```

Output:

```text
torch: 2.5.1+cu121
cuda_build: 12.1
cuda_available: True
device_count: 1
device0_name: NVIDIA GeForce RTX 3070
capability: (8, 6)
```

### Area 4 — CUDA availability / count / name / capability

Covered by the Area 3 probe verbatim: `cuda_available: True`, `device_count: 1`, `device0_name: NVIDIA GeForce RTX 3070`, `capability: (8, 6)`.

### Area 5 — cuDNN availability/version

Command:

```powershell
python -c "import torch; print('cudnn_available:', torch.backends.cudnn.is_available()); print('cudnn_version:', torch.backends.cudnn.version())"
```

Output:

```text
cudnn_available: True
cudnn_version: 90100
```

### Area 6 — Ultralytics version

Command:

```powershell
pip show ultralytics; python -c "import ultralytics; print('ultralytics:', ultralytics.__version__); print('file:', ultralytics.__file__)"
```

Output (note: `pip show` emitted cp1252 `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f680'` logging noise on this console — pip/rich rendering issue only; the version fields below are verbatim and were cross-confirmed via `importlib.metadata`):

```text
Name: ultralytics
Version: 8.4.142
ultralytics: 8.4.142
file: <python-install-dir>\lib\site-packages\ultralytics\__init__.py
```

Cross-confirm (clean, no console noise):

```powershell
python -c "import importlib.metadata as m; print('ultralytics:', m.version('ultralytics'))"
```

```text
ultralytics: 8.4.142
```

### Area 7 — OpenCV + NumPy

Command:

```powershell
python -c "import cv2; print('cv2:', cv2.__version__); print('cv2_file:', cv2.__file__)"; python -c "import numpy; print('numpy:', numpy.__version__)"
```

Output:

```text
cv2: 5.0.0
cv2_file: <python-install-dir>\lib\site-packages\cv2\__init__.py
numpy: 2.2.6
```

Installed OpenCV distributions (two are present; runtime `5.0.0` matches `opencv-python-headless 5.0.0.93`):

```powershell
python -c "import importlib.metadata as m; ds=[d for d in m.distributions() if 'opencv' in (d.metadata['Name'] or '')]; print([(d.metadata['Name'], d.version) for d in ds])"
```

```text
[('opencv-python', '4.9.0.80'), ('opencv-python-headless', '5.0.0.93')]
```

(`pip show opencv-python` additionally reported `Version: 4.9.0.80`. Which dist's files own `site-packages/cv2/` was not disambiguated beyond the version match; recorded as a limitation.)

### Area 8 — ONNX status

Command:

```powershell
python -c "import onnx; print('onnx:', onnx.__version__)"; python -c "import onnxruntime; print('onnxruntime:', onnxruntime.__version__); print('providers:', onnxruntime.get_available_providers())"
```

Output:

```text
onnx: 1.22.0
onnxruntime: 1.23.2
providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

Note: `TensorrtExecutionProvider` appearing in the provider list means the onnxruntime build registers that EP; it does **not** mean TensorRT is installed (Area 9 proves it is absent).

### Area 9 — TensorRT status

Command:

```powershell
python -c "import tensorrt; print(tensorrt.__version__)" 2>&1; python -c "import importlib.util; print('tensorrt_spec:', importlib.util.find_spec('tensorrt'))"
```

Output:

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'tensorrt'
tensorrt_spec: None
```

**TensorRT is absent. This is a Phase 9 (TensorRT FP16 deployment) dependency and explicitly NOT a Phase 2 blocker.** Phase 2 work (PyTorch baseline → ONNX validation) does not require it; nothing was installed to change this.

### Area 10 — `yolo26s-pose.pt` support verdict: SUPPORTED (by inspection)

Evidence chain (installed package FIRST, official docs SECOND, version comparison):

**(a) Installed package `ultralytics 8.4.142` ships YOLO26 model configs, including pose:**

```powershell
python -c "import ultralytics, os; r=os.path.dirname(ultralytics.__file__); print(sorted(os.listdir(r+'/cfg/models')))"
```

```text
['11', '12', '26', 'rt-detr', 'v10', 'v3', 'v5', 'v6', 'v8', 'v9']
```

Contents of `.../site-packages/ultralytics/cfg/models/26/`:

```text
yolo26-cls.yaml, yolo26-depth.yaml, yolo26-obb.yaml, yolo26-p2.yaml, yolo26-p6.yaml,
yolo26-pose.yaml, yolo26-seg.yaml, yolo26-sem.yaml, yolo26.yaml, yoloe-26-seg.yaml, yoloe-26.yaml
```

`yolo26-pose.yaml` (verbatim excerpts) defines the `s` scale, i.e. `model=yolo26s-pose.yaml` resolves:

```yaml
# Ultralytics YOLO26-pose keypoints/pose estimation model with P3/8 - P5/32 outputs
# Model docs: https://docs.ultralytics.com/models/yolo26
# Task docs: https://docs.ultralytics.com/tasks/pose
nc: 80 # number of classes
end2end: True # whether to use end-to-end mode
kpt_shape: [17, 3] # number of keypoints, number of dims (2 for x,y or 3 for x,y,visible)
scales: # model compound scaling constants, i.e. 'model=yolo26n-pose.yaml' will call yolo26-pose.yaml with scale 'n'
  # [depth, width, max_channels]
  n: [0.50, 0.25, 1024] # summary: 363 layers, 3,747,554 parameters, 3,747,554 gradients, 10.7 GFLOPs
  s: [0.50, 0.50, 1024] # summary: 363 layers, 11,870,498 parameters, 11,870,498 gradients, 29.6 GFLOPs
  m: [0.50, 1.00, 512] # summary: 383 layers, 24,344,482 parameters, 24,344,482 gradients, 85.9 GFLOPs
  ...
  - [[16, 19, 22], 1, Pose26, [nc, kpt_shape]] # Pose26(P3, P4, P5)
```

Task registry references YOLO26 pose (`ultralytics/nn/tasks.py` source scan for `yolo26[a-z\-]*`):

```text
['yolo26n', 'yolo26n-cls', 'yolo26n-depth', 'yolo26n-obb', 'yolo26n-pose', 'yolo26n-seg', 'yolo26n-sem']
```

**(b) Official Ultralytics docs (fetched 2026-09-20) list `yolo26s-pose.pt` as an official checkpoint:**

- URL: `https://docs.ultralytics.com/models/yolo26/` — "Supported Tasks and Modes" table, YOLO26-pose row: filenames `` `yolo26n-pose.pt` `yolo26s-pose.pt` `yolo26m-pose.pt` `yolo26l-pose.pt` `yolo26x-pose.pt` ``, task Pose/Keypoints, Training ✅ Validation ✅ Inference ✅ Export ✅. Key-features section: "Precision Pose Estimation … up to +7.2 AP over YOLO11 on COCO pose estimation."
- URL: `https://docs.ultralytics.com/tasks/pose/` — "Ultralytics YOLO26 pretrained Pose models" table lists `YOLO26s-pose` (640 px, mAPpose 50-95(e2e) 63.0, params 10.4 M, FLOPs 24.1 B); "YOLO26 *pose* models use the `-pose` suffix", 17 keypoints; "Models download automatically from the latest Ultralytics release on first use."
- No explicit minimum-Ultralytics-version statement was found on either page (FAQ says only "Install or update the package"). Version comparison therefore rests on the installed package itself: 8.4.142 ships `cfg/models/26/*.yaml` + `Pose26` head + task-registry entries, i.e. this installed version carries YOLO26 support.

**(c) Verdict:** **SUPPORTED (by inspection).** The installed 8.4.142 package contains the architecture/config path for the `s`-scale pose model and the official docs publish `yolo26s-pose.pt` as a released checkpoint with full train/val/inference/export support. **Runtime load proof (`YOLO("yolo26s-pose.pt")`) is deferred to P2-002** because first use auto-downloads weights and downloads are forbidden in this task.

## 3. CUDA smoke-test transcript (real alloc → matmul → copy-back → value verify → release)

Command:

```powershell
python -c "import torch; b0=torch.cuda.memory_allocated(0); print('before_bytes:', b0); a=torch.ones(512,512,device='cuda:0'); b=torch.eye(512,device='cuda:0'); c=torch.matmul(a,b); mid=torch.cuda.memory_allocated(0); print('after_alloc_bytes:', mid); h=c.to('cpu'); print('device:', str(c.device), 'shape:', tuple(c.shape)); print('sum:', float(h.sum()), 'expected:', float(512*512)); print('values_ok:', bool((h==torch.ones(512,512)).all())); del a,b,c,h; torch.cuda.empty_cache(); b1=torch.cuda.memory_allocated(0); print('after_release_bytes:', b1); print('released_bytes:', mid-b1)"
```

Output:

```text
before_bytes: 0
after_alloc_bytes: 11665408
device: cuda:0 shape: (512, 512)
sum: 262144.0 expected: 262144.0
values_ok: True
after_release_bytes: 8519680
released_bytes: 3145728
```

Repeatability / no-growth check (256×256, two trials back-to-back):

```text
s1: 65536.0 ok1: True after_t1: 8519680
s2: 65536.0 ok2: True after_t2: 8519680
stable_no_growth: True
```

Reading: `ones(512) @ eye(512) = ones(512)` verified element-wise on the CPU copy (`sum 262144.0 = 512*512`, `values_ok: True`). `del + empty_cache()` released exactly 3,145,728 bytes (3 × 512×512×4 B — the two inputs plus the matmul output). The residual 8,519,680 bytes is one-time CUDA context/allocator retention: it was identical after the first release and unchanged across both repeat trials (`stable_no_growth: True`), so nothing leaks per allocation cycle.

(One discarded probe: `torch.cuda.reset_peak_memory_stats(0)` raised `RuntimeError: Invalid device argument` in this build; it is not needed for the before/after `memory_allocated()` proof and was replaced by the transcript above.)

## 4. TensorRT non-blocker statement

TensorRT (`import tensorrt`) is absent on this machine. **This is expected and is a Phase 9 (TensorRT FP16 deployment) dependency — explicitly NOT a Phase 2 blocker.** The Phase 2 path (PyTorch baseline → ONNX validation) requires only what is proven present above (CUDA + cuDNN + onnx/onnxruntime). Nothing was installed.

## 5. Assumptions / limitations

1. `pip show ultralytics` output on this console contains cp1252 `UnicodeEncodeError` logging noise (pip/rich emoji rendering); version `8.4.142` cross-confirmed via `importlib.metadata` and `ultralytics.__version__`.
2. Two OpenCV distributions coexist (`opencv-python 4.9.0.80`, `opencv-python-headless 5.0.0.93`); runtime `cv2 5.0.0` matches the headless dist, but file ownership of `site-packages/cv2/` was not disambiguated.
3. `TensorrtExecutionProvider` in the onnxruntime provider list is a build registration, not proof of a TensorRT install.
4. `nvidia-smi` process rows were summarized (desktop `C+G` apps, no compute jobs); rerun reproduces the full table.
5. WSL `wsl --list` output decoded from UTF-16 console bytes; content preserved.
6. Docs quotes are from the live Ultralytics docs as fetched 2026-09-20; pages may change — URLs recorded for re-fetch.
7. No Ultralytics weight download or model load was performed here by design; `YOLO("yolo26s-pose.pt")` first-use download behavior is quoted from docs ("Models download automatically … on first use"), runtime proof deferred to P2-002.
8. `%APPDATA%\Ultralytics\settings.json` (2026-03-09) and `Arial.ttf` (2026-08-12*) are pre-existing; `~/.cache/ultralytics` does not exist. (*console date rendering; predates this task in all readings.)

## 6. Rerun instructions (auditor paste commands)

From `<repo-root>`, PowerShell:

```powershell
git rev-parse HEAD
python --version
wsl --list --verbose
nvidia-smi
python -c "import torch; print('torch:', torch.__version__); print('cuda_build:', torch.version.cuda); print('cuda_available:', torch.cuda.is_available()); print('device_count:', torch.cuda.device_count()); print('device0_name:', torch.cuda.get_device_name(0)); print('capability:', torch.cuda.get_device_capability(0))"
python -c "import torch; print('cudnn_available:', torch.backends.cudnn.is_available()); print('cudnn_version:', torch.backends.cudnn.version())"
python -c "import importlib.metadata as m; print('ultralytics:', m.version('ultralytics'))"
python -c "import ultralytics; print('ultralytics:', ultralytics.__version__); print('file:', ultralytics.__file__)"
python -c "import cv2; print('cv2:', cv2.__version__)"
python -c "import numpy; print('numpy:', numpy.__version__)"
python -c "import onnx; print('onnx:', onnx.__version__)"
python -c "import onnxruntime; print('onnxruntime:', onnxruntime.__version__); print('providers:', onnxruntime.get_available_providers())"
python -c "import tensorrt" 2>&1
python -c "import ultralytics, os; r=os.path.dirname(ultralytics.__file__); print(sorted(os.listdir(r+'/cfg/models')))"
```

Smoke test (real alloc/op/copy-back/release):

```powershell
python -c "import torch; b0=torch.cuda.memory_allocated(0); print('before_bytes:', b0); a=torch.ones(512,512,device='cuda:0'); b=torch.eye(512,device='cuda:0'); c=torch.matmul(a,b); mid=torch.cuda.memory_allocated(0); print('after_alloc_bytes:', mid); h=c.to('cpu'); print('device:', str(c.device), 'shape:', tuple(c.shape)); print('sum:', float(h.sum()), 'expected:', float(512*512)); print('values_ok:', bool((h==torch.ones(512,512)).all())); del a,b,c,h; torch.cuda.empty_cache(); b1=torch.cuda.memory_allocated(0); print('after_release_bytes:', b1); print('released_bytes:', mid-b1)"
```

Docs re-fetch: `https://docs.ultralytics.com/models/yolo26/`, `https://docs.ultralytics.com/tasks/pose/` (compare YOLO26-pose rows against the quotes in §2 Area 10).

## 7. Side-effect check

- No `pip install`, no downloads, no inference, no exports, no benchmarks performed.
- `git status --short` after all probes: only pre-existing untracked `docs/task-briefs/P2-001.md` (coordinator's file, untouched); no new files in the repo besides this report.
- USERPROFILE-wide scan for `*.pt` files modified today: none found.
- `~/.cache/ultralytics` does not exist; `%APPDATA%\Ultralytics\` files predate this task.
