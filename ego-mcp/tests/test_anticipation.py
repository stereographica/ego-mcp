"""Tests for future anticipation salience and selection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ego_mcp.anticipation import (
    ANTICIPATION_PRESENT_PROBABILITY,
    anticipation_band,
    anticipation_salience,
    pick_anticipation,
)
from ego_mcp.types import Memory


class FixedRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


def test_anticipation_salience_clamps_importance_and_days() -> None:
    assert anticipation_salience(99, 0.0) == pytest.approx(1.0)
    assert anticipation_salience(-10, -2.0) == pytest.approx(0.2)
    assert anticipation_salience(5, 60.0) < 0.3


def test_anticipation_band_boundaries() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)

    assert anticipation_band((now - timedelta(seconds=1)).isoformat(), 5, now) == "arrived"
    assert anticipation_band((now + timedelta(hours=48)).isoformat(), 1, now) == "imminent"
    assert anticipation_band((now + timedelta(days=10)).isoformat(), 5, now) == "approaching"
    assert anticipation_band((now + timedelta(days=60)).isoformat(), 5, now) == "distant"


def test_pick_anticipation_prioritizes_imminent_without_thinning() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    approaching = Memory(
        id="approaching",
        content="later",
        anticipated_at=(now + timedelta(days=10)).isoformat(),
        importance=5,
    )
    imminent = Memory(
        id="imminent",
        content="soon",
        anticipated_at=(now + timedelta(hours=36)).isoformat(),
        importance=1,
    )

    assert pick_anticipation([approaching, imminent], now, FixedRng(0.99)) == imminent


def test_pick_anticipation_thins_approaching_band() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    approaching = Memory(
        id="approaching",
        content="later",
        anticipated_at=(now + timedelta(days=10)).isoformat(),
        importance=5,
    )

    assert pick_anticipation([approaching], now, FixedRng(0.49)) == approaching
    assert pick_anticipation(
        [approaching],
        now,
        FixedRng(ANTICIPATION_PRESENT_PROBABILITY),
    ) is None
