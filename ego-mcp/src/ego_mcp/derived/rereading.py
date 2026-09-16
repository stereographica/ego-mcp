"""Rereading lens (D7 S4).

Aggregates ``Memory.access_log`` for the dashboard: which memories are come
back to, how often, and in how many different moods. Presentation of the
rereading line lives in the recall handler (D7 S3); this lens is counting only
and its items never reach a tool response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ego_mcp.derived.source import SourceSnapshot

LENS_NAME = "rereading"
REREAD_TTL_HOURS = 36.0
REREAD_MAX_ITEMS = 30

#: A memory counts as "reread" from this many logged accesses on.
REREAD_MIN_ACCESSES = 3
#: ...and as "reread in different moods" from this many distinct non-empty moods.
REREAD_MIN_DISTINCT_MOODS = 2


def reread_key(memory_id: str, accesses: int) -> str:
    """Return the stable item key: it changes when the log grows."""
    return f"reread:{memory_id}:{accesses}"


def _parse_at(value: Any, now: datetime) -> datetime | None:
    """Parse an ``access_log`` timestamp, aligned to the snapshot's timezone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None and now.tzinfo is not None:
        return parsed.replace(tzinfo=now.tzinfo)
    if parsed.tzinfo is not None and now.tzinfo is None:
        return parsed.replace(tzinfo=None)
    return parsed


def _span_days(entries: list[dict[str, str]], now: datetime) -> int:
    """Whole days between the earliest and latest parsable ``at``."""
    stamps = [
        parsed
        for parsed in (_parse_at(entry.get("at"), now) for entry in entries)
        if parsed is not None
    ]
    if len(stamps) < 2:
        return 0
    return max(0, (max(stamps) - min(stamps)).days)


def _moods(entries: list[dict[str, str]]) -> list[str]:
    """Distinct non-empty moods, in first-seen order."""
    seen: dict[str, None] = {}
    for entry in entries:
        mood = entry.get("mood")
        if isinstance(mood, str) and mood:
            seen.setdefault(mood, None)
    return list(seen)


class RereadingLens:
    """How often, and in how many moods, each memory has been returned to."""

    name = LENS_NAME
    needs_embeddings = False
    ttl_hours = REREAD_TTL_HOURS

    def __init__(self) -> None:
        self.stats: dict[str, int] = {
            "reread_memory_count": 0,
            "reread_multi_mood_count": 0,
        }

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        reread_memory_count = 0
        reread_multi_mood_count = 0
        entries: list[tuple[int, int, str, dict[str, Any]]] = []

        for memory in snapshot.memories:
            log = [item for item in memory.access_log if isinstance(item, dict)]
            if len(log) < REREAD_MIN_ACCESSES:
                continue
            reread_memory_count += 1

            moods = _moods(log)
            if len(moods) >= REREAD_MIN_DISTINCT_MOODS:
                reread_multi_mood_count += 1

            item: dict[str, Any] = {
                "key": reread_key(memory.id, len(log)),
                "memory_id": memory.id,
                "accesses": len(log),
                "distinct_moods": len(moods),
                "span_days": _span_days(log, snapshot.now),
                "moods": moods,
            }
            entries.append((len(moods), len(log), memory.id, item))

        self.stats = {
            "reread_memory_count": reread_memory_count,
            "reread_multi_mood_count": reread_multi_mood_count,
        }

        entries.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        return [entry[3] for entry in entries[:REREAD_MAX_ITEMS]]
