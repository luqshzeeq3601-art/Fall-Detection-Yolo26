"""SQLAlchemy 2.0 ORM persistence models for ElderCare Vision (P5-001)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eldercare.db.base import Base


def _utc_now() -> datetime:
    """Return current UTC timestamp with timezone awareness."""
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    """Generate a standard UUID string representation."""
    return str(uuid.uuid4())


class Camera(Base):
    """Camera persistent entity."""

    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_frame_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    incidents: Mapped[list[Incident]] = relationship(
        "Incident", back_populates="camera", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Camera(id='{self.id}', name='{self.name}', status='{self.status}')>"


class Incident(Base):
    """Detected fall incident entity."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    camera_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    detector_state: Mapped[str] = mapped_column(
        String(64), default="FALL_CONFIRMED", nullable=False
    )
    fall_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    config_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_features: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    camera: Mapped[Camera] = relationship("Camera", back_populates="incidents")
    evidence: Mapped[list[IncidentEvidence]] = relationship(
        "IncidentEvidence", back_populates="incident", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[IncidentReview]] = relationship(
        "IncidentReview", back_populates="incident", cascade="all, delete-orphan"
    )
    enrichments: Mapped[list[AgentEnrichment]] = relationship(
        "AgentEnrichment", back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_incidents_camera_confirmed", "camera_id", confirmed_at.desc()),
        Index("ix_incidents_confirmed_at", confirmed_at.desc()),
    )

    def __repr__(self) -> str:
        return (
            f"<Incident(id='{self.id}', camera_id='{self.camera_id}', "
            f"track_id='{self.track_id}', score={self.fall_score})>"
        )


class IncidentEvidence(Base):
    """Media evidence (snapshot or video clip) associated with an incident."""

    __tablename__ = "incident_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="evidence")

    def __repr__(self) -> str:
        return (
            f"<IncidentEvidence(id='{self.id}', type='{self.evidence_type}', "
            f"incident_id='{self.incident_id}')>"
        )


class IncidentReview(Base):
    """Human review decision for an incident (append-only ledger)."""

    __tablename__ = "incident_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="reviews")

    def __repr__(self) -> str:
        return (
            f"<IncidentReview(id='{self.id}', incident_id='{self.incident_id}', "
            f"label='{self.label}')>"
        )


class AgentEnrichment(Base):
    """Asynchronous Agent/VLM enrichment record for an incident."""

    __tablename__ = "agent_enrichments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="enrichments")

    def __repr__(self) -> str:
        return (
            f"<AgentEnrichment(id='{self.id}', incident_id='{self.incident_id}', "
            f"status='{self.status}')>"
        )


class CameraSource(Base):
    """Video source assigned to a camera: a local webcam index or a video file.

    Kept apart from ``cameras`` so health rows stay credential-free; file sources
    are stored as names inside the server's upload/sample directories, never paths.
    """

    __tablename__ = "camera_sources"

    camera_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # webcam | file
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    room: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    loop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class User(Base):
    """Dashboard operator account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="operator", nullable=False)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    care_setting: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    job_role: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    """Server-side login session; the cookie carries a token whose SHA-256 is stored."""

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="sessions")


class AppSetting(Base):
    """Workspace setting stored as a JSON value under a key."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
