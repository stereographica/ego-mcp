"""Future anticipation salience and selection helpers."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.types import Memory

ANTICIPATION_TAU_DAYS_PER_IMPORTANCE = 7.0
ANTICIPATION_APPROACHING_THRESHOLD = 0.3
ANTICIPATION_IMMINENT_HOURS = 48.0
ANTICIPATION_PRESENT_PROBABILITY = 0.5


def _clamp_importance(importance: int) -> int:
    try:
        value = int(importance)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(5, value))


def _parse_target(anticipated_at: str) -> datetime | None:
    try:
        target = datetime.fromisoformat(anticipated_at)
    except (TypeError, ValueError):
        return None
    return timezone_utils.localize(target)


def anticipation_salience(importance: int, days_until: float) -> float:
    clamped = _clamp_importance(importance)
    tau_days = clamped * ANTICIPATION_TAU_DAYS_PER_IMPORTANCE
    salience = (clamped / 5.0) * math.exp(-max(0.0, days_until) / tau_days)
    return max(0.0, min(1.0, salience))


def anticipation_band(anticipated_at: str, importance: int, now: datetime) -> str:
    target = _parse_target(anticipated_at)
    if target is None:
        return "distant"
    now = timezone_utils.localize(now)
    delta = target - now
    if target <= now:
        return "arrived"
    if delta.total_seconds() / 3600 <= ANTICIPATION_IMMINENT_HOURS:
        return "imminent"
    days_until = delta.total_seconds() / 86400
    if anticipation_salience(importance, days_until) >= ANTICIPATION_APPROACHING_THRESHOLD:
        return "approaching"
    return "distant"


def anticipation_target(anticipated_at: str) -> datetime | None:
    return _parse_target(anticipated_at)


def pick_anticipation(memories: list[Memory], now: datetime, rng: Any) -> Memory | None:
    now = timezone_utils.localize(now)
    imminent: list[tuple[float, datetime, Memory]] = []
    approaching: list[tuple[float, datetime, Memory]] = []

    for memory in memories:
        target = _parse_target(memory.anticipated_at)
        if target is None or target <= now:
            continue
        days_until = (target - now).total_seconds() / 86400
        salience = anticipation_salience(memory.importance, days_until)
        band = anticipation_band(memory.anticipated_at, memory.importance, now)
        item = (salience, target, memory)
        if band == "imminent":
            imminent.append(item)
        elif band == "approaching":
            approaching.append(item)

    if imminent:
        return max(imminent, key=lambda item: (item[0], -item[1].timestamp()))[2]
    if approaching:
        chosen = max(approaching, key=lambda item: (item[0], -item[1].timestamp()))[2]
        if rng.random() < ANTICIPATION_PRESENT_PROBABILITY:
            return chosen
    return None


def pick_arrived_anticipation(memories: list[Memory], now: datetime) -> Memory | None:
    now = timezone_utils.localize(now)
    arrived: list[tuple[datetime, Memory]] = []
    for memory in memories:
        target = _parse_target(memory.anticipated_at)
        if target is not None and target <= now:
            arrived.append((target, memory))
    if not arrived:
        return None
    return min(arrived, key=lambda item: item[0])[1]


def format_arrived_anticipation(
    memory: Memory,
    truncate: Callable[[str, int], str],
) -> str:
    return (
        f'That time came: "{truncate(memory.content, 120)}". '
        "How was it, actually?"
    )


def format_approaching_anticipation(
    memory: Memory,
    now: datetime,
    truncate: Callable[[str, int], str],
) -> str:
    target = _parse_target(memory.anticipated_at)
    if target is None:
        raise ValueError("anticipated_at must be a valid datetime")
    now = timezone_utils.localize(now)
    delta = target - now
    hours_until = delta.total_seconds() / 3600
    days_until = delta.total_seconds() / 86400
    quote = truncate(memory.content, 120)
    if hours_until <= 24:
        return f'Approaching: "{quote}" (within a day).'
    if hours_until <= 48:
        return f'Approaching: "{quote}" (in a day or two).'
    return f'Approaching: "{quote}" (in about {round(days_until)} days).'
