"""Co-retrieval lens (P1 S2).

Counts which memories keep coming back *together* from ``recall``, with a
30-day half-life, and splits the surviving pairs into those the memory graph
already links (Hebbian reinforcement candidates) and those it does not
(candidates to offer). The lens only counts: it never creates a link, never
names a link type, and never touches memory text.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Any

from ego_mcp.derived.graph import build_memory_graph, cosine_distance
from ego_mcp.derived.source import SourceSnapshot

LENS_NAME = "coretrieval"
CO_RETRIEVAL_TTL_HOURS = 48.0
CO_RETRIEVAL_HALF_LIFE_DAYS = 30.0
CO_RETRIEVAL_MIN_WEIGHT = 2.5
CO_RETRIEVAL_MIN_DISTANCE = 0.15
CO_RETRIEVAL_MAX_UNLINKED = 5
CO_RETRIEVAL_MAX_LINKED = 20

#: A recall that returned more than this many memories is capped rather than
#: dropped: only the first ids form pairs, so one wide recall cannot explode
#: into hundreds of pairs.
CO_RETRIEVAL_MAX_IDS_PER_RECALL = 10

KIND_LINKED = "linked"
KIND_UNLINKED = "unlinked"

#: Decimals kept for the numbers written into the derived file. Thresholds and
#: ordering always use the unrounded values.
_VALUE_DIGITS = 4


def co_retrieval_key(a: str, b: str) -> str:
    """Return the stable item key for a pair, normalized to id order."""
    first, second = (a, b) if a <= b else (b, a)
    return f"coretrieval:{first}:{second}"


def _age_days(now: datetime, at: datetime) -> int:
    """Whole days between ``at`` and ``now``, never negative.

    The log is written by the server in the application timezone while ``now``
    comes from the snapshot; a naive/aware mismatch is resolved the same way
    :mod:`ego_mcp.derived.contract` resolves it, rather than raising.
    """
    if at.tzinfo is None and now.tzinfo is not None:
        at = at.replace(tzinfo=now.tzinfo)
    elif at.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=at.tzinfo)
    return max(0, (now - at).days)


class CoRetrievalLens:
    """Weighted co-retrieval pairs, split into linked and unlinked."""

    name = LENS_NAME
    needs_embeddings = True
    ttl_hours = CO_RETRIEVAL_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        weights = self._pair_weights(snapshot)
        if not weights:
            return []

        graph = build_memory_graph(snapshot)
        embeddings = snapshot.embeddings or {}

        linked: list[tuple[float, str, str, dict[str, Any]]] = []
        unlinked: list[tuple[float, str, str, dict[str, Any]]] = []

        for (a, b), weight in weights.items():
            if weight < CO_RETRIEVAL_MIN_WEIGHT:
                continue

            key = co_retrieval_key(a, b)
            if key in snapshot.surfaced:
                # Drop before the caps, not after: consolidate skips surfaced
                # keys when it reads the file, so a pair that is still in the
                # top 5 / top 20 would otherwise hold a slot forever and starve
                # every pair below it (the dream lens filters the same way).
                continue

            distance: float | None = None
            vector_a = embeddings.get(a)
            vector_b = embeddings.get(b)
            if vector_a is not None and vector_b is not None:
                distance = cosine_distance(vector_a, vector_b)
                if distance < CO_RETRIEVAL_MIN_DISTANCE:
                    # Near-identical pairs belong to merge, not to link.
                    continue

            kind = KIND_LINKED if b in graph.adjacency.get(a, set()) else KIND_UNLINKED
            item: dict[str, Any] = {
                "key": key,
                "memory_ids": [a, b],
                "weight": round(weight, _VALUE_DIGITS),
                "distance": (
                    None if distance is None else round(distance, _VALUE_DIGITS)
                ),
                "kind": kind,
            }
            bucket = linked if kind == KIND_LINKED else unlinked
            bucket.append((weight, a, b, item))

        return _top(unlinked, CO_RETRIEVAL_MAX_UNLINKED) + _top(
            linked, CO_RETRIEVAL_MAX_LINKED
        )

    def _pair_weights(self, snapshot: SourceSnapshot) -> dict[tuple[str, str], float]:
        """Sum the decayed weight of every unordered pair in the recall log."""
        existing = {memory.id for memory in snapshot.memories}
        weights: dict[tuple[str, str], float] = defaultdict(float)

        for at, ids in snapshot.co_retrievals:
            kept = [
                memory_id
                for memory_id in dict.fromkeys(ids)
                if memory_id in existing
            ][:CO_RETRIEVAL_MAX_IDS_PER_RECALL]
            if len(kept) < 2:
                continue
            age = _age_days(snapshot.now, at)
            decay = 0.5 ** (age / CO_RETRIEVAL_HALF_LIFE_DAYS)
            for a, b in combinations(sorted(kept), 2):
                weights[(a, b)] += decay

        return dict(weights)


def _top(
    entries: list[tuple[float, str, str, dict[str, Any]]], limit: int
) -> list[dict[str, Any]]:
    """Return the ``limit`` heaviest items, ties broken by id order."""
    entries.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
    return [entry[3] for entry in entries[:limit]]
