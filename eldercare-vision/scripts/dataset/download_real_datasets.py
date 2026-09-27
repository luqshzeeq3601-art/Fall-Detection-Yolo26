"""Automated Dataset Downloader & Staging Helper (Stage 1 / V6).

Provides automated retrieval tools for:
1. UP-Fall Detection Dataset (via Google Drive links or direct archive URLs).
2. Longform ADL continuous video samples.

Usage:
    python scripts/dataset/download_real_datasets.py --dataset upfall --url <DOWNLOAD_URL_OR_GDRIVE_ID>
    python scripts/dataset/download_real_datasets.py --dataset charades --url <URL>
"""

from __future__ import annotations

import argparse
import logging
import shutil
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("download_datasets")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def download_file(url: str, dest_path: Path) -> Path:
    """Download a file with progress reporting."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("Downloading from %s -> %s", url, dest_path)

    if "drive.google.com" in url or len(url) == 33:  # Google Drive URL or File ID
        try:
            import gdown  # type: ignore

            output = gdown.download(url=url, output=str(dest_path), quiet=False, fuzzy=True)
            if output is None:
                raise RuntimeError("gdown failed to download Google Drive file.")
            return Path(output)
        except ImportError:
            LOG.warning(
                "gdown is not installed. Run 'pip install gdown' for automated Google Drive downloads."
            )
            raise

    # Standard direct HTTP/HTTPS download
    def reporthook(blocknum: int, blocksize: int, totalsize: int) -> None:
        if totalsize > 0 and blocknum % 500 == 0:
            percent = (blocknum * blocksize / totalsize) * 100
            LOG.info(
                "Download progress: %.1f%% (%d / %d MB)",
                min(100.0, percent),
                (blocknum * blocksize) // (1024 * 1024),
                totalsize // (1024 * 1024),
            )

    urlretrieve(url, str(dest_path), reporthook=reporthook)
    LOG.info("Download completed successfully: %s", dest_path)
    return dest_path


def extract_and_organize_upfall(archive_path: Path, target_dir: Path) -> int:
    """Extract and organize UP-Fall video clips into target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    video_extensions = {".mp4", ".avi", ".mkv", ".mov"}
    extracted_count = 0

    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path, "r") as z:
            for member in z.namelist():
                if any(member.lower().endswith(ext) for ext in video_extensions):
                    # Extract video file flatly or into subject subfolder
                    filename = Path(member).name
                    dest = target_dir / filename
                    with z.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted_count += 1
                    LOG.info("Extracted: %s", filename)

    LOG.info("Extracted %d video clips into %s", extracted_count, target_dir)
    return extracted_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and Stage Real Datasets for V6")
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=["upfall", "charades", "generic"],
        help="Dataset identifier to download",
    )
    parser.add_argument(
        "--url", type=str, required=True, help="Download URL or Google Drive file ID"
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Destination directory (defaults to datasets/raw/<dataset>_real)",
    )
    args = parser.parse_args()

    dest_dir = args.dest_dir
    if dest_dir is None:
        if args.dataset == "upfall":
            dest_dir = ROOT / "datasets" / "raw" / "upfall_real"
        elif args.dataset == "charades":
            dest_dir = ROOT / "datasets" / "raw" / "longform_adl"
        else:
            dest_dir = ROOT / "datasets" / "raw" / "downloads"

    tmp_archive = dest_dir / "download_tmp.zip"
    download_file(args.url, tmp_archive)

    if tmp_archive.suffix.lower() == ".zip":
        extract_and_organize_upfall(tmp_archive, dest_dir)
        tmp_archive.unlink(missing_ok=True)

    LOG.info(
        "Staging complete. Run 'python scripts/dataset/ingest_v6.py' to build the master manifest."
    )


if __name__ == "__main__":
    main()
