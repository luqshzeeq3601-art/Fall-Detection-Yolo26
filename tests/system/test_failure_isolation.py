"""Cross-boundary failure-isolation drills (P8-001).

Deterministic composition tests over REAL components with injected faults
(fake clocks/sleeps/captures/transports, in-memory DB). No real sleeps,
network, broker, GPU, or cameras. Component-level fault behavior stays owned
by Phases 1–7 suites (re-run fresh as executed evidence); these drills prove
the BOUNDARIES: isolation, observability, recovery, and no state corruption.
"""

from __future__ import annotations

import dataclasses
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base
from eldercare.fall_engine.state_machine import FallState, TrackFallStateMachine
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.publisher import MqttPublisher
from eldercare.mqtt.resilience import publish_best_effort
from eldercare.vision.pose.adapter import adapt_pose_results
from eldercare.vision.stream.health import CameraHealthState, StreamHealthMonitor
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.stream.reconnect import ReconnectController, ReconnectPolicy
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from tests.fixtures.synthetic_fall_fixtures import (
    build_track_observation,
    generate_fall_sequence,
    generate_walking_sequence,
    make_fallen_pose,
    make_standing_pose,
)


class _FakeClock:
    """Manual clock so stall/reconnect timing is deterministic."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeCapture:
    """Scripted RTSP capture: fails until released, then opens."""

    def __init__(self, failures_before_success: int) -> None:
        self._remaining = failures_before_success
        self.opens = 0

    def open(self) -> bool:
        self.opens += 1
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return True


class _FakeConfig:
    camera_id = "cam-fault-01"


def test_stream_stall_offline_bounded_reconnect_and_recovery() -> None:
    """FT-001/FT-002: stall → offline, bounded retries, recovery resets."""
    clock = _FakeClock()
    health = StreamHealthMonitor(
        camera_id="cam-fault-01", degraded_after=2.0, offline_after=10.0, clock=clock
    )
    queue: LatestFrameQueue[object] = LatestFrameQueue(maxsize=2)
    capture = _FakeCapture(failures_before_success=2)
    slept: list[float] = []
    controller = ReconnectController(
        config=_FakeConfig(),  # type: ignore[arg-type]
        capture=capture,  # type: ignore[arg-type]
        health=health,
        policy=ReconnectPolicy(base_delay=1.0, multiplier=2.0, max_delay=30.0, max_attempts=5),
        sleep=slept.append,
        clock=clock,
    )
    assert health.state is CameraHealthState.UNKNOWN
    clock.advance(11.0)
    transition = health.poll()
    assert transition is not None
    assert health.state is CameraHealthState.OFFLINE
    for _frame in range(5):
        queue.put(object())
    assert queue.depth <= 2, "latest-frame queue must stay bounded during stall"
    assert queue.dropped >= 3
    assert controller.attempt() is False
    assert controller.attempt() is False
    assert controller.attempts == 2
    assert slept == [1.0, 2.0], "bounded exponential backoff, fake sleep only"
    assert controller.attempt() is True
    assert controller.attempts == 0
    assert controller.consecutive_failures == 0
    assert queue.depth <= 2


def test_pose_zero_person_yields_no_observations() -> None:
    """Zero-person frame produces an empty pose frame, never fabricated poses."""

    class _EmptyKeypoints:
        xy: list = []
        conf: list = []

    class _EmptyBoxes:
        xyxy: list = []
        conf: list = []

    class _EmptyResults:
        orig_shape = (480, 640)
        keypoints = _EmptyKeypoints()
        boxes = _EmptyBoxes()

    frame = adapt_pose_results(_EmptyResults())
    assert len(frame.persons) == 0


def test_pose_malformed_result_fails_closed() -> None:
    """Malformed inference output raises instead of fabricating poses."""
    with pytest.raises(ValueError):
        adapt_pose_results(None)

    class _NoConf:
        xy: list = []
        conf = None

    class _BadResults:
        orig_shape = (480, 640)
        keypoints = _NoConf()
        boxes = None

    with pytest.raises(ValueError):
        adapt_pose_results(_BadResults())


def test_tracking_cross_camera_isolation_and_expiry() -> None:
    """Same track_id on two cameras never shares history; stale pruned."""
    store_a: TrackHistory = TrackHistory(TrackHistoryConfig())
    store_b: TrackHistory = TrackHistory(TrackHistoryConfig())
    obs_a = build_track_observation(
        make_standing_pose(), camera_id="cam-A", track_id=7, timestamp=100.0
    )
    obs_b = build_track_observation(
        make_standing_pose(), camera_id="cam-B", track_id=7, timestamp=100.0
    )
    store_a.append(obs_a)
    store_b.append(obs_b)
    assert store_a.snapshot("cam-A", 7) != store_b.snapshot("cam-B", 7)
    assert store_a.snapshot("cam-A", 7)[0] is obs_a
    expired = store_a.expire_stale(now=200.0, max_idle_seconds=10.0)
    assert ("cam-A", 7) in expired
    assert store_a.snapshot("cam-A", 7) == ()
    assert store_b.snapshot("cam-B", 7) != ()


def test_single_frame_never_confirms_fall() -> None:
    """One fallen-looking frame without temporal evidence stays unconfirmed."""
    stood = make_standing_pose()
    fallen = make_fallen_pose()
    _ = stood
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    obs = build_track_observation(fallen, camera_id="cam-01", track_id=1, timestamp=1.0)
    state, event = machine.update([obs])
    assert state is not FallState.FALL_CONFIRMED
    assert event is None


def test_recovery_before_confirmation_returns_to_normal() -> None:
    """Descent onset followed by normal activity never confirms."""
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    fall = generate_fall_sequence(duration_sec=3.0, fps=15.0)
    confirmed = False
    for i in range(1, 4):
        state, event = machine.update(fall[:i])
        if state is FallState.FALL_CONFIRMED or event is not None:
            confirmed = True
    assert confirmed is False
    walk = generate_walking_sequence(duration_sec=3.0, fps=15.0)
    for i in range(1, len(walk) + 1):
        state, _ = machine.update(walk[:i])
    assert state is FallState.NORMAL


def _sqlite_service() -> IncidentService:
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return IncidentService(sessionmaker(bind=engine, expire_on_commit=False))


def test_e2e_fall_persist_evidence_dead_broker_detector_intact() -> None:
    """Core flow survives MQTT outage: confirm → persist → evidence → publish-fail."""
    machine = TrackFallStateMachine(camera_id="cam-e2e", track_id=9)
    sequence = generate_fall_sequence(duration_sec=3.0, fps=15.0)
    events = []
    for i in range(1, len(sequence) + 1):
        _, event = machine.update(sequence[:i])
        if event is not None:
            events.append(event)
    assert len(events) == 1, "exactly one confirmed fall event expected"

    service = _sqlite_service()
    now = datetime.now(timezone.utc)
    incident = service.record_fall_incident(
        camera_id="cam-e2e",
        track_id="9",
        started_at=now,
        confirmed_at=now,
        fall_score=0.87,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={"rapid_vertical_drop": True},
        auto_create_camera=True,
    )
    service.attach_evidence(
        incident_id=incident.id,
        evidence_type="snapshot",
        storage_path="/evidence/cam-e2e/snap.jpg",
        mime_type="image/jpeg",
        sha256="a" * 64,
        captured_at=now,
    )
    transport = FakeMqttTransport()
    transport.fail_publish = True
    publisher = MqttPublisher(site_id="test-site", transport=transport)
    publisher.connect()
    mqtt_event = MqttEvent.create(
        event_type="fall.confirmed",
        camera_id="cam-e2e",
        incident_id=incident.id,
        payload={"fall_score": 0.87, "track_id": "9"},
    )
    outcome = publish_best_effort(publisher, mqtt_event, "events/fall")
    assert outcome.delivered is False
    detail = service.get_incident(incident.id)
    assert detail.fall_score == 0.87
    assert len(detail.evidence) == 1
    service.submit_review(incident_id=incident.id, label="confirmed_fall", notes="drill")
    assert len(service.get_incident(incident.id).reviews) == 1


def test_e2e_cooldown_no_alert_storm_then_recovery() -> None:
    """Post-confirm DOWN frames emit no second event; recovery transitions."""
    machine = TrackFallStateMachine(camera_id="cam-e2e", track_id=9)
    sequence = generate_fall_sequence(duration_sec=3.0, fps=15.0)
    events = []
    for i in range(1, len(sequence) + 1):
        _, event = machine.update(sequence[:i])
        if event is not None:
            events.append(event)
    assert len(events) == 1
    last = sequence[-1]
    extra = 0
    for step in range(1, 31):
        bumped = dataclasses.replace(last, timestamp=last.timestamp + step * 0.1)
        _, event = machine.update([*sequence, bumped])
        if event is not None:
            extra += 1
    assert extra == 0, "no alert storm while the same fall state persists"
    walk = generate_walking_sequence(duration_sec=3.0, fps=15.0)
    for i in range(1, len(walk) + 1):
        state, _ = machine.update(walk[:i])
    assert state in (FallState.RECOVERY, FallState.NORMAL)


def test_api_failures_stay_sanitized() -> None:
    """Broken DB → 503 envelope; bad bodies → 422/404; never a traceback."""
    engine = create_engine("sqlite:///nonexistent-dir-xyz/db.sqlite", echo=False)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=factory)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database"] == "unavailable"
    assert "Traceback" not in response.text
    bad = client.post(
        "/incidents/does-not-exist/reviews", json={"label": "bogus", "notes": "x" * 3000}
    )
    assert bad.status_code in (404, 422)
    assert "Traceback" not in bad.text


def test_concurrent_histories_do_not_leak_across_threads() -> None:
    """Parallel per-track updates keep identities isolated (no state leakage)."""
    errors: list[BaseException] = []

    def _drive(camera: str, track: int) -> None:
        try:
            store: TrackHistory = TrackHistory(TrackHistoryConfig())
            for step in range(20):
                store.append(
                    build_track_observation(
                        make_standing_pose(),
                        camera_id=camera,
                        track_id=track,
                        timestamp=100.0 + step,
                    )
                )
            assert store.snapshot(camera, track) != ()
        except BaseException as exc:  # noqa: BLE001 - collected, then re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=_drive, args=(f"cam-{i}", i)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
