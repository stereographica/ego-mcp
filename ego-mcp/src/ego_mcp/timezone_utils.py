"""Timezone helpers driven by environment configuration."""

from __future__ import annotations

import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TIMEZONE_ENV = "EGO_MCP_TIMEZONE"
_DEFAULT_TIMEZONE = "UTC"


def timezone_name() -> str:
    """Return configured timezone ID."""
    return os.environ.get(_TIMEZONE_ENV, _DEFAULT_TIMEZONE)


def app_timezone() -> tzinfo:
    """Return configured IANA timezone.

    Raises:
        ValueError: if the configured timezone ID is invalid.
    """
    name = timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Invalid timezone '{name}' in {_TIMEZONE_ENV}. Use an IANA timezone ID (e.g. 'UTC', 'Asia/Tokyo')."
        ) from exc


def now() -> datetime:
    """Return current time in configured timezone."""
    return datetime.now(tz=app_timezone())


def localize(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in configured timezone."""
    tz = app_timezone()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)
