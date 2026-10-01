"""Broker configuration validation for the Mosquitto service (P7-001).

Validates ``deployment/mosquitto/mosquitto.conf`` directive-by-directive
against ARCHITECTURE.md §3/§8, EVENT_SCHEMA.md §4 and CONSTRAINTS.md, plus
the compose wiring (read-only conf mount, daemon healthcheck, no hard broker
dependency for core services). No live broker, network, or daemon required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF_PATH = REPO_ROOT / "deployment" / "mosquitto" / "mosquitto.conf"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _directives() -> dict[str, list[str]]:
    """Parse mosquitto.conf into ``{directive: [values...]}``.

    Strips comments/blank lines; splits each line into a directive plus its
    remainder (values may contain spaces, e.g. healthcheck topics).
    """
    parsed: dict[str, list[str]] = {}
    for raw_line in CONF_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        key = parts[0].strip().lower()
        value = parts[1].strip() if len(parts) > 1 else ""
        parsed.setdefault(key, []).append(value)
    return parsed


@pytest.fixture(scope="module")
def conf() -> dict[str, list[str]]:
    assert CONF_PATH.is_file(), "deployment/mosquitto/mosquitto.conf is missing"
    return _directives()


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_explicit_mqtt_listener(conf: dict[str, list[str]]) -> None:
    assert conf.get("listener") == ["1883"]
    assert conf.get("protocol") == ["mqtt"]


def test_no_extra_listeners(conf: dict[str, list[str]]) -> None:
    assert len(conf.get("listener", [])) == 1, "exactly one listener expected"
    assert not any(key.startswith("websocket") for key in conf), "no websocket listener allowed"
    assert conf.get("port", []) == [], "no default-port listener expected"


def test_anonymous_policy_is_explicit_and_documented(
    conf: dict[str, list[str]],
) -> None:
    assert conf.get("allow_anonymous") == ["true"]
    text = CONF_PATH.read_text(encoding="utf-8")
    assert "DEVELOPMENT-ONLY" in text, "anonymous deviation must be documented"
    assert "password_file" in text, "production auth path must be documented"
    assert "per_listener_settings" in conf


def test_persistence_targets_compose_volume(conf: dict[str, list[str]]) -> None:
    assert conf.get("persistence") == ["true"]
    assert conf.get("persistence_location") == ["/mosquitto/data/"]
    assert conf.get("autosave_interval") == ["1800"]


def test_bounds_are_explicit(conf: dict[str, list[str]]) -> None:
    assert conf.get("max_connections") == ["50"]
    assert conf.get("max_queued_messages") == ["1000"]


def test_logging_to_stdout_without_debug(conf: dict[str, list[str]]) -> None:
    assert conf.get("log_dest") == ["stdout"]
    assert "debug" not in [value.lower() for value in conf.get("log_type", [])]
    assert conf.get("connection_messages") == ["true"]


def test_no_secrets_or_tls_half_config(conf: dict[str, list[str]]) -> None:
    # Directive-level (comments stripped): documentation prose may name these,
    # but none may be configured.
    for directive in ("password_file", "psk_file", "acl_file"):
        assert directive not in conf, f"{directive} must not be configured"
    for token in ("cafile", "certfile", "keyfile", "require_certificate"):
        assert token not in conf, f"no TLS half-configuration: {token}"
    blob = CONF_PATH.read_text(encoding="utf-8")
    assert "CHANGEME" not in blob


def test_compose_mounts_conf_read_only(compose: dict) -> None:
    mosquitto = compose["services"]["mosquitto"]
    assert mosquitto["image"] == "eclipse-mosquitto:2"
    volumes = mosquitto["volumes"]
    assert any(
        "deployment/mosquitto/mosquitto.conf" in str(entry) and str(entry).endswith(":ro")
        for entry in volumes
    ), f"conf must be mounted read-only, got: {volumes}"
    assert any("mosquitto-data" in str(entry) for entry in volumes)


def test_compose_broker_healthcheck(compose: dict) -> None:
    healthcheck = compose["services"]["mosquitto"].get("healthcheck", {})
    test_cmd = " ".join(str(part) for part in healthcheck.get("test", []))
    assert "mosquitto_sub" in test_cmd
    assert "$SYS" in test_cmd or "$$SYS" in test_cmd


def test_core_services_have_no_hard_broker_dependency(compose: dict) -> None:
    """Vision/API/agent must not require a healthy broker (failure isolation)."""
    services = compose["services"]
    for name in ("vision", "api", "agent-worker"):
        depends = services[name].get("depends_on", {})
        broker_dep = depends.get("mosquitto", {}) if isinstance(depends, dict) else {}
        condition = broker_dep.get("condition", "") if isinstance(broker_dep, dict) else ""
        assert condition != "service_healthy", f"{name} must not hard-depend on mosquitto"
        assert condition != "service_completed_successfully"
