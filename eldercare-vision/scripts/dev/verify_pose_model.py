"""P2-002 — Load-proof for ``yolo26s-pose.pt`` on CUDA.

Loads ``YOLO("yolo26s-pose.pt")`` via the official Ultralytics inference
workflow (first run performs the single sanctioned weights download into the
Ultralytics cache OUTSIDE this repo), runs one minimal prediction on the
canonical Ultralytics ``bus.jpg`` with explicit ``device=0`` / ``imgsz=640``,
and asserts the Results carry 17-keypoint human pose with confidences on CUDA.

Load-proof only: no adapter, no integration, no benchmarks, no exports.

Usage:
    python scripts/dev/verify_pose_model.py [--image PATH] [--device 0]

Only stdlib + ultralytics (+ its transitive torch/numpy) are used.
Exit code 0 = PASS, 1 = assertion failure (FAIL), 2 = usage error.
"""

# ruff: noqa: T201 — stdout is this script's acceptance interface (structured record the Tester diffs).

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import typing
import urllib.request

MODEL_NAME = "yolo26s-pose.pt"
IMGSZ = 640
EXPECTED_KPTS = 17

# Canonical image location: ultralytics.utils.ASSETS_URL + "/bus.jpg"
# (== "https://github.com/ultralytics/assets/releases/download/v0.0.0/bus.jpg").
BUS_JPG_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/bus.jpg"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_image(explicit: str | None) -> tuple[str, dict[str, str]]:
    """Resolve the test image path + provenance record.

    Order: (1) user-supplied ``--image``; (2) official-URL download into the
    OS temp dir (outside the repo); (3) fallback to the pip-installed
    ``ultralytics/assets/bus.jpg`` copy if the download fails (recorded).
    """
    if explicit:
        if not os.path.isfile(explicit):
            print(f"FAIL: --image not found: {explicit}", file=sys.stderr)
            print("RESULT: FAIL")
            sys.exit(1)
        size = os.path.getsize(explicit)
        return explicit, {
            "image_source": "user-supplied --image",
            "image_url": "(local file supplied; no download)",
            "image_path": os.path.abspath(explicit),
            "image_bytes": str(size),
            "image_sha256": sha256_file(explicit),
        }
    tmp_path = os.path.join(tempfile.gettempdir(), "eldercare-p2-002-bus.jpg")
    try:
        with urllib.request.urlopen(BUS_JPG_URL, timeout=120) as resp, open(tmp_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
        return tmp_path, {
            "image_source": "downloaded-official-url",
            "image_url": BUS_JPG_URL,
            "image_path": os.path.abspath(tmp_path),
            "image_bytes": str(os.path.getsize(tmp_path)),
            "image_sha256": sha256_file(tmp_path),
        }
    except Exception as exc:  # noqa: BLE001 - reported, then explicit fallback
        print(f"WARN: official-URL download failed ({exc!r}); trying installed-package asset copy.")
        try:
            from ultralytics.utils import ASSETS

            asset = os.path.join(str(ASSETS), "bus.jpg")
        except Exception:  # noqa: BLE001
            asset = ""
        if asset and os.path.isfile(asset):
            return asset, {
                "image_source": "installed-package-asset-fallback (download failed)",
                "image_url": BUS_JPG_URL,
                "image_path": os.path.abspath(asset),
                "image_bytes": str(os.path.getsize(asset)),
                "image_sha256": sha256_file(asset),
            }
        print(f"FAIL: could not obtain canonical bus.jpg: {exc!r}", file=sys.stderr)
        sys.exit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="P2-002 yolo26s-pose.pt CUDA load-proof.")
    p.add_argument("--image", default=None, help="Local image path (default: fetch bus.jpg).")
    p.add_argument("--device", default=0, type=int, help="Inference device (default 0 = cuda:0).")
    return p.parse_args(argv)


def fail(msg: str) -> typing.NoReturn:
    print(f"FAIL: {msg}", file=sys.stderr)
    print("RESULT: FAIL")
    sys.exit(1)


def main() -> int:
    args = parse_args()
    image_path, prov = resolve_image(args.image)

    from ultralytics import YOLO  # official import path: ultralytics.YOLO

    model = YOLO(MODEL_NAME)  # triggers the single sanctioned weights download on first run

    ckpt_path = os.path.abspath(str(getattr(model, "ckpt_path", MODEL_NAME) or MODEL_NAME))
    if os.path.basename(ckpt_path) != MODEL_NAME:
        fail(f"unexpected checkpoint file: {ckpt_path} (expected exactly {MODEL_NAME})")

    results = model.predict(source=image_path, device=args.device, imgsz=IMGSZ, verbose=False)
    r = results[0]

    person_count = len(r)
    kpts = r.keypoints
    boxes_shape = tuple(r.boxes.data.shape) if r.boxes is not None else None

    print("=== P2-002 acceptance record ===")
    print(f"model_name: {MODEL_NAME}")
    print(f"model_task: {model.task}")
    print(f"weights_cache_path: {ckpt_path}")
    print(f"model_device: {model.device}")
    print(f"imgsz: {IMGSZ}")
    print(f"orig_shape_hw: {tuple(r.orig_shape)}")
    for k in ("image_source", "image_url", "image_path", "image_bytes", "image_sha256"):
        print(f"{k}: {prov[k]}")
    print(f"person_count: {person_count}")
    if kpts is None:
        print("keypoints_xy_shape: None")
        print("keypoints_conf_shape: None")
        print("keypoints_device: None")
    else:
        xy = kpts.xy
        conf = kpts.conf
        data_device = getattr(getattr(kpts, "data", None), "device", None)
        print(f"keypoints_xy_shape: {tuple(xy.shape)}")
        print(f"keypoints_conf_shape: {tuple(conf.shape) if conf is not None else None}")
        print(f"keypoints_device: {data_device}")
    print(f"boxes_shape: {boxes_shape}")

    # ---- hard assertions (any failure = task failure, non-zero exit) ----
    if person_count < 1:
        fail(f"person_count={person_count}, expected >= 1 on canonical bus.jpg")
    if kpts is None:
        fail("results.keypoints is None (no pose output)")
    xy = kpts.xy
    if len(tuple(xy.shape)) != 3 or tuple(xy.shape)[1] != EXPECTED_KPTS or tuple(xy.shape)[2] != 2:
        fail(f"keypoints.xy shape={tuple(xy.shape)}, expected (N, 17, 2)")
    conf = kpts.conf
    if conf is None:
        fail("keypoints.conf is None (per-keypoint confidences missing)")
    if tuple(conf.shape) != (tuple(xy.shape)[0], EXPECTED_KPTS):
        fail(f"keypoints.conf shape={tuple(conf.shape)}, expected ({tuple(xy.shape)[0]}, 17)")
    data_device = getattr(getattr(kpts, "data", None), "device", None)
    expected_device = f"cuda:{args.device}"
    if getattr(data_device, "type", None) != "cuda" or str(data_device) != expected_device:
        fail(f"keypoint tensor device={data_device}, expected {expected_device}")

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
