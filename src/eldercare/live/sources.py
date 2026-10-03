"""Video sources the live worker may open: local webcams and server-side video files.

File sources are referenced by ``<kind>:<file name>`` (``upload:`` or ``sample:``),
never by client-supplied paths, so a request cannot open arbitrary files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm"})
MAX_WEBCAM_INDEX = 9
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,200}$")


class SourceError(ValueError):
    """The requested source is malformed or does not exist."""


@dataclass(frozen=True)
class VideoFile:
    ref: str  # "upload:name.mp4" or "sample:name.mp4"
    name: str
    kind: str  # upload | sample
    size_bytes: int
    expected: str | None = None  # sample clips: "fall" | "no_fall" from the URFD file name


@dataclass(frozen=True)
class ResolvedSource:
    source_type: str  # webcam | file
    ref: str
    label: str
    webcam_index: int | None = None
    path: Path | None = None


def safe_file_name(name: str) -> str:
    """Validate a bare video file name (no directories, known extension)."""
    base = Path(name).name
    if base != name or not _SAFE_NAME.match(base) or ".." in base:
        raise SourceError("Invalid file name.")
    if Path(base).suffix.lower() not in VIDEO_EXTENSIONS:
        raise SourceError(f"Unsupported video type; use one of {sorted(VIDEO_EXTENSIONS)}.")
    return base


class SourceCatalog:
    """Resolves source references against the upload and sample directories."""

    def __init__(self, upload_dir: Path, sample_dir: Path | None) -> None:
        self.upload_dir = upload_dir
        self.sample_dir = sample_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _dir_for(self, kind: str) -> Path | None:
        if kind == "upload":
            return self.upload_dir
        if kind == "sample":
            return self.sample_dir
        return None

    def list_files(self) -> list[VideoFile]:
        files: list[VideoFile] = []
        for kind in ("upload", "sample"):
            folder = self._dir_for(kind)
            if folder is None or not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                    expected = None
                    if kind == "sample":
                        lower = path.name.lower()
                        expected = (
                            "fall"
                            if lower.startswith("fall")
                            else "no_fall"
                            if lower.startswith("adl")
                            else None
                        )
                    files.append(
                        VideoFile(
                            ref=f"{kind}:{path.name}",
                            name=path.name,
                            kind=kind,
                            size_bytes=path.stat().st_size,
                            expected=expected,
                        )
                    )
        return files

    def delete_upload(self, name: str) -> bool:
        """Remove an uploaded video by bare file name."""
        path = self.upload_dir / safe_file_name(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def resolve(self, source_type: str, source: str) -> ResolvedSource:
        if source_type == "webcam":
            if not source.isdigit() or not 0 <= int(source) <= MAX_WEBCAM_INDEX:
                raise SourceError(f"Webcam index must be 0-{MAX_WEBCAM_INDEX}.")
            index = int(source)
            return ResolvedSource("webcam", source, f"Webcam {index}", webcam_index=index)
        if source_type == "file":
            kind, _, name = source.partition(":")
            folder = self._dir_for(kind)
            if folder is None:
                raise SourceError("File source must start with 'upload:' or 'sample:'.")
            path = folder / safe_file_name(name)
            if not path.is_file():
                raise SourceError(f"Video file '{name}' was not found.")
            return ResolvedSource("file", source, name, path=path)
        raise SourceError("source_type must be 'webcam' or 'file'.")
