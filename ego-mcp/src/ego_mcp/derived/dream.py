"""Dream lens: juxtapose two distant, unconnected memories (D2 S1).

The batch only *places two ids side by side*. It never creates a link, never
writes a memory and never says why the pair is a pair: the "thread" that makes
the pair minimally legible is recorded for telemetry but is not part of any
presentation (D2 D2 / D3).

``compute`` is a pure function of the snapshot; the sampling is seeded from the
snapshot date, so two runs on the same day dream the same dream.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.derived.graph import (
    MemoryGraph,
    build_memory_graph,
    cosine_distance,
    has_path_within,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory

LENS_NAME = "dream"
DREAM_TTL_HOURS = 48.0
DREAM_MIN_DISTANCE = 0.55
DREAM_MIN_AGE_DAYS = 7
DREAM_MIN_EMOTION_INTENSITY = 0.5
DREAM_GRAPH_HOPS = 2
DREAM_SAMPLE_PAIRS = 3000
DREAM_MAX_ITEMS = 3
DREAM_PRESENT_PROBABILITY = 0.15
DREAM_THREADS = ("emotion", "hour", "person", "tag")

#: Number of ``:``-separated fields in a surfaced dream key.
_DREAM_KEY_FIELDS = 3
#: A pair is a thread of type ``tag`` only when it shares *exactly* one tag;
#: two or more shared tags is what consolidate's theme link already picks up.
_DREAM_TAG_THREAD_COUNT = 1

_UNKNOWN_TIME_PHASE = "unknown"


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO timestamp, returning ``None`` for anything unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def _age_days(memory: Memory, now: datetime) -> float:
    """Age of ``memory`` in days, or ``-1.0`` when the timestamp is unusable.

    A negative age keeps an untimestamped memory out of the pool: we cannot
    show that it is old enough, and D2 D1.3 admits only memories we can.
    """
    parsed = _parse_time(memory.timestamp)
    if parsed is None:
        return -1.0
    elapsed = (timezone_utils.localize(now) - parsed).total_seconds()
    return elapsed / 86400.0


def _memory_tags(memory: Memory) -> list[str]:
    """Usable tags of a memory (replicated from ``ripening._memory_tags``)."""
    return [tag for tag in memory.tags if isinstance(tag, str) and tag]


def _shared_tags(left: list[str], right: list[str]) -> set[str]:
    """Tags present on both sides.

    Replicated verbatim from :func:`ego_mcp.ripening._shared_tags` (exact
    string match, non-string and empty tags dropped, no case folding) so the
    dream ``tag`` thread and ripening's tension pairing agree on what "the same
    tag" means. It is copied rather than imported because ``ripening`` pulls in
    the server runtime and the stores, which the batch must not import.
    """
    return {
        tag
        for tag in left
        if isinstance(tag, str)
        and tag
        and tag in {r for r in right if isinstance(r, str)}
    }


def _time_phase(memory: Memory) -> str:
    """The recorded time phase, or ``"unknown"`` when there is no body state."""
    trace = memory.emotional_trace
    if trace is None or trace.body_state is None:
        return _UNKNOWN_TIME_PHASE
    phase = trace.body_state.time_phase
    return phase if isinstance(phase, str) and phase else _UNKNOWN_TIME_PHASE


def _person_ids(memory: Memory) -> set[str]:
    return {
        person_id
        for person_id in memory.involved_person_ids
        if isinstance(person_id, str) and person_id
    }


def _threads(a: Memory, b: Memory) -> list[str]:
    """The thin threads that run between two memories (D2 D1.4).

    Returns the thread names in :data:`DREAM_THREADS` order; an empty list
    means the pair is pure noise and is not dream material.
    """
    threads: list[str] = []

    trace_a = a.emotional_trace
    trace_b = b.emotional_trace
    if (
        trace_a is not None
        and trace_b is not None
        and trace_a.primary == trace_b.primary
        and trace_a.intensity >= DREAM_MIN_EMOTION_INTENSITY
        and trace_b.intensity >= DREAM_MIN_EMOTION_INTENSITY
    ):
        threads.append("emotion")

    phase_a = _time_phase(a)
    if phase_a != _UNKNOWN_TIME_PHASE and phase_a == _time_phase(b):
        threads.append("hour")

    if _person_ids(a) & _person_ids(b):
        threads.append("person")

    shared = _shared_tags(_memory_tags(a), _memory_tags(b))
    if len(shared) == _DREAM_TAG_THREAD_COUNT:
        threads.append("tag")

    return threads


def _pair_key(a: str, b: str) -> tuple[str, str]:
    """Order a pair of ids lexicographically."""
    return (a, b) if a < b else (b, a)


def _surfaced_pairs(surfaced: dict[str, str]) -> list[tuple[str, str]]:
    """The pairs behind every well-formed ``dream:{a}:{b}`` mark.

    Marks that do not split into exactly three non-empty fields are ignored
    rather than guessed at.
    """
    pairs: list[tuple[str, str]] = []
    for key in surfaced:
        if not key.startswith(f"{LENS_NAME}:"):
            continue
        fields = key.split(":")
        if len(fields) != _DREAM_KEY_FIELDS:
            continue
        first, second = fields[1], fields[2]
        if not first or not second:
            continue
        pairs.append(_pair_key(first, second))
    return pairs


def _behavioural_stats(
    pairs: list[tuple[str, str]], graph: MemoryGraph
) -> dict[str, int]:
    """Count how many already-dreamt pairs the persona has since linked (D3).

    This is the whole effect measurement for T8: the batch never links, so a
    link between two juxtaposed memories can only have come from a decision.
    """
    linked = sum(1 for a, b in pairs if b in graph.adjacency.get(a, frozenset()))
    return {
        "dream_pairs_surfaced": len(pairs),
        "dream_pairs_linked": linked,
    }


class DreamLens:
    """Pairs of distant, unconnected memories held side by side."""

    name = LENS_NAME
    needs_embeddings = True
    ttl_hours = DREAM_TTL_HOURS

    def __init__(self) -> None:
        self.stats: dict[str, int] = {}

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        graph = build_memory_graph(snapshot)
        surfaced_pairs = _surfaced_pairs(snapshot.surfaced)
        self.stats = _behavioural_stats(surfaced_pairs, graph)

        embeddings = snapshot.embeddings or {}
        pool = [
            memory
            for memory in snapshot.memories
            if memory.id in embeddings
            and _age_days(memory, snapshot.now) >= DREAM_MIN_AGE_DAYS
        ]
        if len(pool) < 2:
            return []

        seen_pairs = set(surfaced_pairs)
        rng = random.Random(snapshot.now.date().isoformat())
        candidates: dict[tuple[str, str], tuple[float, list[str]]] = {}
        for _ in range(DREAM_SAMPLE_PAIRS):
            a, b = rng.sample(pool, 2)
            pair = _pair_key(a.id, b.id)
            if pair in seen_pairs or pair in candidates:
                continue
            distance = cosine_distance(embeddings[a.id], embeddings[b.id])
            if distance < DREAM_MIN_DISTANCE:
                continue
            if has_path_within(graph, a.id, b.id, DREAM_GRAPH_HOPS):
                continue
            if graph.notions_of_memory.get(a.id, set()) & graph.notions_of_memory.get(
                b.id, set()
            ):
                continue
            threads = _threads(a, b)
            if not threads:
                continue
            candidates[pair] = (distance, threads)

        ordered = sorted(
            candidates.items(), key=lambda entry: (-entry[1][0], entry[0])
        )
        return [
            {
                "key": f"{LENS_NAME}:{first}:{second}",
                "memory_ids": [first, second],
                "distance": round(distance, 3),
                "threads": threads,
            }
            for (first, second), (distance, threads) in ordered[:DREAM_MAX_ITEMS]
        ]
