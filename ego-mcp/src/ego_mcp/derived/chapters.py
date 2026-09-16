"""Chapter-boundary lens: where the shape of the weeks turns (D5 S1).

Memories are bucketed into ISO weeks; each week carries a topic centroid, a
mean valence and the people who appear in it. A boundary is a week where the
four weeks before and the four weeks after are far apart on those three axes.

The lens names nothing. It emits the week, the distance and the id of the
memory nearest to each window's centre — the quoting is the server's job.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple

import numpy as np

from ego_mcp import timezone_utils
from ego_mcp.derived.graph import centroid, cosine_distance
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory

logger = logging.getLogger(__name__)

LENS_NAME = "chapters"
CHAPTER_TTL_HOURS = 336.0  # 14 days
CHAPTER_WINDOW_WEEKS = 4
CHAPTER_MIN_MEMORIES_PER_WINDOW = 6
CHAPTER_SCORE_MIN = 0.35
CHAPTER_MIN_GAP_WEEKS = 6
CHAPTER_LOCAL_MAX_RADIUS_WEEKS = 2
CHAPTER_MAX_ITEMS = 12
CHAPTER_W_VALENCE = 0.5
CHAPTER_W_PEOPLE = 0.5
#: Item keys are singular: the lens is "chapters", one item is one chapter.
CHAPTER_KEY_PREFIX = "chapter:"
#: A boundary re-detected within this many weeks of an already surfaced one is
#: treated as the same turn and keeps the surfaced key.
CHAPTER_KEY_CARRY_WEEKS = 1
#: Rounding of the emitted score, so the file is stable byte for byte.
CHAPTER_SCORE_DIGITS = 3

_DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class WeekBucket:
    """One ISO week of memories that carry an embedding."""

    week_start: date
    memory_ids: list[str]
    centroid: np.ndarray | None
    mean_valence: float
    people: frozenset[str]


class WindowStats(NamedTuple):
    """Aggregate of consecutive buckets; a tuple that also reads by name."""

    centroid: np.ndarray | None
    mean_valence: float
    people: frozenset[str]
    memory_ids: list[str]


def _local_datetime(memory: Memory) -> datetime | None:
    """Return the memory timestamp in the app timezone, or ``None``."""
    if not isinstance(memory.timestamp, str) or not memory.timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(memory.timestamp)
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def _week_start(moment: datetime) -> date:
    """Return the Monday of the ISO week containing ``moment``."""
    day = moment.date()
    return day - timedelta(days=day.weekday())


def _bucket_by_week(
    memories: Sequence[Memory],
    embeddings: Mapping[str, np.ndarray],
) -> list[WeekBucket]:
    """Group memories that have an embedding into consecutive ISO weeks.

    Weeks with no memory are kept as empty buckets so week indices stay a
    continuous timeline: a quiet stretch must not pull two eras together.
    """
    grouped: dict[date, list[tuple[datetime, Memory]]] = {}
    for memory in memories:
        if not memory.id or memory.id not in embeddings:
            continue
        moment = _local_datetime(memory)
        if moment is None:
            continue
        grouped.setdefault(_week_start(moment), []).append((moment, memory))

    if not grouped:
        return []

    buckets: list[WeekBucket] = []
    last = max(grouped)
    week = min(grouped)
    while week <= last:
        entries = sorted(grouped.get(week, []), key=lambda pair: (pair[0], pair[1].id))
        memory_ids = [memory.id for _, memory in entries]
        valences = [float(memory.emotional_trace.valence) for _, memory in entries]
        people: set[str] = set()
        for _, memory in entries:
            people.update(
                person_id for person_id in memory.involved_person_ids if person_id
            )
        buckets.append(
            WeekBucket(
                week_start=week,
                memory_ids=memory_ids,
                centroid=centroid([embeddings[key] for key in memory_ids]),
                mean_valence=(sum(valences) / len(valences)) if valences else 0.0,
                people=frozenset(people),
            )
        )
        week = week + timedelta(days=_DAYS_PER_WEEK)
    return buckets


def _window(buckets: Sequence[WeekBucket], start_idx: int, n: int) -> WindowStats:
    """Aggregate ``n`` buckets starting at ``start_idx``.

    The valence mean is weighted by memory count, so it equals the mean over
    the window's memories and empty weeks do not pull it toward zero.
    """
    memory_ids: list[str] = []
    people: set[str] = set()
    vectors: list[np.ndarray] = []
    valence_total = 0.0
    for bucket in buckets[start_idx : start_idx + n]:
        memory_ids.extend(bucket.memory_ids)
        people.update(bucket.people)
        if bucket.centroid is not None:
            vectors.append(bucket.centroid)
        valence_total += bucket.mean_valence * len(bucket.memory_ids)
    return WindowStats(
        centroid=centroid(vectors),
        mean_valence=valence_total / len(memory_ids) if memory_ids else 0.0,
        people=frozenset(people),
        memory_ids=memory_ids,
    )


def _boundary_score(before: WindowStats, after: WindowStats) -> float:
    """Distance between two windows on topic, valence and people (D5 D1)."""
    if before.centroid is None or after.centroid is None:
        d_topic = 0.0
    else:
        d_topic = cosine_distance(before.centroid, after.centroid)
    d_valence = abs(before.mean_valence - after.mean_valence)
    union = before.people | after.people
    d_people = (
        0.0 if not union else 1.0 - len(before.people & after.people) / len(union)
    )
    return d_topic + CHAPTER_W_VALENCE * d_valence + CHAPTER_W_PEOPLE * d_people


def _nearest_memory_id(
    memory_ids: Sequence[str],
    embeddings: Mapping[str, np.ndarray],
    center: np.ndarray | None,
) -> str:
    """Return the id in ``memory_ids`` closest to ``center`` (first wins ties)."""
    if center is None:
        return ""
    best_id = ""
    best_distance = float("inf")
    for memory_id in memory_ids:
        vector = embeddings.get(memory_id)
        if vector is None:
            continue
        distance = cosine_distance(vector, center)
        if distance < best_distance:
            best_distance = distance
            best_id = memory_id
    return best_id


def _is_local_max(by_index: Mapping[int, float], index: int) -> bool:
    """Return whether ``index`` scores at least as high as its neighbours."""
    score = by_index[index]
    radius = CHAPTER_LOCAL_MAX_RADIUS_WEEKS
    for offset in range(-radius, radius + 1):
        if offset == 0:
            continue
        neighbour = by_index.get(index + offset)
        if neighbour is not None and neighbour > score:
            return False
    return True


def _surfaced_boundary_weeks(surfaced: Mapping[str, str]) -> list[date]:
    """Return the boundary weeks already marked as surfaced, oldest first."""
    weeks: list[date] = []
    for key in surfaced:
        if not key.startswith(CHAPTER_KEY_PREFIX):
            continue
        try:
            weeks.append(date.fromisoformat(key[len(CHAPTER_KEY_PREFIX) :]))
        except ValueError:
            continue
    return sorted(weeks)


def _carry_over_key(
    week_start: date,
    known_weeks: Sequence[date],
    used: set[str],
) -> str:
    """Return the key for ``week_start``, reusing a known one within a week.

    A boundary that shifts by a week between runs is the same turn; keeping
    the old key keeps it marked as already presented (D5 S1).
    """
    exact = f"{CHAPTER_KEY_PREFIX}{week_start.isoformat()}"
    if exact in used or week_start in known_weeks:
        return exact
    limit = CHAPTER_KEY_CARRY_WEEKS * _DAYS_PER_WEEK
    best: date | None = None
    best_gap = limit + 1
    for known in known_weeks:  # oldest first, so a tie keeps the older week
        gap = abs((known - week_start).days)
        if gap > limit or gap >= best_gap:
            continue
        if f"{CHAPTER_KEY_PREFIX}{known.isoformat()}" in used:
            continue
        best, best_gap = known, gap
    if best is None:
        return exact
    return f"{CHAPTER_KEY_PREFIX}{best.isoformat()}"


class ChaptersLens:
    """Unnamed chapter boundaries, newest first."""

    name = LENS_NAME
    needs_embeddings = True
    ttl_hours = CHAPTER_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        embeddings: Mapping[str, np.ndarray] = snapshot.embeddings or {}
        buckets = _bucket_by_week(snapshot.memories, embeddings)

        window = CHAPTER_WINDOW_WEEKS
        scored: list[tuple[int, float, WindowStats, WindowStats]] = []
        # The last window's worth of weeks is never judged: a boundary only
        # becomes visible once there is a full stretch of weeks after it.
        for index in range(window, len(buckets) - window):
            before = _window(buckets, index - window, window)
            after = _window(buckets, index, window)
            if (
                len(before.memory_ids) < CHAPTER_MIN_MEMORIES_PER_WINDOW
                or len(after.memory_ids) < CHAPTER_MIN_MEMORIES_PER_WINDOW
            ):
                continue
            scored.append((index, _boundary_score(before, after), before, after))

        by_index = {index: score for index, score, _, _ in scored}
        peaks = [
            entry
            for entry in scored
            if entry[1] >= CHAPTER_SCORE_MIN and _is_local_max(by_index, entry[0])
        ]

        # Highest score first, older week on a tie: the older boundary is the
        # one more likely to be surfaced already.
        peaks.sort(key=lambda entry: (-entry[1], entry[0]))
        accepted: list[tuple[int, float, WindowStats, WindowStats]] = []
        for entry in peaks:
            if any(
                abs(entry[0] - kept[0]) < CHAPTER_MIN_GAP_WEEKS for kept in accepted
            ):
                continue
            accepted.append(entry)
        accepted.sort(key=lambda entry: entry[0], reverse=True)

        known_weeks = _surfaced_boundary_weeks(snapshot.surfaced)
        used: set[str] = set()
        items: list[dict[str, Any]] = []
        for index, score, before, after in accepted[:CHAPTER_MAX_ITEMS]:
            week_start = buckets[index].week_start
            key = _carry_over_key(week_start, known_weeks, used)
            used.add(key)
            items.append(
                {
                    "key": key,
                    "boundary_week": week_start.isoformat(),
                    "score": round(score, CHAPTER_SCORE_DIGITS),
                    "before_memory_id": _nearest_memory_id(
                        before.memory_ids, embeddings, before.centroid
                    ),
                    "after_memory_id": _nearest_memory_id(
                        after.memory_ids, embeddings, after.centroid
                    ),
                    "people_before": sorted(before.people),
                    "people_after": sorted(after.people),
                }
            )
        return items
