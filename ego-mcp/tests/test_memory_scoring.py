"""Focused tests for decay scoring extensions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ego_mcp._memory_scoring import calculate_time_decay


def test_high_link_confidence_extends_half_life() -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    baseline = calculate_time_decay(old.isoformat(), now=now, link_confidence_max=0.0)
    reinforced = calculate_time_decay(old.isoformat(), now=now, link_confidence_max=0.9)
    weakly_linked = calculate_time_decay(old.isoformat(), now=now, link_confidence_max=0.1)

    assert reinforced > baseline
    assert weakly_linked > baseline
    assert reinforced > weakly_linked


def test_access_count_extends_half_life_with_cap() -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    cold = calculate_time_decay(old.isoformat(), now=now, access_count=0)
    practiced = calculate_time_decay(old.isoformat(), now=now, access_count=6)
    saturated = calculate_time_decay(old.isoformat(), now=now, access_count=20)

    assert practiced > cold
    assert saturated > practiced
    assert saturated == pytest.approx(
        calculate_time_decay(old.isoformat(), now=now, access_count=100)
    )
