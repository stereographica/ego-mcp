"""Recurrence lens: calendar echoes of earlier days (D1 S1).

The lens is purely mechanical: it matches calendar days (a year or more ago,
or exactly half a year ago) and ranks the memories that fall on them. It says
nothing about what the echo means — the wake_up line quotes the memory itself.

``compute`` looks ahead :data:`RECURRENCE_HORIZON_DAYS` days so a batch that
skips a day or two still has the coming dates on disk.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.preciousness import is_unarrived_anticipation
from ego_mcp.types import Memory

logger = logging.getLogger(__name__)

LENS_NAME = "recurrence"
RECURRENCE_TTL_HOURS = 36.0
#: Days ahead of ``snapshot.now`` that are computed in advance (inclusive).
RECURRENCE_HORIZON_DAYS = 7
RECURRENCE_MIN_IMPORTANCE = 4
#: Same threshold as ``preciousness.PRECIOUS_INTENSITY_MIN``.
RECURRENCE_PERSON_INTENSITY_MIN = 0.6
RECURRENCE_PRESENT_PROBABILITY = 0.5
#: Ranked: ``year`` always outranks ``half_year``.
RECURRENCE_PERIODS = ("year", "half_year")
#: At most this many candidates are written per target date.
RECURRENCE_MAX_PER_DATE = 3
#: Rounding of the emitted score, so the file is stable byte for byte.
RECURRENCE_SCORE_DIGITS = 3

_SCORE_PERSON_BONUS = 0.3
_SCORE_INTENSITY_WEIGHT = 0.5
_SCORE_IMPORTANCE_DIVISOR = 5.0
_HALF_YEAR_MONTHS = 6


def _add_months(source: date, months: int) -> date:
    """Return ``source`` shifted by ``months``, clamping to the month end."""
    month_index = source.month - 1 + months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _year_anniversary(memory_local_date: date, year: int) -> date:
    """Return the day in ``year`` that carries the memory's month and day.

    February 29th falls on February 28th in a common year (D1 D1).
    """
    month = memory_local_date.month
    day = memory_local_date.day
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return date(year, month, day)


def _calendar_matches(
    memory_local_date: date, target_date: date
) -> tuple[str, int] | None:
    """Return ``(period, span)`` when the two dates line up, else ``None``.

    ``year`` wins whenever both periods would match.
    """
    years = target_date.year - memory_local_date.year
    if years >= 1 and _year_anniversary(memory_local_date, target_date.year) == (
        target_date
    ):
        return ("year", years)
    if _add_months(memory_local_date, _HALF_YEAR_MONTHS) == target_date:
        return ("half_year", 1)
    return None


def _eligible(memory: Memory, now: datetime) -> bool:
    """Return whether the memory is worth coming back to (D1 D2).

    Either gate opens it: importance, or a person plus a strong trace. An
    anticipation that has not arrived yet belongs to the future channel and is
    never a recurrence candidate.
    """
    if is_unarrived_anticipation(memory, now):
        return False
    if memory.importance >= RECURRENCE_MIN_IMPORTANCE:
        return True
    if not memory.involved_person_ids:
        return False
    return float(memory.emotional_trace.intensity) >= RECURRENCE_PERSON_INTENSITY_MIN


def _score(memory: Memory) -> float:
    """Rank within one date: importance, then trace, then company (D1 D4)."""
    score = float(memory.importance) / _SCORE_IMPORTANCE_DIVISOR
    score += _SCORE_INTENSITY_WEIGHT * float(memory.emotional_trace.intensity)
    if memory.involved_person_ids:
        score += _SCORE_PERSON_BONUS
    return score


def _local_datetime(memory: Memory) -> datetime | None:
    """Return the memory timestamp in the app timezone, or ``None``."""
    if not isinstance(memory.timestamp, str) or not memory.timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(memory.timestamp)
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


class RecurrenceLens:
    """Calendar echoes for today and the coming week."""

    name = LENS_NAME
    needs_embeddings = False
    ttl_hours = RECURRENCE_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        now = snapshot.now
        today = timezone_utils.localize(now).date()

        candidates: list[tuple[Memory, date, datetime, float]] = []
        for memory in snapshot.memories:
            if not memory.id:
                continue
            moment = _local_datetime(memory)
            if moment is None:
                continue
            if not _eligible(memory, now):
                continue
            candidates.append((memory, moment.date(), moment, _score(memory)))

        items: list[dict[str, Any]] = []
        for offset in range(RECURRENCE_HORIZON_DAYS + 1):
            target = today + timedelta(days=offset)
            matched: list[tuple[int, float, datetime, Memory, str, int]] = []
            for memory, memory_date, moment, score in candidates:
                match = _calendar_matches(memory_date, target)
                if match is None:
                    continue
                period, span = match
                matched.append(
                    (
                        RECURRENCE_PERIODS.index(period),
                        -score,
                        moment,
                        memory,
                        period,
                        span,
                    )
                )
            # year before half_year, then score descending, then the older
            # memory (it carries the longer stretch of time).
            matched.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
            on_date = target.isoformat()
            for _, negated_score, _moment, memory, period, span in matched[
                :RECURRENCE_MAX_PER_DATE
            ]:
                items.append(
                    {
                        "key": f"{LENS_NAME}:{memory.id}:{on_date}",
                        "memory_id": memory.id,
                        "on_date": on_date,
                        "period": period,
                        "span": span,
                        "score": round(-negated_score, RECURRENCE_SCORE_DIGITS),
                    }
                )
        return items
