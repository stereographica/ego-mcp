"""Notion drift lens: the ground under a notion moved (D4 S1).

Two mechanical signals, both measured and never interpreted:

``drift``
    The source memories of a notion, split at their median timestamp, have
    centroids that sit far apart *relative to how spread out each half is*.
    The lens emits the distance, the ratio and the id of the newer-half memory
    closest to the newer centroid — never where the ground moved *to*.

``stale_conviction``
    A conviction (``is_conviction``) that has not been reinforced for
    :data:`DRIFT_STALE_DAYS` days.

Nothing here changes a label, a confidence or a reinforcement count: D4 turns
one landscape line into a question, and the answer is lived, not computed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np

from ego_mcp.derived.graph import centroid, cosine_distance
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.notion import is_conviction
from ego_mcp.types import Memory, Notion

LENS_NAME = "drift"
DRIFT_TTL_HOURS = 168.0
#: Source memories (with embeddings, not deleted) a notion needs to be judged.
DRIFT_MIN_SOURCES = 6
#: Minimum size of each half after the median split.
DRIFT_MIN_HALF = 3
#: Minimum cosine distance between the two half centroids.
DRIFT_MIN_DISTANCE = 0.20
#: Minimum ``distance / dispersion`` — the move must beat the natural spread.
DRIFT_RATIO_MIN = 1.5
#: Dispersion floor, so a tight cluster cannot make the ratio explode.
DRIFT_DISPERSION_FLOOR = 0.05
#: Days without reinforcement before a conviction counts as stale.
DRIFT_STALE_DAYS = 45
DRIFT_MAX_DRIFT_ITEMS = 3
DRIFT_MAX_STALE_ITEMS = 2

DRIFT_DISTANCE_DIGITS = 3
DRIFT_RATIO_DIGITS = 2

_SECONDS_PER_DAY = 86400.0


def _parse_moment(value: str, *, reference: datetime) -> datetime | None:
    """Parse an ISO timestamp into something comparable with ``reference``.

    A naive timestamp adopts the reference's timezone (the stores write local
    ISO strings); an aware timestamp compared against a naive reference is
    stripped. Anything unparsable is ``None`` — the caller drops it rather than
    guessing where it belongs in time.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None and reference.tzinfo is not None:
        return parsed.replace(tzinfo=reference.tzinfo)
    if parsed.tzinfo is not None and reference.tzinfo is None:
        return parsed.replace(tzinfo=None)
    return parsed


def _split_halves(
    memories_sorted_by_time: Sequence[Memory],
) -> tuple[list[Memory], list[Memory]]:
    """Split at the median; an odd count gives the extra memory to the newer half."""
    midpoint = len(memories_sorted_by_time) // 2
    return (
        list(memories_sorted_by_time[:midpoint]),
        list(memories_sorted_by_time[midpoint:]),
    )


def _dispersion(vectors: Sequence[np.ndarray], center: np.ndarray) -> float:
    """Mean cosine distance from ``center``; an empty set has no spread."""
    if len(vectors) == 0:
        return 0.0
    total = sum(cosine_distance(vector, center) for vector in vectors)
    return float(total) / len(vectors)


def _sources(
    notion: Notion,
    memory_by_id: dict[str, Memory],
    embeddings: dict[str, np.ndarray],
    *,
    now: datetime,
) -> list[tuple[datetime, Memory]]:
    """Return the usable source memories of a notion, oldest first.

    Dropped: ids repeated in ``source_memory_ids``, ids whose memory is gone
    (dead links), ids without an embedding (never embedded, or dropped by the
    snapshot's dimension filter), and memories whose timestamp does not parse
    (they cannot be placed in a half).
    """
    usable: list[tuple[datetime, Memory]] = []
    seen: set[str] = set()
    for memory_id in notion.source_memory_ids:
        if not isinstance(memory_id, str) or memory_id in seen:
            continue
        memory = memory_by_id.get(memory_id)
        if memory is None or memory_id not in embeddings:
            continue
        moment = _parse_moment(memory.timestamp, reference=now)
        if moment is None:
            continue
        seen.add(memory_id)
        usable.append((moment, memory))
    usable.sort(key=lambda entry: (entry[0], entry[1].id))
    return usable


def _measure_drift(
    notion: Notion,
    memory_by_id: dict[str, Memory],
    embeddings: dict[str, np.ndarray],
    *,
    now: datetime,
) -> tuple[float, float, str] | None:
    """Return ``(distance, ratio, nearest_id)`` when the notion's ground moved."""
    usable = _sources(notion, memory_by_id, embeddings, now=now)
    if len(usable) < DRIFT_MIN_SOURCES:
        return None

    moment_of = {memory.id: moment for moment, memory in usable}
    older, newer = _split_halves([memory for _, memory in usable])
    if len(older) < DRIFT_MIN_HALF or len(newer) < DRIFT_MIN_HALF:
        return None

    older_vectors = [embeddings[memory.id] for memory in older]
    newer_vectors = [embeddings[memory.id] for memory in newer]
    older_centroid = centroid(older_vectors)
    newer_centroid = centroid(newer_vectors)
    if older_centroid is None or newer_centroid is None:
        return None

    distance = cosine_distance(older_centroid, newer_centroid)
    dispersion = (
        _dispersion(older_vectors, older_centroid)
        + _dispersion(newer_vectors, newer_centroid)
    ) / 2.0
    ratio = distance / max(dispersion, DRIFT_DISPERSION_FLOOR)
    if distance < DRIFT_MIN_DISTANCE or ratio < DRIFT_RATIO_MIN:
        return None

    nearest = min(
        newer,
        key=lambda memory: (
            cosine_distance(embeddings[memory.id], newer_centroid),
            -moment_of[memory.id].timestamp(),
            memory.id,
        ),
    )
    return distance, ratio, nearest.id


def _stale_days(notion: Notion, *, now: datetime) -> float | None:
    """Return the days since a conviction was reinforced, or ``None``."""
    if not is_conviction(notion):
        return None
    reinforced = _parse_moment(notion.last_reinforced, reference=now)
    if reinforced is None:
        return None
    days = (now - reinforced).total_seconds() / _SECONDS_PER_DAY
    if days < DRIFT_STALE_DAYS:
        return None
    return days


class DriftLens:
    """Notions whose source ground moved, and convictions left unrevisited."""

    name = LENS_NAME
    needs_embeddings = True
    ttl_hours = DRIFT_TTL_HOURS

    def __init__(self) -> None:
        self.stats: dict[str, int] = {}

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        embeddings = snapshot.embeddings or {}
        memory_by_id = {memory.id: memory for memory in snapshot.memories}
        generated_date = snapshot.now.date().isoformat()

        drift_candidates: list[tuple[float, float, str, dict[str, Any]]] = []
        drift_notion_ids: set[str] = set()
        for notion in snapshot.notions:
            measured = _measure_drift(
                notion, memory_by_id, embeddings, now=snapshot.now
            )
            if measured is None:
                continue
            distance, ratio, nearest_id = measured
            drift_notion_ids.add(notion.id)
            drift_candidates.append(
                (
                    distance,
                    ratio,
                    notion.id,
                    {
                        "key": f"{LENS_NAME}:{notion.id}:{generated_date}",
                        "kind": "drift",
                        "notion_id": notion.id,
                        "distance": round(distance, DRIFT_DISTANCE_DIGITS),
                        "ratio": round(ratio, DRIFT_RATIO_DIGITS),
                        "newest_source_memory_id": nearest_id,
                    },
                )
            )

        stale_candidates: list[tuple[float, str, dict[str, Any]]] = []
        for notion in snapshot.notions:
            # A notion that drifted is asked about as drift only, even when the
            # drift item itself loses its slot to the cap.
            if notion.id in drift_notion_ids:
                continue
            days = _stale_days(notion, now=snapshot.now)
            if days is None:
                continue
            stale_candidates.append(
                (
                    days,
                    notion.id,
                    {
                        "key": f"{LENS_NAME}:{notion.id}:{generated_date}:stale",
                        "kind": "stale_conviction",
                        "notion_id": notion.id,
                        "days_since_reinforced": int(days),
                    },
                )
            )

        # Distance descending, then ratio descending, then notion id: the file
        # must be byte-stable across two runs of the same snapshot.
        drift_candidates.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        stale_candidates.sort(key=lambda entry: (-entry[0], entry[1]))

        drift_items = [item for _, _, _, item in drift_candidates][
            :DRIFT_MAX_DRIFT_ITEMS
        ]
        stale_items = [item for _, _, item in stale_candidates][:DRIFT_MAX_STALE_ITEMS]

        self.stats = {
            "notion_count": len(snapshot.notions),
            "drift_candidates": len(drift_candidates),
            "stale_candidates": len(stale_candidates),
            "drift_items": len(drift_items),
            "stale_items": len(stale_items),
        }
        return drift_items + stale_items
