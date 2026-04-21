"""Interoception helpers for time phase."""

from __future__ import annotations

from datetime import datetime

from ego_mcp import timezone_utils


def time_phase(now: datetime | None = None) -> str:
    """Classify current time into coarse cognitive phases."""
    if now is None:
        now = timezone_utils.now()
    hour = now.hour
    if 0 <= hour <= 4:
        return "late_night"
    if 5 <= hour <= 6:
        return "early_morning"
    if 7 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 20:
        return "evening"
    return "night"


def get_body_state() -> dict[str, str]:
    """Get compact body state snapshot."""
    return {"time_phase": time_phase()}
