"""P11.7-001 — Evidence quarantine integrity tests.

Guards that quarantined Phase 11 / 11.5 / 11.6 artifacts stay byte-identical (LF-normalised),
that every provenance citation still points at the cited text, and that the FA/h discrepancy
reproduction matches the audit.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "docs" / "reports" / "P11.7-001-evidence-quarantine-index.json"
BUILDER_PATH = ROOT / "experiments" / "v4" / "audit" / "build_evidence_quarantine_index.py"
REPRO_SCRIPT = ROOT / "experiments" / "v4" / "audit" / "reproduce_fa_rate_discrepancy.py"
REPRO_PATH = ROOT / "experiments" / "v4" / "audit" / "P11.7-001-fa-rate-reproduction.json"

# Artifacts named in the Phase 11.7 audit (plan section 0.1) that must be quarantined.
REQUIRED_QUARANTINED = {
    "experiments/v3/holdout/P11.6_006_deployment_holdout_evaluation.json",
    "experiments/v3/holdout/P11.6_006_deployment_holdout_evaluation.md",
    "datasets/manifests/v3_deployment_holdout_manifest.csv",
    "experiments/v3/holdout/holdout_specification.json",
    "docs/reports/P11.6-007-legacy-benchmark-comparison.json",
    "docs/reports/P11.6-007-legacy-benchmark-comparison.md",
    "experiments/v3/candidates/P11.6_002_temporal_benchmark_report.json",
    "experiments/v3/candidates/P11.6_004_pose_backbone_study_report.json",
    "experiments/v3/tracking/P11.6_003_tracking_resilience_report.json",
    "experiments/v3/diagnostics/P11.6_001_root_cause_audit_report.json",
    "experiments/v3/candidates/v3_candidate_freeze_manifest.json",
    "models/temporal_fall_classifier_v3.json",
    "experiments/v3/experiment_log.json",
    "scripts/benchmark/run_v3_system_resilience_audit.py",
    "docs/reports/P11-003-upfall-raw-evaluation.json",
    "docs/reports/P11-004-uat-report.md",
}
EXPECTED_REAL = {
    "docs/reports/P11-002-urfd-raw-evaluation.json",
    "docs/reports/P11.5-005-urfd-raw-evaluation.json",
    "benchmarks/results/p9_004_tensorrt_fp16.json",
}


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_lf(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture(scope="module")
def index() -> dict[str, Any]:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def builder() -> Any:
    return _load_module("build_evidence_quarantine_index", BUILDER_PATH)


def test_index_schema(index: dict[str, Any]) -> None:
    assert index["task_id"] == "P11.7-001"
    assert index["artifact_count"] == len(index["artifacts"])
    classes = set(index["provenance_classes"])
    for entry in index["artifacts"]:
        assert entry["provenance_classes"], entry["path"]
        assert set(entry["provenance_classes"]) <= classes, entry["path"]
        assert entry["affected_metrics"], entry["path"]


def test_required_artifacts_are_quarantined(index: dict[str, Any]) -> None:
    by_path = {e["path"]: e for e in index["artifacts"]}
    missing = REQUIRED_QUARANTINED - set(by_path)
    assert not missing, f"Not indexed: {sorted(missing)}"
    for path in REQUIRED_QUARANTINED:
        assert by_path[path]["deployment_evidence"] is False, path


def test_only_real_artifacts_are_deployment_evidence(index: dict[str, Any]) -> None:
    real = {e["path"] for e in index["artifacts"] if e["deployment_evidence"]}
    assert real == EXPECTED_REAL


def test_quarantined_artifacts_unchanged(index: dict[str, Any]) -> None:
    for entry in index["artifacts"]:
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert _sha256_lf(path) == entry["sha256_lf"], f"Modified: {entry['path']}"


def test_evidence_files_unchanged(index: dict[str, Any]) -> None:
    for rel, digest in index["evidence_file_locks"].items():
        assert _sha256_lf(ROOT / rel) == digest, f"Evidence file changed: {rel}"


def test_evidence_citations_resolve(index: dict[str, Any]) -> None:
    for entry in index["artifacts"]:
        for ev in entry["evidence"]:
            lines = (ROOT / ev["file"]).read_text(encoding="utf-8").splitlines()
            assert 0 < ev["line"] <= len(lines), f"Line out of range: {ev['file']}:{ev['line']}"
            assert ev["pattern"] in lines[ev["line"] - 1], f"{ev['file']}:{ev['line']}"


def test_index_matches_builder_registry(index: dict[str, Any], builder: Any) -> None:
    rebuilt = builder.build_index()
    assert rebuilt == index, "Index is stale; re-run build_evidence_quarantine_index.py"


def test_fa_rate_reproduction_matches_audit() -> None:
    repro = json.loads(REPRO_PATH.read_text(encoding="utf-8"))
    adl = repro["short_adl_clips"]
    streams = repro["long_form_streams"]
    rec = repro["reported_metric_reconstruction"]

    assert repro["fall_clips"] == {"tp": 54, "fn": 0}
    assert adl["count"] == 44 and adl["false_positives"] == 8
    activities = sorted(s["activity"] for s in adl["false_positive_samples"])
    assert activities == ["bending_pick_object"] * 4 + ["normal_lying_down"] * 4
    assert streams["count"] == 6
    assert [s["frames_processed"] for s in streams["per_stream"]] == [360] * 6
    assert streams["seconds_actually_processed"] == pytest.approx(72.0)
    assert streams["declared_hours"] == pytest.approx(26.5)
    assert rec["reported_false_alerts_per_camera_hour"] == pytest.approx(0.301, abs=1e-4)


def test_fa_rate_reproduction_file_is_current() -> None:
    """The saved reproduction must equal a fresh in-memory replay (no hand edits)."""
    module = _load_module("reproduce_fa_rate_discrepancy", REPRO_SCRIPT)
    saved = json.loads(REPRO_PATH.read_text(encoding="utf-8"))
    assert module.reproduce() == saved
