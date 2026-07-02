"""Tests for implicit preciousness protection rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ego_mcp.preciousness import (
    PRECIOUS_ACCESS_MIN,
    PRECIOUS_IMPORTANCE_MAX,
    PRECIOUS_INTENSITY_MIN,
    is_precious,
    is_protected,
    is_unarrived_anticipation,
)
from ego_mcp.types import EmotionalTrace, Memory


def test_precious_shared_memory_includes_intensity_boundary() -> None:
    boundary = Memory(
        involved_person_ids=["person_a"],
        emotional_trace=EmotionalTrace(intensity=PRECIOUS_INTENSITY_MIN),
        importance=5,
    )
    below_boundary = Memory(
        involved_person_ids=["person_a"],
        emotional_trace=EmotionalTrace(intensity=0.59),
        importance=5,
    )

    assert is_precious(boundary) is True
    assert is_precious(below_boundary) is False


def test_precious_repeated_low_importance_boundaries() -> None:
    boundary = Memory(
        access_count=PRECIOUS_ACCESS_MIN,
        importance=PRECIOUS_IMPORTANCE_MAX,
    )
    importance_too_high = Memory(
        access_count=PRECIOUS_ACCESS_MIN,
        importance=PRECIOUS_IMPORTANCE_MAX + 1,
    )
    access_too_low = Memory(
        access_count=PRECIOUS_ACCESS_MIN - 1,
        importance=PRECIOUS_IMPORTANCE_MAX,
    )

    assert is_precious(boundary) is True
    assert is_precious(importance_too_high) is False
    assert is_precious(access_too_low) is False


def test_unarrived_anticipation_uses_dynamic_attribute() -> None:
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    memory = Memory()
    setattr(memory, "anticipated_at", (now + timedelta(days=1)).isoformat())

    assert is_unarrived_anticipation(memory, now) is True
    assert is_protected(memory, now) is True


def test_unarrived_anticipation_missing_invalid_or_past_is_false() -> None:
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    missing = Memory()
    invalid = Memory()
    past = Memory()
    setattr(invalid, "anticipated_at", "not-a-date")
    setattr(past, "anticipated_at", (now - timedelta(seconds=1)).isoformat())

    assert is_unarrived_anticipation(missing, now) is False
    assert is_unarrived_anticipation(invalid, now) is False
    assert is_unarrived_anticipation(past, now) is False
    assert is_protected(past, now) is False
