"""Download official UR Fall Detection Dataset (URFD) RGB videos (cam0).

Source: University of Rzeszow (http://fenix.ur.edu.pl/~mkepski/ds/uf.html)
"""

from __future__ import annotations

import logging
import sys
import time
import urllib.request
from pathlib import Path

from eldercare.fall_engine.evaluation.manifest import load_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_urfd")

BASE_URL = "http://fenix.ur.edu.pl/~mkepski/ds/data"


def download_urfd(
    manifest_path: Path | None = None,
    output_base_dir: Path | None = None,
    split_filter: str | None = None,
) -> int:
    """Download URFD cam0 mp4 videos defined in manifest."""
    root = Path(__file__).resolve().parent.parent.parent
    manifest_file = manifest_path or (root / "datasets" / "manifests" / "urfd_manifest.csv")
    out_dir = output_base_dir or (root / "datasets" / "raw" / "urfd")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_file.is_file():
        logger.error(f"Manifest not found: {manifest_file}")
        return 1

    records = load_manifest(manifest_file)
    if split_filter:
        records = [r for r in records if r.split == split_filter]

    logger.info(f"Loaded {len(records)} records from {manifest_file.name} (filter={split_filter})")

    downloaded = 0
    skipped = 0
    failed = 0

    for idx, rec in enumerate(records, start=1):
        filename = Path(rec.path_local).name
        dest = out_dir / filename
        if dest.is_file() and dest.stat().st_size > 10000:
            logger.info(
                f"[{idx}/{len(records)}] Already exists: {filename} ({dest.stat().st_size} bytes)"
            )
            skipped += 1
            continue

        url = f"{BASE_URL}/{filename}"
        logger.info(f"[{idx}/{len(records)}] Downloading {url} -> {dest.name}")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
                chunk = resp.read()
                f.write(chunk)
            downloaded += 1
            logger.info(f"  ✓ Saved {filename} ({len(chunk)} bytes)")
            time.sleep(0.1)  # friendly rate limit
        except Exception as e:
            logger.error(f"  ✗ Failed downloading {filename}: {e}")
            if dest.exists():
                dest.unlink()
            failed += 1

    logger.info(
        "URFD Download Summary: %d downloaded, %d existing, %d failed (Total: %d)",
        downloaded,
        skipped,
        failed,
        len(records),
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(download_urfd(split_filter=split))
