"""Interoception helpers for time phase and system load."""

from __future__ import annotations

import os
from datetime import datetime

try:
    import psutil  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    psutil = None


def time_phase(now: datetime | None = None) -> str:
    """Classify current time into coarse cognitive phases."""
    if now is None:
        now = datetime.now()
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


def _load_ratio() -> float:
    """Return normalized 1-minute load average ratio."""
    cpu_count = max(1, os.cpu_count() or 1)

    if psutil is not None:
        try:
            load1 = psutil.getloadavg()[0]
            return float(load1) / cpu_count
        except Exception:
            pass

    try:
        load1 = os.getloadavg()[0]
        return float(load1) / cpu_count
    except (AttributeError, OSError):
        return 0.0


def system_load() -> str:
    """Discretize normalized system load."""
    ratio = _load_ratio()
    if ratio < 0.7:
        return "low"
    if ratio < 1.2:
        return "medium"
    return "high"


def get_body_state() -> dict[str, str]:
    """Get compact body state snapshot."""
    uptime_hours = "0.0"
    if psutil is not None:
        try:
            uptime_seconds = datetime.now().timestamp() - float(psutil.boot_time())
            uptime_hours = f"{max(0.0, uptime_seconds / 3600):.1f}"
        except Exception:
            uptime_hours = "0.0"

    return {
        "time_phase": time_phase(),
        "system_load": system_load(),
        "uptime_hours": uptime_hours,
    }
