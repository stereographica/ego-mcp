"""Absence and reunion helpers for relationship surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ego_mcp import timezone_utils

ABSENCE_EMA_ALPHA = 0.3
ABSENCE_MIN_INTERACTIONS = 3
ABSENCE_FALLBACK_DAYS = 7.0
ABSENCE_QUIET_MULT = 2.0
ABSENCE_LONG_MULT = 4.0
ABSENCE_SOCIAL_THIRST_BOOST = 0.08


def _parse_absence_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def interaction_interval_ema(interaction_log: Any) -> float | None:
    if not isinstance(interaction_log, list) or len(interaction_log) < ABSENCE_MIN_INTERACTIONS:
        return None

    timestamps: list[datetime] = []
    for item in interaction_log:
        if not isinstance(item, dict):
            continue
        parsed = _parse_absence_timestamp(item.get("timestamp"))
        if parsed is not None:
            timestamps.append(parsed)

    timestamps.sort()
    if len(timestamps) < ABSENCE_MIN_INTERACTIONS:
        return None

    intervals: list[float] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        interval_days = (current - previous).total_seconds() / 86400.0
        if interval_days >= 0:
            intervals.append(interval_days)

    if len(intervals) < ABSENCE_MIN_INTERACTIONS - 1:
        return None

    ema = intervals[0]
    for interval in intervals[1:]:
        ema = ABSENCE_EMA_ALPHA * interval + (1.0 - ABSENCE_EMA_ALPHA) * ema
    return ema


def absence_band(rel_raw: dict[str, Any], now: datetime) -> tuple[str, float]:
    parsed_last = _parse_absence_timestamp(rel_raw.get("last_interaction"))
    if parsed_last is None:
        return "unknown", 0.0

    localized_now = timezone_utils.localize(now)
    elapsed_days = max(0.0, (localized_now - parsed_last).total_seconds() / 86400.0)
    ema = interaction_interval_ema(rel_raw.get("interaction_log")) or ABSENCE_FALLBACK_DAYS
    if elapsed_days < ABSENCE_QUIET_MULT * ema:
        return "usual", elapsed_days
    if elapsed_days < ABSENCE_LONG_MULT * ema:
        return "quiet", elapsed_days
    return "long", elapsed_days


def approx_duration_words(days: float) -> str:
    if days < 1:
        return "earlier today"
    if days < 2:
        return "about a day"
    if days < 3:
        return "a couple of days"
    if days < 5:
        return "a few days"
    if days < 8:
        return "about a week"
    if days < 12:
        return "over a week"
    if days < 18:
        return "about two weeks"
    if days < 25:
        return "about three weeks"
    if days < 45:
        return "about a month"
    if days < 75:
        return "about two months"
    if days < 135:
        return "a few months"
    if days < 240:
        return "several months"
    if days < 550:
        return "about a year"
    return "well over a year"
