"""V4 Dataset Annotation & QA Verification Framework (P11.7-007).

Validates bounding boxes, 17-keypoint anatomical consistency, temporal fall onsets,
impact terminations, and lying durations to ensure zero annotation defects.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from eldercare.vision.pose.adapter import PersonPose

logger = logging.getLogger("annotation_qa")


@dataclass(frozen=True)
class TemporalIntervalAudit:
    """Audit result for a single sequence's temporal intervals."""

    sequence_id: str
    is_fall: bool
    is_valid: bool
    fall_duration_frames: int
    fall_duration_seconds: float
    lying_duration_frames: int
    lying_duration_seconds: float
    defects: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PoseGeometryAudit:
    """Audit result for bounding box and 17-keypoint geometry."""

    is_valid: bool
    bbox_valid: bool
    aspect_ratio: float
    present_keypoint_count: int
    mean_confidence: float
    torso_length_pixels: float
    defects: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetQAAuditResult:
    """Comprehensive dataset QA audit report."""

    total_sequences: int
    fall_sequences: int
    adl_sequences: int
    valid_sequences: int
    defective_sequences: int
    temporal_compliance_rate: float
    overall_qa_status: str
    temporal_audits: list[TemporalIntervalAudit]
    defects: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["temporal_audits"] = [a.to_dict() for a in self.temporal_audits]
        return d


class AnnotationQAVerifier:
    """Verifies dataset annotation integrity, bounding boxes, and temporal boundaries."""

    def __init__(
        self,
        min_fall_duration_sec: float = 0.2,
        max_fall_duration_sec: float = 3.5,
        min_lying_duration_sec: float = 0.1,
    ) -> None:
        self.min_fall_duration_sec = min_fall_duration_sec
        self.max_fall_duration_sec = max_fall_duration_sec
        self.min_lying_duration_sec = min_lying_duration_sec

    def validate_temporal_sequence(self, record: dict[str, Any]) -> TemporalIntervalAudit:
        """Validate temporal boundary annotations for a video record."""
        seq_id = record.get("sequence_id", "unknown")
        is_fall = bool(record.get("is_fall", False))
        frame_cnt = int(record.get("frame_count", 0))
        fps = float(record.get("fps", 30.0))
        if fps <= 0:
            fps = 30.0

        defects: list[str] = []
        fall_dur_f = 0
        fall_dur_s = 0.0
        lying_dur_f = 0
        lying_dur_s = 0.0

        f_start = record.get("fall_start_frame")
        f_end = record.get("fall_end_frame")
        l_start = record.get("lying_start_frame")

        if is_fall:
            if f_start is None or f_end is None or l_start is None:
                defects.append("Missing fall interval boundaries in fall sequence")
            else:
                f_start = int(f_start)
                f_end = int(f_end)
                l_start = int(l_start)

                if f_start < 1:
                    defects.append(f"fall_start_frame ({f_start}) < 1")
                if f_end < f_start:
                    defects.append(f"fall_end_frame ({f_end}) < fall_start_frame ({f_start})")
                if l_start < f_end:
                    defects.append(f"lying_start_frame ({l_start}) < fall_end_frame ({f_end})")
                if l_start > frame_cnt:
                    defects.append(
                        f"lying_start_frame ({l_start}) exceeds frame_count ({frame_cnt})"
                    )

                fall_dur_f = f_end - f_start + 1
                fall_dur_s = fall_dur_f / fps
                lying_dur_f = max(0, frame_cnt - l_start + 1)
                lying_dur_s = lying_dur_f / fps

                if fall_dur_s < self.min_fall_duration_sec:
                    defects.append(
                        f"Fall duration {fall_dur_s:.2f}s is below "
                        f"minimum {self.min_fall_duration_sec}s"
                    )
                if fall_dur_s > self.max_fall_duration_sec:
                    defects.append(
                        f"Fall duration {fall_dur_s:.2f}s exceeds "
                        f"maximum {self.max_fall_duration_sec}s"
                    )
                if lying_dur_s < self.min_lying_duration_sec:
                    defects.append(
                        f"Lying duration {lying_dur_s:.2f}s is below "
                        f"minimum {self.min_lying_duration_sec}s"
                    )
        else:
            # ADL sequences must NOT have fall intervals
            if f_start is not None and str(f_start).strip() != "":
                defects.append(f"ADL sequence contains non-null fall_start_frame ({f_start})")
            if f_end is not None and str(f_end).strip() != "":
                defects.append(f"ADL sequence contains non-null fall_end_frame ({f_end})")
            if l_start is not None and str(l_start).strip() != "":
                defects.append(f"ADL sequence contains non-null lying_start_frame ({l_start})")

        is_valid = len(defects) == 0
        return TemporalIntervalAudit(
            sequence_id=seq_id,
            is_fall=is_fall,
            is_valid=is_valid,
            fall_duration_frames=fall_dur_f,
            fall_duration_seconds=round(fall_dur_s, 3),
            lying_duration_frames=lying_dur_f,
            lying_duration_seconds=round(lying_dur_s, 3),
            defects=defects,
        )

    def validate_pose_geometry(
        self,
        pose: PersonPose,
        image_width: int,
        image_height: int,
    ) -> PoseGeometryAudit:
        """Validate bounding box and 17-keypoint anatomical consistency."""
        defects: list[str] = []
        x1, y1, x2, y2 = pose.bbox_xyxy

        # 1. Bounding box validity
        bw = x2 - x1
        bh = y2 - y1
        bbox_valid = True

        if bw <= 0 or bh <= 0:
            defects.append(f"Degenerate bounding box: width={bw:.1f}, height={bh:.1f}")
            bbox_valid = False
        if x1 < -10 or y1 < -10 or x2 > image_width + 10 or y2 > image_height + 10:
            defects.append(
                f"Bounding box {(x1, y1, x2, y2)} significantly outside "
                f"image ({image_width}x{image_height})"
            )
            bbox_valid = False

        aspect_ratio = bw / bh if bh > 0 else 0.0
        if aspect_ratio < 0.05 or aspect_ratio > 20.0:
            defects.append(f"Extreme bounding box aspect ratio: {aspect_ratio:.2f}")

        # 2. Keypoints audit
        kpts = pose.keypoints
        if len(kpts) != 17:
            defects.append(f"Keypoint count is {len(kpts)}, expected 17")

        present_kpts = [k for k in kpts if k.present and k.x is not None and k.y is not None]
        mean_conf = (
            sum(k.confidence for k in present_kpts) / len(present_kpts) if present_kpts else 0.0
        )

        # 3. Keypoint containment check (keypoints should lie within bbox margin)
        margin_x = max(20.0, bw * 0.25)
        margin_y = max(20.0, bh * 0.25)
        for idx, k in enumerate(present_kpts):
            if (
                k.x < x1 - margin_x
                or k.x > x2 + margin_x
                or k.y < y1 - margin_y
                or k.y > y2 + margin_y
            ):
                defects.append(f"Keypoint {idx} at ({k.x:.1f}, {k.y:.1f}) lies far outside bbox")

        # 4. Anatomical torso length check
        # COCO indices: left_shoulder=5, right_shoulder=6, left_hip=11, right_hip=12
        torso_len = 0.0
        if len(kpts) == 17:
            ls, rs = kpts[5], kpts[6]
            lh, rh = kpts[11], kpts[12]
            if (
                ls.present
                and rs.present
                and lh.present
                and rh.present
                and ls.x is not None
                and rs.x is not None
                and lh.x is not None
                and rh.x is not None
                and ls.y is not None
                and rs.y is not None
                and lh.y is not None
                and rh.y is not None
            ):
                mid_sh_x = (ls.x + rs.x) / 2.0
                mid_sh_y = (ls.y + rs.y) / 2.0
                mid_hip_x = (lh.x + rh.x) / 2.0
                mid_hip_y = (lh.y + rh.y) / 2.0
                torso_len = math.hypot(mid_sh_x - mid_hip_x, mid_sh_y - mid_hip_y)
                if torso_len <= 1.0:
                    defects.append(f"Collapsed torso length: {torso_len:.1f} pixels")

        is_valid = len(defects) == 0
        return PoseGeometryAudit(
            is_valid=is_valid,
            bbox_valid=bbox_valid,
            aspect_ratio=round(aspect_ratio, 3),
            present_keypoint_count=len(present_kpts),
            mean_confidence=round(mean_conf, 3),
            torso_length_pixels=round(torso_len, 2),
            defects=defects,
        )

    def audit_manifest(self, manifest_path: Path | str) -> DatasetQAAuditResult:
        """Run full QA audit over all records in manifest."""
        path = Path(manifest_path)
        if not path.is_file():
            raise FileNotFoundError(f"Manifest not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records", [])
        total_seqs = len(records)
        falls = sum(1 for r in records if r.get("is_fall"))
        adls = total_seqs - falls

        audits: list[TemporalIntervalAudit] = []
        all_defects: list[str] = []

        for r in records:
            audit = self.validate_temporal_sequence(r)
            audits.append(audit)
            if not audit.is_valid:
                for d in audit.defects:
                    all_defects.append(f"[{audit.sequence_id}] {d}")

        valid_count = sum(1 for a in audits if a.is_valid)
        defective_count = total_seqs - valid_count
        compliance = valid_count / total_seqs if total_seqs > 0 else 0.0
        status = "PASS" if defective_count == 0 else "FAIL"

        return DatasetQAAuditResult(
            total_sequences=total_seqs,
            fall_sequences=falls,
            adl_sequences=adls,
            valid_sequences=valid_count,
            defective_sequences=defective_count,
            temporal_compliance_rate=round(compliance, 4),
            overall_qa_status=status,
            temporal_audits=audits,
            defects=all_defects,
        )
