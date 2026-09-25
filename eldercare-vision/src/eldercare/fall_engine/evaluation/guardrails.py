"""Metric integrity guardrails, provenance, hardcoded-gate, and label-leak detectors.

Part of Phase 11.7 deployment hardening (P11.7-002).
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
QUARANTINE_INDEX_PATH = ROOT / "docs" / "reports" / "P11.7-001-evidence-quarantine-index.json"


def sha256_lf(path: Path | str) -> str:
    """Compute LF-normalised sha256 hash of a file."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


class ProvenanceValidationError(Exception):
    """Raised when an evaluation artifact fails provenance validation."""


class MetricIntegrityGuard:
    """Validates metric dictionaries and reports for provenance and calculation integrity."""

    def __init__(self, quarantine_index_path: Path | str | None = None) -> None:
        self.quarantine_path = Path(quarantine_index_path or QUARANTINE_INDEX_PATH)
        self.quarantined_paths: set[str] = set()
        if self.quarantine_path.is_file():
            index = json.loads(self.quarantine_path.read_text(encoding="utf-8"))
            for art in index.get("artifacts", []):
                if not art.get("deployment_evidence", False):
                    self.quarantined_paths.add(art.get("path", ""))

    def validate_metrics_dict(self, data: dict[str, Any], artifact_rel_path: str = "") -> list[str]:
        """Validate a metrics dictionary for deployment evidence integrity.

        Returns:
            List of violation error messages (empty if completely valid).
        """
        violations: list[str] = []

        is_deployment = data.get("deployment_evidence", False)
        provenance = data.get("provenance", "")

        # Rule 1: Quarantined artifacts cannot be claimed as deployment evidence
        if artifact_rel_path and artifact_rel_path in self.quarantined_paths:
            if is_deployment:
                violations.append(
                    f"Artifact '{artifact_rel_path}' is quarantined in P11.7-001 "
                    "and cannot have deployment_evidence=True."
                )

        # Rule 2: If deployment_evidence is True, provenance MUST be 'real_measured'
        if is_deployment and provenance != "real_measured":
            violations.append(
                f"Deployment evidence requires provenance='real_measured', but got '{provenance}'."
            )

        # Rule 3: Deployment evidence must have cryptographic hashes of source files
        if is_deployment:
            hashes = data.get("source_file_hashes", {})
            if not hashes or not isinstance(hashes, dict):
                violations.append(
                    "Deployment evidence requires non-empty 'source_file_hashes' mapping."
                )
            else:
                for rel_p, expected_hash in hashes.items():
                    full_p = ROOT / rel_p
                    if not full_p.is_file():
                        violations.append(f"Source file '{rel_p}' does not exist on disk.")
                    else:
                        actual_hash = sha256_lf(full_p)
                        if actual_hash != expected_hash:
                            violations.append(
                                f"Source file '{rel_p}' hash mismatch: "
                                f"expected {expected_hash}, got {actual_hash}."
                            )

        # Rule 4: Denominator separation check
        # Short clips must not be mixed into long-form camera hours
        if "long_form_processed_camera_hours" in data:
            lf_hours = data["long_form_processed_camera_hours"]
            lf_alerts = data.get("long_form_false_alert_count", 0)
            lf_rate = data.get("long_form_false_alerts_per_camera_hour", 0.0)

            if lf_hours > 0:
                expected_rate = round(lf_alerts / lf_hours, 4)
                if abs(lf_rate - expected_rate) > 0.001:
                    violations.append(
                        f"Long-form FA rate mismatch: recorded {lf_rate}, "
                        f"but {lf_alerts} / {lf_hours} = {expected_rate}."
                    )
            elif lf_alerts > 0:
                violations.append(
                    f"Long-form alerts recorded ({lf_alerts}) but processed camera hours is 0."
                )

        # Rule 5: Actual processed seconds must be backed by actual frames
        if is_deployment and "actual_processed_seconds" in data:
            proc_sec = data["actual_processed_seconds"]
            dec_frames = data.get("actual_decoded_frames", 0)
            if proc_sec > 0 and dec_frames <= 0:
                violations.append(
                    f"Actual processed seconds is {proc_sec}s "
                    f"but actual_decoded_frames is {dec_frames}."
                )

        return violations


class HardcodedGateValueDetector:
    """Scans Python code ASTs for hardcoded evaluation outcomes and literal gate constants."""

    SUSPICIOUS_LITERAL_METRICS: set[str] = {
        "recall",
        "precision",
        "f1",
        "f2",
        "f2_score",
        "missed_fall_rate",
        "false_alerts_per_camera_hour",
        "pose_availability_rate",
        "track_continuity_rate",
        "id_switch_rate",
        "e2e_alert_latency",
        "median_tta",
        "p95_tta",
    }

    def scan_file(self, file_path: Path | str) -> list[dict[str, Any]]:
        """Parse Python file and detect hardcoded dictionary constants for metric gates.

        Returns:
            List of findings with file, line, metric, and suspicious constant value.
        """
        p = Path(file_path)
        if not p.is_file():
            return []

        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            # Check for dict literals assigning float constants to metric names
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=True):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        key_str = k.value.lower()
                        if key_str in self.SUSPICIOUS_LITERAL_METRICS:
                            if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)):
                                # Hardcoded gate targets in check_deployment_gates are allowed;
                                # hardcoded outcomes in runners are flagged
                                findings.append(
                                    {
                                        "file": str(p),
                                        "line": node.lineno,
                                        "metric": key_str,
                                        "literal_value": v.value,
                                    }
                                )

        return findings


class LabelLeakageDetector:
    """Detects if an evaluator passes ground-truth labels into model observation generators."""

    LABEL_NAMES: set[str] = {"is_fall", "ground_truth", "label", "target", "fall_class"}

    def scan_file(self, file_path: Path | str) -> list[dict[str, Any]]:
        """Scan file for patterns where observation generators branch on labels."""
        p = Path(file_path)
        if not p.is_file():
            return []

        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            # Check for: is_fall = int(record["is_fall"]) == 1
            # followed by observation synthesis branching on is_fall
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in self.LABEL_NAMES:
                        findings.append(
                            {
                                "file": str(p),
                                "line": node.lineno,
                                "target": target.id,
                                "context": "Ground truth assignment in evaluation code",
                            }
                        )

        return findings
