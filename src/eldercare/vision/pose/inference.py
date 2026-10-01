"""Pose inference boundary: predictor surface + Ultralytics production class (P2-004).

This is the ONLY Phase 2 file allowed to mention ``ultralytics`` — and only
via a LAZY import inside :meth:`UltralyticsPosePredictor.predict`, so CPU CI
collection never requires CUDA, weights, or the package itself. No ``torch`` /
``cv2`` import here (not even lazily), no inference at import time, no threads.

Production contract (P2-002 acceptance record, ``verify_pose_model.py``):
``YOLO("yolo26s-pose.pt")`` + ``predict(source=image, device=0, imgsz=640,
verbose=False)[0]`` yields a single ``Results`` with ``keypoints.xy`` shaped
``(N, 17, 2)``, ``keypoints.conf`` shaped ``(N, 17)``, on ``cuda:0``
(``bus.jpg``: 4 persons). Fakes implement the :class:`PosePredictor` surface
below and return duck-typed ``Results`` with ``keypoints`` / ``boxes`` /
``orig_shape`` as consumed by ``adapt_pose_results``.
"""

from __future__ import annotations

from typing import Any, Protocol


class PosePredictor(Protocol):
    """Minimal inference surface the pipeline depends on.

    Fakes implement this method and return a single duck-typed Ultralytics
    ``Results`` (attributes ``keypoints`` / ``boxes`` / ``orig_shape``).
    """

    def predict(self, image: Any) -> Any:
        """Run pose inference on one image; return a single ``Results``."""
        ...


class UltralyticsPosePredictor:
    """Production :class:`PosePredictor` over ``YOLO(model_name)``.

    Args:
        model_name: Weights file (default ``"yolo26s-pose.pt"`` per
            CONSTRAINTS §2; resolved through the Ultralytics cache).
        device: Inference device (default ``0`` = ``cuda:0`` per CONSTRAINTS §2).
        imgsz: Square inference size (default ``640`` per CONSTRAINTS §2).

    The model loads once on first :meth:`predict`. No thresholding, no
    adaptation, no ``Results`` retention beyond the return.
    """

    def __init__(
        self,
        model_name: str = "yolo26s-pose.pt",
        device: int = 0,
        imgsz: int = 640,
    ) -> None:
        if not isinstance(model_name, str) or not model_name:
            raise ValueError(f"model_name must be a non-empty string, got {model_name!r}")
        if isinstance(device, bool) or not isinstance(device, int):
            raise TypeError(f"device must be an int, got {device!r}")
        if isinstance(imgsz, bool) or not isinstance(imgsz, int) or imgsz <= 0:
            raise ValueError(f"imgsz must be a positive int, got {imgsz!r}")
        self._model_name = model_name
        self._device = device
        self._imgsz = imgsz
        self._model: Any = None

    @property
    def model_name(self) -> str:
        """Configured weights file name."""
        return self._model_name

    @property
    def device(self) -> int:
        """Configured inference device."""
        return self._device

    @property
    def imgsz(self) -> int:
        """Configured square inference size."""
        return self._imgsz

    def predict(self, image: Any) -> Any:
        """Run ``YOLO.predict`` on one image; return the single ``Results``.

        Raises:
            ValueError: if the backend returns an empty result list
                (fail closed — never fabricate a pose).
        """
        from ultralytics import YOLO

        if self._model is None:
            self._model = YOLO(self._model_name)
        results = self._model.predict(
            source=image, device=self._device, imgsz=self._imgsz, verbose=False
        )
        if not results:
            raise ValueError(
                "Ultralytics predictor returned no results: refusing to fabricate a pose"
            )
        return results[0]

    def __repr__(self) -> str:
        return (
            f"UltralyticsPosePredictor(model_name={self._model_name!r}, "
            f"device={self._device!r}, imgsz={self._imgsz!r})"
        )
