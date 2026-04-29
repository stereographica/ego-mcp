"""Surface handlers for person-related recall features."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ego_mcp.relationship import RelationshipStore
from ego_mcp.types import MemorySearchResult, RecalledPerson

logger = logging.getLogger(__name__)


def _collect_resonant_persons(
    base_results: list[MemorySearchResult],
    relationship_store: RelationshipStore,
    max_persons: int = 3,
) -> list[RecalledPerson]:
    """Collect persons that resonate with recalled memories.

    Scans ``involved_person_ids`` on all base results, ranks by frequency
    (desc) then most-recent timestamp (desc), and returns the top *max_persons*
    as ``RecalledPerson`` instances with ``surface_type="resonant"``.
    """
    # person_id -> (count, most_recent_ts, representative_memory_id)
    counter: dict[str, tuple[int, str, str]] = {}
    for result in base_results:
        for pid in result.memory.involved_person_ids:
            # Canonicalize to prevent alias fragmentation
            resolved = relationship_store.resolve_person(pid)
            pid = resolved if resolved is not None else pid
            prev = counter.get(pid)
            ts = result.memory.timestamp
            if prev is None:
                counter[pid] = (1, ts, result.memory.id)
            else:
                count, prev_ts, prev_mid = prev
                new_ts = ts if ts > prev_ts else prev_ts
                new_mid = result.memory.id if ts > prev_ts else prev_mid
                counter[pid] = (count + 1, new_ts, new_mid)

    if not counter:
        return []

    # frequency desc, most_recent desc
    ranked = sorted(
        counter.items(),
        key=lambda kv: (kv[1][0], kv[1][1]),
        reverse=True,
    )

    persons: list[RecalledPerson] = []
    for pid, (count, ts, mid) in ranked:
        if len(persons) >= max_persons:
            break
        rel = relationship_store.get(pid)
        name = rel.name if rel.name else pid
        persons.append(
            RecalledPerson(
                person_id=pid,
                name=name,
                surface_type="resonant",
                trigger_memory_id=mid,
            )
        )
    return persons


def _format_resonant_person(person: RecalledPerson, now: datetime | None = None) -> str:
    """Format a single resonant person reference as natural English text."""
    return (
        f'\n[resonance]\n'
        f'So, I\'m remembering {person.name} too.'
    )


def _get_active_person_ids(
    relationship_store: RelationshipStore,
    max_persons: int = 2,
) -> list[str]:
    """Return person_ids of most recently interacted persons, sorted descending."""
    try:
        all_models = relationship_store._data
    except AttributeError:
        return []
    if not all_models:
        return []
    active: list[tuple[str, str]] = []
    for pid, raw in all_models.items():
        if not isinstance(raw, dict):
            continue
        last_int = raw.get("last_interaction")
        if not last_int:
            continue
        active.append((pid, last_int))
    if not active:
        return []
    active.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in active[:max_persons]]


def _format_active_persons(
    relationship_store: RelationshipStore,
    max_persons: int = 2,
) -> str:
    """Format 'people currently in mind' from most recent interactions.

    Returns a short section string or empty string if no persons found.
    """
    try:
        all_models = relationship_store._data
    except AttributeError:
        return ""

    if not all_models:
        return ""

    # Filter to only persons with last_interaction, then sort descending
    active: list[tuple[str, str, dict[str, Any]]] = []
    for pid, raw in all_models.items():
        if not isinstance(raw, dict):
            continue
        last_int = raw.get("last_interaction")
        if not last_int:
            continue
        active.append((pid, last_int, raw))

    if not active:
        return ""

    active.sort(key=lambda x: x[1], reverse=True)

    persons: list[tuple[str, str]] = []
    for pid, last_int, raw in active:
        if len(persons) >= max_persons:
            break
        name = raw.get("name") or pid
        persons.append((name, last_int[:10] if isinstance(last_int, str) else str(last_int)))

    if not persons:
        return ""

    names = [name for name, _ in persons]
    if len(names) == 1:
        return f"\n{names[0]} surfaced on their own."
    elif len(names) == 2:
        return f"\n{names[0]} and {names[1]} surfaced on their own."
    else:
        last = names[-1]
        others = ", ".join(names[:-1])
        return f"\n{others} and {last} surfaced on their own."
