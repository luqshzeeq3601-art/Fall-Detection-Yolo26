"""Export YOLO26s-pose PyTorch checkpoint to TensorRT 11 FP16 engine.

Reproducible pipeline:
1. Export yolo26s-pose.pt to ONNX (opset 18, imgsz=640)
2. Convert ONNX weights to FP16 with onnxconverter_common (preserving FLOAT32 I/O)
3. Build strongly-typed TensorRT 11 FP16 serialized network
4. Embed Ultralytics pose metadata into the engine binary

Usage:
    python scripts/export_tensorrt_fp16.py --weights yolo26s-pose.pt --out yolo26s-pose.engine
"""

# ruff: noqa: T201 - stdout is this script's CLI interface

from __future__ import annotations

import argparse
import json
from pathlib import Path

import onnx
import onnxconverter_common
import tensorrt as trt
from ultralytics import YOLO


def export_tensorrt_fp16(
    weights_path: str | Path = "yolo26s-pose.pt",
    output_engine_path: str | Path = "yolo26s-pose.engine",
    imgsz: int = 640,
    device: int = 0,
) -> Path:
    """Build and save a TensorRT FP16 engine from a YOLO pose checkpoint."""
    weights_path = Path(weights_path)
    output_engine_path = Path(output_engine_path)

    temp_onnx = weights_path.with_suffix(".onnx")
    temp_fp16_onnx = weights_path.with_name(f"{weights_path.stem}-fp16.onnx")

    # Step 1: Export base model to ONNX
    print(f"[1/4] Exporting {weights_path} to ONNX (opset 18, imgsz={imgsz})...")
    model = YOLO(str(weights_path))
    model.export(format="onnx", opset=18, dynamic=False, imgsz=imgsz, device=device)

    # Step 2: Convert to FP16 ONNX graph
    print(f"[2/4] Converting {temp_onnx} to FP16 graph with float32 I/O...")
    onnx_model = onnx.load(str(temp_onnx))
    onnx_fp16 = onnxconverter_common.convert_float_to_float16(onnx_model, keep_io_types=True)
    onnx.save(onnx_fp16, str(temp_fp16_onnx))

    # Step 3: Build strongly-typed TensorRT 11 engine
    print(f"[3/4] Compiling TensorRT 11 FP16 serialized plan on CUDA device {device}...")
    logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(logger)
    network_flags = (
        1 << int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED)
        if hasattr(trt.NetworkDefinitionCreationFlag, "STRONGLY_TYPED")
        else 0
    )
    network = builder.create_network(network_flags)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(str(temp_fp16_onnx)):
        raise RuntimeError(f"Failed to parse {temp_fp16_onnx} into TensorRT network")

    config = builder.create_builder_config()
    engine_bytes = builder.build_serialized_network(network, config)
    if engine_bytes is None:
        raise RuntimeError("TensorRT engine compilation failed")

    # Step 4: Embed metadata dictionary for Ultralytics AutoBackend compatibility
    print(f"[4/4] Serializing metadata and engine binary to {output_engine_path}...")
    metadata = {
        "description": "Ultralytics YOLO26s-pose FP16 engine for RTX 3070",
        "author": "ElderCare Vision Optimization Pipeline",
        "version": "1.0.0",
        "task": "pose",
        "head": "Pose26",
        "batch": 1,
        "imgsz": [imgsz, imgsz],
        "names": {0: "person"},
        "channels": 3,
        "end2end": False,
        "kpt_shape": [17, 3],
        "kpt_names": {
            0: [
                "nose",
                "left_eye",
                "right_eye",
                "left_ear",
                "right_ear",
                "left_shoulder",
                "right_shoulder",
                "left_elbow",
                "right_elbow",
                "left_wrist",
                "right_wrist",
                "left_hip",
                "right_hip",
                "left_knee",
                "right_knee",
                "left_ankle",
                "right_ankle",
            ]
        },
    }
    meta_json = json.dumps(metadata)
    with open(output_engine_path, "wb") as f:
        f.write(len(meta_json).to_bytes(4, byteorder="little", signed=True))
        f.write(meta_json.encode())
        f.write(engine_bytes)

    print(f"TensorRT FP16 engine successfully built: {output_engine_path}")
    return output_engine_path


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Export YOLO26s-pose to TensorRT 11 FP16.")
    parser.add_argument("--weights", default="yolo26s-pose.pt", help="Input .pt model path")
    parser.add_argument("--out", default="yolo26s-pose.engine", help="Output .engine path")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference resolution")
    parser.add_argument("--device", type=int, default=0, help="CUDA device index")
    args = parser.parse_args()

    export_tensorrt_fp16(
        weights_path=args.weights,
        output_engine_path=args.out,
        imgsz=args.imgsz,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
