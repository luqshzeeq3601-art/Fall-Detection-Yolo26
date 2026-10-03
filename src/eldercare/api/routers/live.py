"""Live video: sources, uploads, stream start/stop, MJPEG stream, snapshots, telemetry."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from eldercare.api.dependencies import get_db, get_live_manager
from eldercare.db.models import Camera, CameraSource
from eldercare.live.manager import CameraBusyError, LiveManager
from eldercare.live.sources import SourceError, safe_file_name

router = APIRouter(tags=["Live"])

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB
_CHUNK = 1024 * 1024
_BOUNDARY = "frame"


class StreamStart(BaseModel):
    source_type: Literal["webcam", "file"] | None = None
    source: str | None = Field(default=None, max_length=255)
    loop: bool | None = None

    model_config = ConfigDict(extra="forbid")


class SourceTest(BaseModel):
    source_type: Literal["webcam", "file"]
    source: str = Field(..., max_length=255)

    model_config = ConfigDict(extra="forbid")


class SourceStart(BaseModel):
    source_type: Literal["webcam", "file"]
    source: str = Field(..., max_length=255)
    loop: bool = False

    model_config = ConfigDict(extra="forbid")


class CameraSourceRead(BaseModel):
    camera_id: str
    source_type: str
    source: str
    room: str | None
    loop: bool

    model_config = ConfigDict(from_attributes=True)


class CameraSourceWrite(BaseModel):
    source_type: Literal["webcam", "file"]
    source: str = Field(..., min_length=1, max_length=255)
    room: str | None = Field(default=None, max_length=128)
    loop: bool = False

    model_config = ConfigDict(extra="forbid")


def _source_error(exc: SourceError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/live/sources")
def list_sources(manager: Annotated[LiveManager, Depends(get_live_manager)]) -> dict[str, Any]:
    """Webcam indexes and the server's uploaded/sample video files."""
    return {
        "webcams": [{"source": str(i), "label": f"Webcam {i}"} for i in range(3)],
        "files": [f.__dict__ for f in manager.catalog.list_files()],
    }


@router.post("/live/uploads", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile,
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> dict[str, Any]:
    """Store a video file for analysis; returns its source reference."""
    try:
        name = safe_file_name(file.filename or "")
    except SourceError as exc:
        raise _source_error(exc) from exc
    target = manager.catalog.upload_dir / name
    tmp = target.with_suffix(target.suffix + ".part")
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Video exceeds the 1 GiB limit."
                    )
                out.write(chunk)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"ref": f"upload:{name}", "name": name, "kind": "upload", "size_bytes": size}


@router.get("/live/cameras")
async def detect_cameras(
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> dict[str, Any]:
    """Probe this server's webcams (indexes 0-4) and report which deliver frames."""
    return {"cameras": await asyncio.to_thread(manager.scan_cameras)}


@router.delete("/live/uploads/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    name: str, manager: Annotated[LiveManager, Depends(get_live_manager)]
) -> Response:
    """Delete an uploaded video (incidents already recorded from it are kept)."""
    for session in manager.statuses():
        if session["active"] and session["source"] == f"upload:{name}":
            raise HTTPException(status.HTTP_409_CONFLICT, "Stop the analysis before deleting.")
    try:
        removed = manager.catalog.delete_upload(name)
    except SourceError as exc:
        raise _source_error(exc) from exc
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/live/start")
def start_source(
    payload: SourceStart,
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> dict[str, Any]:
    """Start detection on a webcam or video file without choosing a camera first."""
    try:
        camera_id = manager.camera_for_source(payload.source_type, payload.source)
        return manager.start(camera_id, payload.source_type, payload.source, payload.loop)
    except SourceError as exc:
        raise _source_error(exc) from exc
    except CameraBusyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Camera '{exc}' is already running. Stop it before starting another source.",
        ) from exc


@router.get("/live/status")
def live_status(manager: Annotated[LiveManager, Depends(get_live_manager)]) -> dict[str, Any]:
    """State of every stream started since the server came up."""
    return {"sessions": manager.statuses(), "metrics": manager.stream_metrics()}


@router.post("/live/test")
def test_source(
    payload: SourceTest, manager: Annotated[LiveManager, Depends(get_live_manager)]
) -> dict[str, Any]:
    """Open a source and read one frame."""
    try:
        ok, detail = manager.test_source(payload.source_type, payload.source)
    except SourceError as exc:
        raise _source_error(exc) from exc
    return {"ok": ok, "detail": detail}


@router.get("/live/camera-sources", response_model=list[CameraSourceRead])
def list_camera_sources(db: Annotated[Session, Depends(get_db)]) -> list[CameraSource]:
    return list(db.scalars(select(CameraSource).order_by(CameraSource.camera_id)).all())


@router.put("/cameras/{camera_id}/source", response_model=CameraSourceRead)
def set_camera_source(
    camera_id: str,
    payload: CameraSourceWrite,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> CameraSource:
    """Assign a webcam or video file to a camera (validated, applied on next start)."""
    if db.get(Camera, camera_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Camera '{camera_id}' not found.")
    try:
        manager.catalog.resolve(payload.source_type, payload.source)
    except SourceError as exc:
        raise _source_error(exc) from exc
    row = db.get(CameraSource, camera_id)
    if row is None:
        row = CameraSource(camera_id=camera_id, source_type=payload.source_type, source="")
        db.add(row)
    row.source_type = payload.source_type
    row.source = payload.source
    row.room = (payload.room or "").strip() or None
    row.loop = payload.loop
    db.commit()
    db.refresh(row)
    return row


@router.post("/cameras/{camera_id}/stream/start")
def start_stream(
    camera_id: str,
    payload: StreamStart,
    manager: Annotated[LiveManager, Depends(get_live_manager)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Start live fall detection on the camera's (or the given) source."""
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Camera '{camera_id}' not found.")
    if not camera.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Camera is disabled. Enable it in Settings.")
    try:
        return manager.start(camera_id, payload.source_type, payload.source, payload.loop)
    except SourceError as exc:
        raise _source_error(exc) from exc
    except CameraBusyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"This source is already streaming on camera '{exc}'."
        ) from exc


@router.post("/cameras/{camera_id}/stream/stop")
def stop_stream(
    camera_id: str, manager: Annotated[LiveManager, Depends(get_live_manager)]
) -> dict[str, Any]:
    return {"stopped": manager.stop(camera_id)}


@router.get("/cameras/{camera_id}/stream.mjpg")
async def mjpeg_stream(
    camera_id: str,
    request: Request,
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> StreamingResponse:
    """Annotated frames as multipart/x-mixed-replace (usable directly in an <img>)."""
    session = manager.get(camera_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No stream for this camera.")

    async def frames() -> AsyncIterator[bytes]:
        seq = -1
        while not await request.is_disconnected():
            new_seq, jpeg = await asyncio.to_thread(session.wait_frame, seq, 1.0)
            if jpeg is not None and new_seq != seq:
                seq = new_seq
                yield (
                    (
                        f"--{_BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                        f"Content-Length: {len(jpeg)}\r\n\r\n"
                    ).encode()
                    + jpeg
                    + b"\r\n"
                )
            elif not session.active:
                break

    return StreamingResponse(
        frames(),
        media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/cameras/{camera_id}/snapshot.jpg")
def snapshot(
    camera_id: str, manager: Annotated[LiveManager, Depends(get_live_manager)]
) -> Response:
    """Latest annotated frame as a JPEG download."""
    session = manager.get(camera_id)
    jpeg = session.latest_jpeg() if session else None
    if jpeg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No frame available yet.")
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{camera_id}-snapshot.jpg"',
        },
    )


@router.get("/system/metrics")
def system_metrics(
    manager: Annotated[LiveManager, Depends(get_live_manager)],
) -> dict[str, Any]:
    """Current host/stream telemetry plus the last five minutes of 2-second samples."""
    return {"current": manager.latest(), "history": manager.history()}
