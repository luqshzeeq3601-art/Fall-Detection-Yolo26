"""CLI tool to verify live RTSP camera ingestion and latency (Phase 1 / Verification).

Usage:
    python scripts/dev/test_rtsp_stream.py --url rtsp://user:pass@192.168.1.50:8554/live --frames 50
"""

from __future__ import annotations

import argparse
import sys
import time

from eldercare.common.redaction import redact_rtsp_url
from eldercare.vision.stream.camera import CameraConfig
from eldercare.vision.stream.capture import RtspCapture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test and benchmark live RTSP stream ingestion.")
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="RTSP / RTSPS stream URL (e.g., rtsp://192.168.1.100:8080/h264_pcm.sdp)",
    )
    parser.add_argument(
        "--camera-id",
        type=str,
        default="test-camera",
        help="Identifier for the camera",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=50,
        help="Number of frames to capture and benchmark (default: 50)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    redacted_url = redact_rtsp_url(args.url)
    print(f"[+] Initializing RTSP capture for camera '{args.camera_id}' ({redacted_url})...")

    try:
        config = CameraConfig(
            camera_id=args.camera_id,
            name="RTSP Test Camera",
            rtsp_url=args.url,
        )
    except Exception as exc:
        print(f"[!] Invalid camera configuration: {exc}", file=sys.stderr)
        return 1

    capture = RtspCapture(config)
    print("[+] Connecting to RTSP stream...")
    t_open_start = time.perf_counter()
    if not capture.open():
        print(f"[!] Failed to open stream: {capture.last_error}", file=sys.stderr)
        return 1

    open_duration = time.perf_counter() - t_open_start
    print(f"[+] Stream connected successfully in {open_duration * 1000:.1f} ms.")

    latencies_ms: list[float] = []
    received_frames = 0
    frame_shape = None

    try:
        for i in range(args.frames):
            t0 = time.perf_counter()
            ok, frame = capture.read()
            dt_ms = (time.perf_counter() - t0) * 1000.0

            if not ok or frame is None:
                print(f"[!] Frame {i+1}/{args.frames} read failed: {capture.last_error}", file=sys.stderr)
                break

            latencies_ms.append(dt_ms)
            received_frames += 1
            if frame_shape is None:
                frame_shape = frame.shape
                print(f"[+] First frame received: resolution={frame.shape[1]}x{frame.shape[0]}, channels={frame.shape[2]}")

            if (i + 1) % 10 == 0 or (i + 1) == args.frames:
                print(f"    -> Ingested {i+1}/{args.frames} frames (last: {dt_ms:.1f} ms)...")

    finally:
        capture.release()
        print("[+] RTSP stream closed and handle released.")

    if received_frames > 0:
        avg_latency = sum(latencies_ms) / len(latencies_ms)
        min_latency = min(latencies_ms)
        max_latency = max(latencies_ms)
        effective_fps = 1000.0 / avg_latency if avg_latency > 0 else 0.0

        print("\n=== RTSP INGESTION BENCHMARK SUMMARY ===")
        print(f"Frames Received:  {received_frames}/{args.frames}")
        print(f"Frame Resolution: {frame_shape[1]}x{frame_shape[0]}" if frame_shape else "N/A")
        print(f"Average Ingest:   {avg_latency:.2f} ms (~{effective_fps:.1f} FPS)")
        print(f"Min / Max Ingest: {min_latency:.2f} ms / {max_latency:.2f} ms")
        print("Status:           PASSED (Verified RTSP Stream Ingest)")
        return 0
    else:
        print("[!] No frames were ingested.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
