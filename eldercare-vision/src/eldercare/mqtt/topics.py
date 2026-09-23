"""MQTT topic construction for ElderCare Vision (P7-002).

Authoritative topic roots (EVENT_SCHEMA.md §4)::

    eldercare/{site_id}/{camera_id}/events/fall
    eldercare/{site_id}/{camera_id}/health
    eldercare/{site_id}/{camera_id}/agent

Validation is strict: topic segments must never contain MQTT wildcards
(``+``/``#``), path separators, whitespace, or control characters, and the
final topic must fit the MQTT UTF-8 length limit. Overly broad wildcard
*subscriptions* are the caller's responsibility; this module only builds
concrete publish topics and rejects anything wildcard-shaped.
"""

from __future__ import annotations

from typing import Literal

TopicCategory = Literal["events/fall", "health", "agent"]

TOPIC_PREFIX = "eldercare"
SCHEMA_VERSION = "1.0"
_MAX_TOPIC_BYTES = 65535

_CATEGORIES: tuple[str, ...] = ("events/fall", "health", "agent")


def _check_segment(name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > 128:
        raise ValueError(f"{name} must be at most 128 characters")
    for char in value:
        if char in "+#/" or char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F:
            raise ValueError(
                f"{name} must not contain wildcards, slashes, "
                f"whitespace, or control characters: {value!r}"
            )
    return value


def build_topic(site_id: str, camera_id: str, category: TopicCategory) -> str:
    """Build a concrete publish topic for the given site/camera/category."""
    if category not in _CATEGORIES:
        raise ValueError(f"Unknown topic category {category!r}. Allowed: {sorted(_CATEGORIES)}")
    site = _check_segment("site_id", site_id)
    camera = _check_segment("camera_id", camera_id)
    topic = f"{TOPIC_PREFIX}/{site}/{camera}/{category}"
    if len(topic.encode("utf-8")) > _MAX_TOPIC_BYTES:
        raise ValueError("Built topic exceeds the MQTT length limit")
    return topic
