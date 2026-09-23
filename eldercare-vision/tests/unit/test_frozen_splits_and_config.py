"""Unit tests for frozen splits and configuration verification (P4-008, ADR-005)."""

from pathlib import Path

import pytest

from eldercare.fall_engine.calibration.freeze import (
    FROZEN_ARTIFACT_DIGESTS,
    assert_frozen_artifacts_intact,
    compute_file_sha256,
    find_repository_root,
    verify_frozen_artifacts,
)
from eldercare.fall_engine.evaluation.manifest import (
    load_manifest,
    validate_manifest_integrity,
)


class TestFrozenSplitsAndConfig:
    """Test suite verifying frozen checksums and structural integrity per ADR-005."""

    @pytest.fixture
    def repo_root(self) -> Path:
        root = find_repository_root()
        assert (root / "config" / "fall_detection.yaml").is_file()
        assert (root / "datasets" / "manifests").is_dir()
        return root

    def test_all_expected_artifacts_exist_in_registry(self) -> None:
        """Verify the frozen registry contains all 4 mandatory artifacts."""
        expected_keys = {
            "config/fall_detection.yaml",
            "datasets/manifests/urfd_manifest.csv",
            "datasets/manifests/upfall_manifest.csv",
            "datasets/manifests/local_manifest.csv",
        }
        assert set(FROZEN_ARTIFACT_DIGESTS.keys()) == expected_keys

    def test_config_matches_frozen_digest(self, repo_root: Path) -> None:
        """Verify config/fall_detection.yaml matches ADR-005 SHA-256 digest."""
        config_path = repo_root / "config" / "fall_detection.yaml"
        digest = compute_file_sha256(config_path, normalize_newlines=True)
        assert digest == FROZEN_ARTIFACT_DIGESTS["config/fall_detection.yaml"]

    def test_urfd_manifest_matches_frozen_digest(self, repo_root: Path) -> None:
        """Verify datasets/manifests/urfd_manifest.csv matches ADR-005 SHA-256 digest."""
        manifest_path = repo_root / "datasets" / "manifests" / "urfd_manifest.csv"
        digest = compute_file_sha256(manifest_path, normalize_newlines=True)
        assert digest == FROZEN_ARTIFACT_DIGESTS["datasets/manifests/urfd_manifest.csv"]

    def test_upfall_manifest_matches_frozen_digest(self, repo_root: Path) -> None:
        """Verify datasets/manifests/upfall_manifest.csv matches ADR-005 SHA-256 digest."""
        manifest_path = repo_root / "datasets" / "manifests" / "upfall_manifest.csv"
        digest = compute_file_sha256(manifest_path, normalize_newlines=True)
        assert digest == FROZEN_ARTIFACT_DIGESTS["datasets/manifests/upfall_manifest.csv"]

    def test_local_manifest_matches_frozen_digest(self, repo_root: Path) -> None:
        """Verify datasets/manifests/local_manifest.csv matches ADR-005 SHA-256 digest."""
        manifest_path = repo_root / "datasets" / "manifests" / "local_manifest.csv"
        digest = compute_file_sha256(manifest_path, normalize_newlines=True)
        assert digest == FROZEN_ARTIFACT_DIGESTS["datasets/manifests/local_manifest.csv"]

    def test_verify_frozen_artifacts_returns_all_passed(self, repo_root: Path) -> None:
        """Verify programmatic verification function returns True for all artifacts."""
        results = verify_frozen_artifacts(repo_root)
        assert len(results) == 4
        for rel_path, is_valid in results.items():
            assert is_valid is True, f"Artifact failed hash verification: {rel_path}"

    def test_assert_frozen_artifacts_intact_succeeds(self, repo_root: Path) -> None:
        """Verify assert_frozen_artifacts_intact completes without error on pristine repo."""
        assert_frozen_artifacts_intact(repo_root)

    def test_compute_file_sha256_missing_file_raises(self, tmp_path: Path) -> None:
        """Verify compute_file_sha256 raises FileNotFoundError on missing file."""
        nonexistent = tmp_path / "nonexistent.file"
        with pytest.raises(FileNotFoundError, match="does not exist"):
            compute_file_sha256(nonexistent)

    def test_assert_frozen_artifacts_intact_detects_mutation(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        """Verify assert_frozen_artifacts_intact detects tampered files in a test directory."""
        # Create a mock repo directory with 1 mutated file
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "fall_detection.yaml").write_text(
            "tampered_content: true\n", encoding="utf-8"
        )

        manifest_dir = tmp_path / "datasets" / "manifests"
        manifest_dir.mkdir(parents=True)
        for name in ["urfd_manifest.csv", "upfall_manifest.csv", "local_manifest.csv"]:
            content = (repo_root / "datasets" / "manifests" / name).read_bytes()
            (manifest_dir / name).write_bytes(content)

        with pytest.raises(RuntimeError) as exc_info:
            assert_frozen_artifacts_intact(tmp_path)

        assert "Frozen artifacts integrity verification failed (ADR-005)" in str(exc_info.value)
        assert "config/fall_detection.yaml: Hash mismatch" in str(exc_info.value)

    def test_frozen_manifests_split_integrity(self, repo_root: Path) -> None:
        """Verify that all frozen manifests load cleanly and maintain split disjointness."""
        for rel_path in [
            "datasets/manifests/urfd_manifest.csv",
            "datasets/manifests/upfall_manifest.csv",
            "datasets/manifests/local_manifest.csv",
        ]:
            manifest_path = repo_root / rel_path
            records = load_manifest(manifest_path)
            assert len(records) > 0, f"Empty manifest: {rel_path}"

            # validate_manifest_integrity raises ValueError if invalid
            validate_manifest_integrity(records)

            dev_samples = {r.sample_id for r in records if r.split == "dev"}
            test_samples = {r.sample_id for r in records if r.split == "test"}
            assert len(dev_samples) > 0, f"Manifest {rel_path} has no dev samples"
            assert len(test_samples) > 0, f"Manifest {rel_path} has no test samples"
            assert dev_samples.isdisjoint(test_samples), f"Leakage: sample overlap in {rel_path}"
