"""Implicit protection rules for memories that should stay reachable."""

from __future__ import annotations

from datetime import datetime

from ego_mcp import timezone_utils
from ego_mcp.types import Memory

PRECIOUS_INTENSITY_MIN = 0.6
PRECIOUS_ACCESS_MIN = 3
PRECIOUS_IMPORTANCE_MAX = 2
PRECIOUS_DECAY_FLOOR = 0.25


def is_precious(memory: Memory) -> bool:
    a = (
        bool(memory.involved_person_ids)
        and memory.emotional_trace.intensity >= PRECIOUS_INTENSITY_MIN
    )
    b = (
        memory.access_count >= PRECIOUS_ACCESS_MIN
        and memory.importance <= PRECIOUS_IMPORTANCE_MAX
    )
    return a or b


def is_unarrived_anticipation(memory: Memory, now: datetime) -> bool:
    value = getattr(memory, "anticipated_at", "")
    if not isinstance(value, str) or not value:
        return False
    try:
        target = datetime.fromisoformat(value)
    except ValueError:
        return False
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone_utils.app_timezone())
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone_utils.app_timezone())
    return target > now


def is_protected(memory: Memory, now: datetime) -> bool:
    return is_precious(memory) or is_unarrived_anticipation(memory, now)
