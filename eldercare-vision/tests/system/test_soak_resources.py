"""Extended-run soak test with resource trending (P8-004).

Specified workload: 2,000 synthetic frames through observation → bounded
history → fall engine → snapshot → periodic sqlite persist → best-effort MQTT
publish (live broker first half, dead second half). No real sleeps, network,
broker, GPU, or cameras. Measurements observed, never estimated; no invented
targets — bounds below are structural (configured capacities) or generous
tripwires documented as such.
"""

from __future__ import annotations

import dataclasses
import gc
import time
import tracemalloc
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.db.base import Base
from eldercare.fall_engine.state_machine import FallStateMachineManager
from eldercare.incidents.schemas import IncidentFilter
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.pipeline_metrics import collect_pipeline_metrics
from eldercare.mqtt.publisher import MqttPublisher
from eldercare.mqtt.resilience import publish_best_effort
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from tests.fixtures.synthetic_fall_fixtures import (
    generate_fall_sequence,
    generate_walking_sequence,
)

ITERATIONS = 2000
PERSIST_EVERY = 50
WALL_BUDGET_S = 300.0
EXPECTED_PERSISTS = ITERATIONS // PERSIST_EVERY


def test_soak_bounded_resources_and_zero_unhandled() -> None:
    """Run the specified workload; assert boundedness, integrity, and trends."""
    walk = generate_walking_sequence(duration_sec=2.0, fps=15.0, camera_id="cam-soak", track_id=1)
    fall = generate_fall_sequence(duration_sec=2.0, fps=15.0, camera_id="cam-soak", track_id=1)
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = IncidentService(sessionmaker(bind=engine, expire_on_commit=False))
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="soak", transport=transport)
    publisher.connect()
    manager = FallStateMachineManager()
    store: TrackHistory = TrackHistory(TrackHistoryConfig())
    queue: LatestFrameQueue[object] = LatestFrameQueue(maxsize=2)
    now = datetime.now(timezone.utc)

    gc.collect()
    tracemalloc.start()
    start_current, _ = tracemalloc.get_traced_memory()
    max_history = 0
    max_depth = 0
    confirms = 0
    started = time.monotonic()
    for cycle in range(ITERATIONS):
        episode = fall if (cycle // 500) % 2 == 1 else walk
        frame = episode[cycle % len(episode)]
        bumped = dataclasses.replace(frame, timestamp=1000.0 + cycle * 0.05)
        try:
            store.append(bumped)
            snapshot = store.snapshot("cam-soak", 1)
            manager.update_track("cam-soak", 1, snapshot)
            queue.put(object())
            metrics = collect_pipeline_metrics("cam-soak")
            assert metrics.schema_version == "1.0"
            transport.fail_publish = cycle >= ITERATIONS // 2
            event = MqttEvent.create(
                event_type="fall.confirmed" if (cycle // 500) % 2 == 1 else "camera.online",
                camera_id="cam-soak",
            )
            outcome = publish_best_effort(publisher, event, "events/fall")
            if outcome.delivered:
                confirms += 1
            if cycle % PERSIST_EVERY == 0:
                service.record_fall_incident(
                    camera_id="cam-soak",
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
        except Exception:
            tracemalloc.stop()
            raise
        max_history = max(max_history, len(store.snapshot("cam-soak", 1)))
        max_depth = max(max_depth, queue.depth)
    elapsed = time.monotonic() - started
    end_current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert elapsed < WALL_BUDGET_S
    assert max_history <= 60, "per-track history must respect the configured bound"
    assert max_depth <= 2, "queue must respect capacity"
    assert end_current <= max(start_current * 3, start_current + 5_000_000)
    items, total = service.list_incidents(IncidentFilter(camera_id="cam-soak"))
    assert total == EXPECTED_PERSISTS
    assert len(items) == EXPECTED_PERSISTS
    assert publisher.published_count + publisher.failed_count == ITERATIONS
    assert publisher.failed_count == ITERATIONS // 2
    assert confirms == ITERATIONS // 2
