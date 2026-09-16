"""Stagnation index — four statistics on the shape of the recent window (D6 S1).

The lens measures four signs of a self-locking loop over the last
:data:`STAGNATION_WINDOW_DAYS` days: consecutive introspections saying the same
thing, themes repeating from the days before, links reaching only the near and
the new, and no question being born. It composes them into one score and one
band, and stops there — the numbers exist for telemetry, never for the response
text (D6 D4, future_plan article 4).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from ego_mcp import timezone_utils
from ego_mcp.derived.graph import MemoryGraph, build_memory_graph, cosine_distance
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Category, Memory

LENS_NAME = "stagnation"
STAGNATION_TTL_HOURS = 36.0
STAGNATION_WINDOW_DAYS = 14
STAGNATION_ROLLING_DAYS = 5
STAGNATION_MIN_MEMORIES = 8
STAGNATION_OLD_LINK_DAYS = 30
STAGNATION_W = {
    "sameness": 0.35,
    "repetition": 0.35,
    "novelty": 0.20,
    "births": 0.10,
}
STAGNATION_CIRCLING_MIN = 0.45
STAGNATION_STUCK_MIN = 0.65
STAGNATION_SOCIAL_THIRST_BOOST = 0.06
STAGNATION_EXPRESSION_BOOST = 0.04

#: 6b (modulation) ships disabled; flip to ``True`` once 6a has been observed.
STAGNATION_MODULATION_ENABLED = False

STAGNATION_BAND_FLOWING = "flowing"
STAGNATION_BAND_CIRCLING = "circling"
STAGNATION_BAND_STUCK = "stuck"

#: Categories that are always present and would inflate the repetition rate.
STAGNATION_GENERIC_CATEGORIES = frozenset(
    {Category.DAILY.value, Category.CONVERSATION.value}
)

#: Decimals kept in the written file, so a rerun on the same day is comparable.
STAGNATION_PRECISION = 3


# --- helpers ----------------------------------------------------------------


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO timestamp into an aware datetime, or ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def memory_times(memories: list[Memory]) -> dict[str, datetime]:
    """Map memory id -> parsed timestamp, skipping unparsable ones."""
    times: dict[str, datetime] = {}
    for memory in memories:
        parsed = _parse_time(memory.timestamp)
        if parsed is not None and memory.id:
            times[memory.id] = parsed
    return times


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_tag(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.strip().lower()


def _themes(memory: Memory) -> list[str]:
    """Theme tokens for one memory: its tags plus its non-generic category.

    Tags and categories live in separate namespaces so a tag that happens to be
    spelled like a category is not counted as the same theme.
    """
    themes: list[str] = []
    seen: set[str] = set()
    for raw_tag in memory.tags:
        tag = _normalize_tag(raw_tag)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        themes.append(f"tag:{tag}")
    category = getattr(memory.category, "value", str(memory.category))
    if category and category not in STAGNATION_GENERIC_CATEGORIES:
        themes.append(f"category:{category}")
    return themes


# --- components -------------------------------------------------------------


def introspection_sameness(
    memories_in_window: list[Memory],
    embeddings: Mapping[str, np.ndarray] | None,
) -> float | None:
    """Mean cosine similarity between consecutive introspections.

    Only ``introspection`` memories that carry an embedding take part. Fewer
    than two of them means the component is missing, not zero.
    """
    ordered: list[tuple[datetime, str, np.ndarray]] = []
    for memory in memories_in_window:
        if memory.category != Category.INTROSPECTION:
            continue
        vector = None if embeddings is None else embeddings.get(memory.id)
        parsed = _parse_time(memory.timestamp)
        if vector is None or parsed is None:
            continue
        ordered.append((parsed, memory.id, vector))

    if len(ordered) < 2:
        return None
    ordered.sort(key=lambda entry: (entry[0], entry[1]))

    similarities: list[float] = []
    for (_, _, left), (_, _, right) in zip(ordered, ordered[1:], strict=False):
        if left.shape != right.shape:
            continue
        similarities.append(1.0 - cosine_distance(left, right))
    if not similarities:
        return None
    return _clamp(sum(similarities) / len(similarities))


def theme_repetition(memories_in_window: list[Memory], now: datetime) -> float | None:
    """Mean share of a day's themes that already appeared in the five days before.

    A day without themes is skipped; a window without any theme-bearing day
    leaves the component missing.
    """
    today = timezone_utils.localize(now).date()
    by_day: dict[date, list[str]] = defaultdict(list)
    for memory in memories_in_window:
        parsed = _parse_time(memory.timestamp)
        if parsed is None:
            continue
        day = parsed.date()
        if day > today:
            continue
        by_day[day].extend(_themes(memory))

    days = sorted(day for day, themes in by_day.items() if themes)
    if not days:
        return None

    rates: list[float] = []
    for day in days:
        themes = by_day[day]
        previous: set[str] = set()
        for offset in range(1, STAGNATION_ROLLING_DAYS + 1):
            previous.update(by_day.get(day - timedelta(days=offset), []))
        repeated = sum(1 for theme in themes if theme in previous)
        rates.append(repeated / len(themes))
    return _clamp(sum(rates) / len(rates))


def link_novelty(
    memories_in_window: list[Memory],
    graph: MemoryGraph,
    now: datetime,
    *,
    timestamps: Mapping[str, datetime],
) -> float | None:
    """Share of the window's links that reach far: another component, or an old memory.

    Links have no timestamp of their own, so every link held by a memory in the
    window counts as drawn in the window. Dead links, self-links and links to a
    memory whose timestamp cannot be read are not counted at all; no live link
    at all leaves the component missing rather than zero.
    """
    cutoff = timezone_utils.localize(now) - timedelta(days=STAGNATION_OLD_LINK_DAYS)
    counted: set[tuple[str, str]] = set()
    total = 0
    novel = 0

    for memory in memories_in_window:
        for link in memory.linked_ids:
            target = link.target_id
            if not isinstance(target, str) or not target or target == memory.id:
                continue
            if target not in graph.adjacency:
                continue
            pair = (memory.id, target)
            if pair in counted:
                continue
            counted.add(pair)
            target_time = timestamps.get(target)
            if target_time is None:
                continue
            total += 1
            far = graph.component_of.get(memory.id) != graph.component_of.get(target)
            if far or target_time <= cutoff:
                novel += 1

    if total == 0:
        return None
    return _clamp(novel / total)


def question_births(
    question_log: list[dict[str, Any]], window_start: datetime
) -> int:
    """Number of questions whose ``created_at`` falls inside the window."""
    births = 0
    for entry in question_log:
        created = _parse_time(entry.get("created_at"))
        if created is not None and created >= window_start:
            births += 1
    return births


# --- composition ------------------------------------------------------------


def _contribution(name: str, value: float) -> float:
    """Turn one component into its stagnation-direction contribution."""
    if name == "novelty":
        return _clamp(1.0 - value)
    if name == "births":
        return 1.0 if value == 0 else 0.0
    return _clamp(value)


def compose_score(components: Mapping[str, float | None]) -> float:
    """Weighted mean of the present components; missing weights are redistributed."""
    weighted = 0.0
    total_weight = 0.0
    for name, weight in STAGNATION_W.items():
        value = components.get(name)
        if value is None:
            continue
        weighted += weight * _contribution(name, float(value))
        total_weight += weight
    if total_weight <= 0.0:
        return 0.0
    return round(_clamp(weighted / total_weight), STAGNATION_PRECISION)


def band_for(score: float) -> str:
    """Name the band a score falls in (D6 D1)."""
    if score < STAGNATION_CIRCLING_MIN:
        return STAGNATION_BAND_FLOWING
    if score < STAGNATION_STUCK_MIN:
        return STAGNATION_BAND_CIRCLING
    return STAGNATION_BAND_STUCK


class StagnationLens:
    """One measurement of the recent window's shape (D6)."""

    name = LENS_NAME
    needs_embeddings = True
    ttl_hours = STAGNATION_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        """Return one item, or nothing when the window is too thin to judge.

        Thin activity is absence, not stagnation (T2 holds that), so fewer than
        :data:`STAGNATION_MIN_MEMORIES` memories in the window emits nothing.
        """
        window_start = snapshot.now - timedelta(days=STAGNATION_WINDOW_DAYS)
        times = memory_times(snapshot.memories)
        window = [
            memory
            for memory in snapshot.memories
            if (time := times.get(memory.id)) is not None and time >= window_start
        ]
        if len(window) < STAGNATION_MIN_MEMORIES:
            return []

        graph = build_memory_graph(snapshot)
        components: dict[str, float | None] = {
            "sameness": _rounded(introspection_sameness(window, snapshot.embeddings)),
            "repetition": _rounded(theme_repetition(window, snapshot.now)),
            "novelty": _rounded(
                link_novelty(window, graph, snapshot.now, timestamps=times)
            ),
            "births": float(question_births(snapshot.question_log, window_start)),
        }
        score = compose_score(components)
        day = snapshot.now.date().isoformat()
        return [
            {
                "key": f"stagnation:{day}",
                "band": band_for(score),
                "score": score,
                "components": components,
                "memory_count": len(window),
            }
        ]


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, STAGNATION_PRECISION)
