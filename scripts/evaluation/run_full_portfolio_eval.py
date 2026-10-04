"""Script to execute full portfolio evaluation on frozen Test-B split and export required artifacts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.evaluation.portfolio_evaluator import PortfolioEvaluationRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("run_full_portfolio_eval")


def main() -> None:
    models_dir = ROOT / "models" / "v6_3_phase3b"
    manifest_path = ROOT / "datasets" / "manifests" / "v6_master_manifest.json"
    cache_dir = ROOT / "datasets" / "cache" / "poses_mp"
    output_dir = ROOT / "results" / "evaluation"
    report_file = ROOT / "docs" / "results" / "EVALUATION_REPORT.md"

    LOG.info("Initializing PortfolioEvaluationRunner...")
    runner = PortfolioEvaluationRunner(
        models_dir=models_dir,
        manifest_path=manifest_path,
        cache_dir=cache_dir,
        allow_sealed=True,
    )

    LOG.info("Evaluating split 'test_b' (132 sequences)...")
    results = runner.evaluate_split("test_b", test_id_prefix="TEST-B")
    LOG.info("Evaluated %d sequences.", len(results))

    pred_csv, metrics_json, scenario_csv, rep_md = runner.export_results(
        results=results,
        output_dir=output_dir,
        report_path=report_file,
    )

    LOG.info("Exported predictions: %s", pred_csv)
    LOG.info("Exported metrics: %s", metrics_json)
    LOG.info("Exported per-scenario: %s", scenario_csv)
    LOG.info("Exported report: %s", rep_md)


if __name__ == "__main__":
    main()
