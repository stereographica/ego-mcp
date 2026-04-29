"""Proust involuntary recall — probabilistic surfacing of old memories."""

from __future__ import annotations

import random as _random_module
from datetime import datetime, timedelta, timezone
from random import Random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ego_mcp._memory_store import MemoryStore
    from ego_mcp.types import Memory

_MIN_AGE_DAYS = 30
_MAX_ACCESS_COUNT = 2
_SEARCH_N = 15
_DEFAULT_PROBABILITY = 0.25
PROUST_PERSON_PROBABILITY = 0.08


async def find_proust_memory(
    seed_query: str,
    memory_store: MemoryStore,
    probability: float = _DEFAULT_PROBABILITY,
    random_source: Random | None = None,
) -> Memory | None:
    """Search for an old, rarely-accessed memory semantically close to *seed_query*.

    Returns a single memory with probability *probability*, or ``None``.
    """
    rng = random_source if random_source is not None else _random_module.Random()

    cutoff = datetime.now(timezone.utc) - timedelta(days=_MIN_AGE_DAYS)
    date_to = cutoff.strftime("%Y-%m-%d")

    results = await memory_store.search(
        query=seed_query,
        n_results=_SEARCH_N,
        date_to=date_to,
    )

    # Post-filter: low access count only
    candidates = [
        r for r in results if r.memory.access_count <= _MAX_ACCESS_COUNT
    ]

    if not candidates:
        return None

    if rng.random() >= probability:
        return None

    # Pick the semantically closest (lowest distance)
    candidates.sort(key=lambda r: r.distance)
    return candidates[0].memory
