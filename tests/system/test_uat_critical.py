"""Executable critical UAT cases UAT-01…UAT-20 (P8-002).

Every case maps 1:1 to `uat/cases/UAT-CASES.md` (frozen from UAT_PLAN.md).
Deterministic synthetic harnesses over real components: no cameras, GPU,
network, broker, sleeps, or provider calls. Lab results are NOT clinical or
real-world validation.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base
from eldercare.fall_engine.state_machine import (
    FallState,
    FallStateMachineManager,
    TrackFallStateMachine,
)
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.publisher import MqttPublisher
from eldercare.mqtt.resilience import publish_best_effort
from eldercare.vision.stream.health import CameraHealthState, StreamHealthMonitor
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.stream.reconnect import ReconnectController, ReconnectPolicy
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from tests.fixtures.synthetic_fall_fixtures import (
    build_track_observation,
    generate_bending_sequence,
    generate_fall_sequence,
    generate_fall_with_recovery_sequence,
    generate_sitting_sequence,
    generate_slow_liedown_sequence,
    generate_walking_sequence,
    interpolate_poses,
    make_bending_pose,
    make_sitting_pose,
    make_standing_pose,
)


def _run(machine: TrackFallStateMachine, history) -> tuple[FallState, list]:
    events = []
    state = FallState.NORMAL
    for i in range(1, len(history) + 1):
        state, event = machine.update(history[:i])
        if event is not None:
            events.append(event)
    return state, events


def test_uat_01_normal_walking() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, generate_walking_sequence(duration_sec=3.0, fps=15.0))
    assert events == []
    assert state is FallState.NORMAL


def test_uat_02_sitting_normally() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(
        machine, generate_sitting_sequence(duration_sec=3.0, fps=15.0, sit_start_sec=1.0)
    )
    assert events == []
    assert state is FallState.NORMAL


def test_uat_03_standing_up() -> None:
    standing = make_standing_pose()
    seated = make_sitting_pose()
    observations = []
    frames = 18
    for i in range(frames):
        alpha = i / (frames - 1)
        pose = interpolate_poses(seated, standing, alpha)
        observations.append(
            build_track_observation(pose, camera_id="cam-01", track_id=1, timestamp=i / 15.0)
        )
    for i in range(15):
        observations.append(
            build_track_observation(
                standing, camera_id="cam-01", track_id=1, timestamp=(frames + i) / 15.0
            )
        )
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, observations)
    assert events == []
    assert state is FallState.NORMAL


def test_uat_04_bending_picking_object() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(
        machine, generate_bending_sequence(duration_sec=3.0, fps=15.0, bend_start_sec=1.0)
    )
    assert events == []
    assert state is not FallState.FALL_CONFIRMED


def test_uat_05_kneeling() -> None:
    standing = make_standing_pose()
    apex = interpolate_poses(standing, make_bending_pose(), 0.7)
    observations = []
    for i in range(15):
        alpha = i / 14
        pose = interpolate_poses(standing, apex, alpha)
        observations.append(
            build_track_observation(pose, camera_id="cam-01", track_id=1, timestamp=i / 15.0)
        )
    for i in range(15, 45):
        observations.append(
            build_track_observation(apex, camera_id="cam-01", track_id=1, timestamp=i / 15.0)
        )
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, observations)
    assert events == []
    assert state is not FallState.FALL_CONFIRMED


def test_uat_06_intentional_slow_lying_down() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, generate_slow_liedown_sequence(duration_sec=4.0, fps=15.0))
    assert state is not FallState.FALL_CONFIRMED, f"slow liedown ended in {state}"
    assert events == []


def test_uat_07_controlled_fall_candidate_then_confirmed() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, generate_fall_sequence(duration_sec=3.0, fps=15.0))
    assert state is FallState.FALL_CONFIRMED
    assert len(events) == 1
    states = [t.to_state for t in machine.transitions]
    assert FallState.DESCENT_CANDIDATE in states, "candidate must precede confirmation"
    assert states.index(FallState.DESCENT_CANDIDATE) < states.index(FallState.FALL_CONFIRMED)


def test_uat_08_person_remains_down_single_incident() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    sequence = list(generate_fall_sequence(duration_sec=3.0, fps=15.0))
    state, events = _run(machine, sequence)
    assert len(events) == 1
    last = sequence[-1]
    extra = 0
    for step in range(1, 31):
        bumped = dataclasses.replace(last, timestamp=last.timestamp + step * 0.1)
        _, event = machine.update([*sequence, bumped])
        if event is not None:
            extra += 1
    assert extra == 0


def test_uat_09_person_recovers() -> None:
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, _ = _run(machine, generate_fall_with_recovery_sequence(duration_sec=5.0, fps=15.0))
    assert state in (FallState.RECOVERY, FallState.NORMAL)


def test_uat_10_partial_occlusion() -> None:
    full = generate_walking_sequence(duration_sec=3.0, fps=15.0)
    gapped = [obs for i, obs in enumerate(full) if i % 3 != 2]
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, gapped)
    assert events == []
    assert state is not FallState.FALL_CONFIRMED
    low_conf = [dataclasses.replace(obs, detection_confidence=0.3) for obs in full]
    machine2 = TrackFallStateMachine(camera_id="cam-01", track_id=2)
    state2, events2 = _run(machine2, low_conf)
    assert events2 == []
    assert state2 is not FallState.FALL_CONFIRMED


def test_uat_11_two_people() -> None:
    manager = FallStateMachineManager()
    walk = generate_walking_sequence(duration_sec=3.0, fps=15.0, track_id=1)
    fall = generate_fall_sequence(duration_sec=3.0, fps=15.0, track_id=2)
    for i in range(1, len(walk) + 1):
        manager.update_track("cam-01", 1, walk[:i])
    for i in range(1, len(fall) + 1):
        manager.update_track("cam-01", 2, fall[:i])
    assert manager.get_state("cam-01", 1) is not FallState.FALL_CONFIRMED
    assert manager.get_state("cam-01", 2) is FallState.FALL_CONFIRMED


def test_uat_12_low_light_proxy() -> None:
    full = generate_walking_sequence(duration_sec=3.0, fps=15.0)
    dimmed = [dataclasses.replace(obs, detection_confidence=0.25) for obs in full]
    machine = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    state, events = _run(machine, dimmed)
    assert events == []
    assert state is not FallState.FALL_CONFIRMED


class _ManualClock:
    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


class _ScriptedCapture:
    def __init__(self, succeed: bool) -> None:
        self._succeed = succeed

    def open(self) -> bool:
        return self._succeed


class _Config:
    camera_id = "cam-uat-13"


def test_uat_13_camera_disconnected() -> None:
    clock = _ManualClock()
    health = StreamHealthMonitor(
        camera_id="cam-uat-13", degraded_after=2.0, offline_after=10.0, clock=clock
    )
    controller = ReconnectController(
        config=_Config(),  # type: ignore[arg-type]
        capture=_ScriptedCapture(succeed=False),  # type: ignore[arg-type]
        health=health,
        policy=ReconnectPolicy(base_delay=1.0, max_attempts=3),
        sleep=lambda _: None,
        clock=clock,
    )
    clock.now += 11.0
    transition = health.poll()
    assert transition is not None
    assert health.state is CameraHealthState.OFFLINE
    assert controller.attempt() is False
    assert controller.attempts == 1


def test_uat_14_camera_restored() -> None:
    clock = _ManualClock()
    health = StreamHealthMonitor(
        camera_id="cam-uat-13", degraded_after=2.0, offline_after=10.0, clock=clock
    )
    controller = ReconnectController(
        config=_Config(),  # type: ignore[arg-type]
        capture=_ScriptedCapture(succeed=True),  # type: ignore[arg-type]
        health=health,
        policy=ReconnectPolicy(base_delay=1.0, max_attempts=3),
        sleep=lambda _: None,
        clock=clock,
    )
    assert controller.attempt() is True
    assert controller.attempts == 0
    health.notify_frame(clock())
    assert health.state is CameraHealthState.ONLINE


def _memory_service() -> IncidentService:
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return IncidentService(sessionmaker(bind=engine, expire_on_commit=False))


def test_uat_15_mqtt_unavailable_core_continues() -> None:
    service = _memory_service()
    now = datetime.now(timezone.utc)
    incident = service.record_fall_incident(
        camera_id="cam-uat-15",
        track_id="5",
        started_at=now,
        confirmed_at=now,
        fall_score=0.81,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={},
        auto_create_camera=True,
    )
    transport = FakeMqttTransport()
    transport.fail_publish = True
    publisher = MqttPublisher(site_id="uat", transport=transport)
    publisher.connect()
    event = MqttEvent.create(
        event_type="fall.confirmed", camera_id="cam-uat-15", incident_id=incident.id
    )
    outcome = publish_best_effort(publisher, event, "events/fall")
    assert outcome.delivered is False
    assert service.get_incident(incident.id).fall_score == 0.81


def test_uat_16_vlm_unavailable_core_continues() -> None:
    service = _memory_service()
    now = datetime.now(timezone.utc)
    incident = service.record_fall_incident(
        camera_id="cam-uat-16",
        track_id="6",
        started_at=now,
        confirmed_at=now,
        fall_score=0.83,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={},
        auto_create_camera=True,
    )
    detail = service.get_incident(incident.id)
    assert detail.enrichments == []
    assert detail.detector_state
    assert detail.fall_score == 0.83


def test_uat_17_dashboard_closed_backend_continues() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = IncidentService(factory)
    now = datetime.now(timezone.utc)
    service.record_fall_incident(
        camera_id="cam-uat-17",
        track_id="7",
        started_at=now,
        confirmed_at=now,
        fall_score=0.79,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={},
        auto_create_camera=True,
    )
    app = create_app(session_factory=factory)
    assert app.state.connection_manager.active_count == 0
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/incidents", params={"camera_id": "cam-uat-17"})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_uat_18_backend_restart_preserves_incidents(tmp_path) -> None:
    db_file = tmp_path / "uat18.sqlite"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = IncidentService(factory)
    now = datetime.now(timezone.utc)
    incident_id = service.record_fall_incident(
        camera_id="cam-uat-18",
        track_id="8",
        started_at=now,
        confirmed_at=now,
        fall_score=0.88,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={},
        auto_create_camera=True,
    ).id
    engine.dispose()
    engine2 = create_engine(f"sqlite:///{db_file}", echo=False)
    factory2 = sessionmaker(bind=engine2, expire_on_commit=False)
    assert IncidentService(factory2).get_incident(incident_id).fall_score == 0.88
    app = create_app(session_factory=factory2)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health").json() == {"status": "ok"}
    engine2.dispose()


def test_uat_19_human_review_preserves_detector_record() -> None:
    service = _memory_service()
    now = datetime.now(timezone.utc)
    incident = service.record_fall_incident(
        camera_id="cam-uat-19",
        track_id="9",
        started_at=now,
        confirmed_at=now,
        fall_score=0.9,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={"rapid_vertical_drop": True},
        auto_create_camera=True,
    )
    before = service.get_incident(incident.id)
    snapshot = (
        before.fall_score,
        before.model_name,
        before.model_version,
        before.config_version,
        before.detector_state,
        tuple(sorted(before.evidence_features.items())),
    )
    service.submit_review(incident_id=incident.id, label="non_fall", notes="UAT check")
    after = service.get_incident(incident.id)
    assert (
        after.fall_score,
        after.model_name,
        after.model_version,
        after.config_version,
        after.detector_state,
        tuple(sorted(after.evidence_features.items())),
    ) == snapshot
    assert len(after.reviews) == 1


def test_uat_20_bounded_extended_runtime() -> None:
    store: TrackHistory = TrackHistory(TrackHistoryConfig())
    machine = TrackFallStateMachine(camera_id="cam-uat-20", track_id=1)
    walk = generate_walking_sequence(duration_sec=2.0, fps=15.0)
    queue: LatestFrameQueue[object] = LatestFrameQueue(maxsize=2)
    service = _memory_service()
    now = datetime.now(timezone.utc)
    started = time.monotonic()
    for cycle in range(300):
        frame = walk[cycle % len(walk)]
        bumped = dataclasses.replace(frame, timestamp=1000.0 + cycle * 0.05)
        machine.update([bumped])
        store.append(bumped)
        queue.put(object())
        if cycle % 5 == 0:
            service.record_fall_incident(
                camera_id="cam-uat-20",
                track_id="1",
                started_at=now,
                confirmed_at=now,
                fall_score=0.5,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
                auto_create_camera=True,
            )
    elapsed = time.monotonic() - started
    assert elapsed < 120.0
    assert len(store) <= 300
    assert queue.depth <= 2
    assert machine.state is not FallState.FALL_CONFIRMED
