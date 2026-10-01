"""Unit tests for FrameValidator (P11.8-003).

Verifies detection and rejection of side-by-side composite frames (depth+RGB),
grayscale halves, resolution mismatches, and right-half cropping utility.
"""

from __future__ import annotations

import numpy as np
import pytest

from eldercare.fall_engine.dataset.frame_validator import (
    FrameValidator,
    crop_right_rgb_half,
)


@pytest.fixture
def validator() -> FrameValidator:
    return FrameValidator()


def test_validator_accepts_clean_rgb_frame(validator: FrameValidator) -> None:
    """Natural color RGB frame with color variation must pass validation."""
    # Create RGB frame with color variation (H=480, W=640, C=3)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:, :, 0] = 50  # B
    frame[:, :, 1] = 120  # G
    frame[:, :, 2] = 200  # R

    result = validator.validate_frame(frame, expected_resolution=(480, 640))
    assert result.is_valid is True
    assert result.is_composite is False
    assert result.resolution_match is True
    assert result.message == "PASS"


def test_validator_rejects_side_by_side_composite(validator: FrameValidator) -> None:
    """Frame with left grayscale depth map and right color RGB must be rejected."""
    frame = np.zeros((240, 640, 3), dtype=np.uint8)

    # Left half: grayscale depth map (R=G=B)
    gray_pattern = np.arange(240 * 320, dtype=np.uint8).reshape((240, 320)) % 255
    frame[:, :320, 0] = gray_pattern
    frame[:, :320, 1] = gray_pattern
    frame[:, :320, 2] = gray_pattern

    # Right half: color RGB image
    frame[:, 320:, 0] = 30  # Blue
    frame[:, 320:, 1] = 150  # Green
    frame[:, 320:, 2] = 220  # Red

    result = validator.validate_frame(frame)
    assert result.is_valid is False
    assert result.is_composite is True
    assert "Side-by-side composite detected" in result.message
    assert result.left_chroma_diff < 0.1
    assert result.right_chroma_diff > 10.0


def test_validator_rejects_resolution_mismatch(validator: FrameValidator) -> None:
    """Frame with unexpected dimensions must be rejected."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:, :, 1] = 100
    frame[:, :, 2] = 180

    result = validator.validate_frame(frame, expected_resolution=(480, 640))
    assert result.is_valid is False
    assert result.resolution_match is False
    assert "Resolution mismatch" in result.message


def test_validator_handles_empty_or_corrupt_frame(validator: FrameValidator) -> None:
    """Empty or non-array inputs must fail cleanly without unhandled exceptions."""
    empty_frame = np.empty((0, 0, 3), dtype=np.uint8)
    result = validator.validate_frame(empty_frame)
    assert result.is_valid is False
    assert "empty" in result.message.lower()


def test_crop_right_rgb_half() -> None:
    """Cropping utility must extract the right half of a composite frame."""
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, :100, :] = 50
    frame[:, 100:, :] = 150

    cropped = crop_right_rgb_half(frame)
    assert cropped.shape == (100, 100, 3)
    assert np.all(cropped == 150)
