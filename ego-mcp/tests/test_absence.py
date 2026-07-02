"""Tests for absence and reunion helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pytest

from ego_mcp.absence import (
    ABSENCE_FALLBACK_DAYS,
    absence_band,
    approx_duration_words,
    interaction_interval_ema,
)


@pytest.mark.parametrize(
    ("days", "words"),
    [
        (0.5, "earlier today"),
        (1.5, "about a day"),
        (2.5, "a couple of days"),
        (4.5, "a few days"),
        (7.5, "about a week"),
        (11.5, "over a week"),
        (17.5, "about two weeks"),
        (24.5, "about three weeks"),
        (44.5, "about a month"),
        (74.5, "about two months"),
        (134.5, "a few months"),
        (239.5, "several months"),
        (549.5, "about a year"),
        (550.0, "well over a year"),
    ],
)
def test_approx_duration_words_uses_fourteen_numberless_bands(
    days: float,
    words: str,
) -> None:
    result = approx_duration_words(days)

    assert result == words
    assert re.search(r"\d", result) is None


def test_absence_band_unknown_without_last_interaction() -> None:
    assert absence_band({}, datetime(2026, 7, 2, tzinfo=timezone.utc)) == (
        "unknown",
        0.0,
    )


def test_less_than_three_interactions_uses_absolute_fallback() -> None:
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    raw: dict[str, Any] = {
        "last_interaction": "2026-07-01T00:00:00+00:00",
        "interaction_log": [
            {"timestamp": "2026-06-01T00:00:00+00:00", "tone": "calm"},
            {"timestamp": "2026-07-01T00:00:00+00:00", "tone": "happy"},
        ],
    }

    band, elapsed = absence_band(raw, now)

    assert ABSENCE_FALLBACK_DAYS == 7.0
    assert elapsed == pytest.approx(14.0)
    assert band == "quiet"


def test_absence_boundaries_use_upper_band() -> None:
    raw: dict[str, Any] = {
        "last_interaction": "2026-07-03T00:00:00+00:00",
        "interaction_log": [
            {"timestamp": "2026-07-01T00:00:00+00:00", "tone": "calm"},
            {"timestamp": "2026-07-02T00:00:00+00:00", "tone": "calm"},
            {"timestamp": "2026-07-03T00:00:00+00:00", "tone": "calm"},
        ],
    }

    quiet, _ = absence_band(raw, datetime(2026, 7, 5, tzinfo=timezone.utc))
    long, _ = absence_band(raw, datetime(2026, 7, 7, tzinfo=timezone.utc))

    assert interaction_interval_ema(raw["interaction_log"]) == pytest.approx(1.0)
    assert quiet == "quiet"
    assert long == "long"


def test_date_only_last_interaction_is_midnight_app_timezone() -> None:
    raw: dict[str, Any] = {"last_interaction": "2026-07-01"}
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)

    band, elapsed = absence_band(raw, now)

    assert elapsed == pytest.approx(14.0)
    assert band == "quiet"


def test_interval_ema_skips_unreadable_timestamps_and_sorts() -> None:
    log = [
        {"timestamp": "not-a-time", "tone": "calm"},
        {"timestamp": "2026-07-03T00:00:00+00:00", "tone": "calm"},
        {"timestamp": "2026-07-01T00:00:00+00:00", "tone": "calm"},
        {"timestamp": "2026-07-02T00:00:00+00:00", "tone": "calm"},
    ]

    assert interaction_interval_ema(log) == pytest.approx(1.0)
