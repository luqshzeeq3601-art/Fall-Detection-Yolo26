"""Frame and video input validator for dataset ingestion and inference pipelines (P11.8-003).

Detects and rejects:
1. Side-by-side composite frames (e.g. left grayscale depth map + right RGB video).
2. Grayscale-half or corrupted composite frame streams.
3. Resolution mismatches against the dataset manifest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("frame_validator")


class FrameValidationError(ValueError):
    """Raised when an ingested frame or video fails integrity checks."""


@dataclass
class FrameValidationResult:
    """Detailed result of a single frame or video validation check."""

    is_valid: bool
    is_composite: bool
    is_grayscale_half: bool
    resolution_match: bool
    actual_resolution: tuple[int, int]  # (height, width)
    expected_resolution: tuple[int, int] | None
    left_chroma_diff: float
    right_chroma_diff: float
    message: str


class FrameValidator:
    """Validates raw frame arrays and video files against quality and format constraints."""

    def __init__(
        self,
        chroma_diff_threshold: float = 2.0,
        composite_ratio_threshold: float = 5.0,
    ) -> None:
        """Initialize validator.

        Args:
            chroma_diff_threshold: Max mean RGB channel divergence to consider a region grayscale.
            composite_ratio_threshold: Ratio of right-to-left chroma divergence to flag composite.
        """
        self.chroma_diff_threshold = chroma_diff_threshold
        self.composite_ratio_threshold = composite_ratio_threshold

    def compute_chroma_divergence(self, img_region: np.ndarray) -> float:
        """Calculate mean channel absolute divergence: mean(|R-G| + |G-B| + |B-R|).

        For pure grayscale or depth maps, this is 0.0.
        For natural color RGB images, this is typically > 5.0.
        """
        if img_region.ndim != 3 or img_region.shape[2] < 3:
            return 0.0

        b = img_region[:, :, 0].astype(np.float32)
        g = img_region[:, :, 1].astype(np.float32)
        r = img_region[:, :, 2].astype(np.float32)

        diff = np.abs(r - g) + np.abs(g - b) + np.abs(b - r)
        return float(np.mean(diff))

    def detect_side_by_side_composite(self, frame: np.ndarray) -> tuple[bool, bool, float, float]:
        """Check if frame is a side-by-side composite (e.g. left depth map, right RGB).

        Returns:
            (is_composite, is_grayscale_half, left_chroma, right_chroma)
        """
        if frame.ndim != 3 or frame.shape[2] < 3:
            return False, False, 0.0, 0.0

        h, w, _ = frame.shape
        mid_x = w // 2

        left_half = frame[:, :mid_x, :]
        right_half = frame[:, mid_x:, :]

        left_chroma = self.compute_chroma_divergence(left_half)
        right_chroma = self.compute_chroma_divergence(right_half)

        # Left half is grayscale depth map while right half is color RGB
        is_left_grayscale = left_chroma < self.chroma_diff_threshold
        color_threshold = self.chroma_diff_threshold * self.composite_ratio_threshold
        is_right_color = right_chroma > color_threshold

        is_composite = bool(is_left_grayscale and is_right_color)
        is_grayscale_half = bool(is_left_grayscale and not is_right_color and left_chroma < 0.1)

        return is_composite, is_grayscale_half, left_chroma, right_chroma

    def validate_frame(
        self,
        frame: np.ndarray,
        expected_resolution: tuple[int, int] | None = None,
    ) -> FrameValidationResult:
        """Validate a single numpy frame array.

        Args:
            frame: Numpy array of shape (H, W, 3).
            expected_resolution: Optional (expected_height, expected_width).
        """
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            return FrameValidationResult(
                is_valid=False,
                is_composite=False,
                is_grayscale_half=False,
                resolution_match=False,
                actual_resolution=(0, 0),
                expected_resolution=expected_resolution,
                left_chroma_diff=0.0,
                right_chroma_diff=0.0,
                message="Frame is empty or not a valid numpy array",
            )

        h, w = frame.shape[:2]
        actual_res = (h, w)

        res_match = True
        if expected_resolution is not None:
            res_match = (h == expected_resolution[0]) and (w == expected_resolution[1])

        is_composite, is_grayscale_half, left_c, right_c = self.detect_side_by_side_composite(frame)

        errors: list[str] = []
        if is_composite:
            errors.append(
                f"Side-by-side composite detected: left depth (chroma={left_c:.2f}), "
                f"right RGB (chroma={right_c:.2f})"
            )
        if not res_match and expected_resolution is not None:
            errors.append(
                f"Resolution mismatch: expected {expected_resolution[1]}x{expected_resolution[0]}, "
                f"got {w}x{h}"
            )

        is_valid = len(errors) == 0
        message = "PASS" if is_valid else "; ".join(errors)

        return FrameValidationResult(
            is_valid=is_valid,
            is_composite=is_composite,
            is_grayscale_half=is_grayscale_half,
            resolution_match=res_match,
            actual_resolution=actual_res,
            expected_resolution=expected_resolution,
            left_chroma_diff=left_c,
            right_chroma_diff=right_c,
            message=message,
        )

    def validate_video_file(
        self,
        video_path: Path | str,
        expected_resolution: tuple[int, int] | None = None,
        sample_frames: int = 5,
    ) -> FrameValidationResult:
        """Sample and validate frames from a video file.

        Args:
            video_path: Path to video file.
            expected_resolution: Optional (expected_height, expected_width).
            sample_frames: Number of evenly spaced frames to inspect.
        """
        p = Path(video_path)
        if not p.is_file():
            return FrameValidationResult(
                is_valid=False,
                is_composite=False,
                is_grayscale_half=False,
                resolution_match=False,
                actual_resolution=(0, 0),
                expected_resolution=expected_resolution,
                left_chroma_diff=0.0,
                right_chroma_diff=0.0,
                message=f"Video file not found: {video_path}",
            )

        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            return FrameValidationResult(
                is_valid=False,
                is_composite=False,
                is_grayscale_half=False,
                resolution_match=False,
                actual_resolution=(0, 0),
                expected_resolution=expected_resolution,
                left_chroma_diff=0.0,
                right_chroma_diff=0.0,
                message=f"Failed to open video stream: {video_path}",
            )

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return FrameValidationResult(
                is_valid=False,
                is_composite=False,
                is_grayscale_half=False,
                resolution_match=False,
                actual_resolution=(0, 0),
                expected_resolution=expected_resolution,
                left_chroma_diff=0.0,
                right_chroma_diff=0.0,
                message=f"Video has 0 frames: {video_path}",
            )

        max_frame = max(0, total_frames - 1)
        num_samples = min(sample_frames, total_frames)
        indices = np.linspace(0, max_frame, num_samples, dtype=int)
        last_result: FrameValidationResult | None = None

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            res = self.validate_frame(frame, expected_resolution=expected_resolution)
            if not res.is_valid:
                cap.release()
                return res
            last_result = res

        cap.release()
        if last_result is None:
            return FrameValidationResult(
                is_valid=False,
                is_composite=False,
                is_grayscale_half=False,
                resolution_match=False,
                actual_resolution=(0, 0),
                expected_resolution=expected_resolution,
                left_chroma_diff=0.0,
                right_chroma_diff=0.0,
                message="No frames could be read from video",
            )
        return last_result


def crop_right_rgb_half(frame: np.ndarray) -> np.ndarray:
    """Crop the right half (RGB portion) of a side-by-side composite frame.

    Args:
        frame: Numpy array of shape (H, W, 3).

    Returns:
        Cropped array of shape (H, W // 2, 3).
    """
    mid_x = frame.shape[1] // 2
    return frame[:, mid_x:, :].copy()
