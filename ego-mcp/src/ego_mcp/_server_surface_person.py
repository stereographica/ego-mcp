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
    """Format a single resonant person reference as natural Japanese text."""
    return (
        f'\n[resonance]\n'
        f'\u305d\u3046\u3070\u308a {person.name} \u306e\u3082\u306e\u3082\u898b\u3048\u305f\u3002'
    )


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

    lines = ["[around me]"]
    for name, date in persons:
        lines.append(f"  - {name} (last seen {date})")
    return "\n".join(lines)
