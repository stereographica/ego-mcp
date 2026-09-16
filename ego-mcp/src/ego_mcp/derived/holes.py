"""Structural holes in the memory graph (D3 S1).

Four shapes of "density without form": a person who recurs across memories that
never connected to anything, a memory returned to often yet linked to nothing, a
tag that runs through many memories no notion holds, and a memory that sits
between two notions that are not related to each other.

The lens measures positions and frequencies only. It never says a hole should be
filled, and it never proposes a link or a notion (D3 D3, T10).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.derived.graph import MemoryGraph, build_memory_graph
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory, Notion

LENS_NAME = "holes"

#: Seven days: topology moves slowly.
HOLES_TTL_HOURS = 168.0

#: Degree-zero memories mentioning one person before the person counts.
HOLES_PERSON_MIN = 5
#: ``access_count`` before an isolated memory counts as worn.
HOLES_WORN_ACCESS_MIN = 3
#: Memories carrying one tag before the uncovered tag counts.
HOLES_TAG_MIN = 6

#: Per-kind caps (D3 D1) and the overall cap.
HOLES_PERSON_LIMIT = 2
HOLES_WORN_LIMIT = 3
HOLES_TAG_LIMIT = 3
HOLES_STRADDLING_LIMIT = 3
HOLES_MAX_ITEMS = 8

#: How many memory ids an item carries as evidence.
HOLES_MEMORY_IDS = 5

HOLES_KIND_ORDER = (
    "person_unlinked",
    "worn_isolated",
    "tag_without_notion",
    "straddling",
)


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


def _epoch(value: str) -> float:
    """Sort key for "newest first": unparsable timestamps sort oldest."""
    parsed = _parse_time(value)
    return 0.0 if parsed is None else parsed.timestamp()


def normalize_tag(tag: Any) -> str:
    """Normalize one tag for comparison: stripped and lowercased.

    Empty or non-string tags normalize to ``""`` and are dropped by callers.
    """
    if not isinstance(tag, str):
        return ""
    return tag.strip().lower()


def _unique(values: Iterable[Any]) -> list[str]:
    """Return the non-empty string values, deduplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values:
        if isinstance(value, str) and value:
            seen.setdefault(value, None)
    return list(seen)


def _notion_adjacency(notions: list[Notion]) -> dict[str, set[str]]:
    """Symmetric ``related_notion_ids`` adjacency over live notions.

    Dead references (to notions that no longer exist) and self-references are
    dropped, as in :func:`ego_mcp.notion._build_notion_adjacency`.
    """
    live = {notion.id for notion in notions if notion.id}
    adjacency: dict[str, set[str]] = {notion_id: set() for notion_id in live}
    for notion in notions:
        if notion.id not in adjacency:
            continue
        for related in notion.related_notion_ids:
            if not isinstance(related, str) or related == notion.id:
                continue
            if related not in adjacency:
                continue
            adjacency[notion.id].add(related)
            adjacency[related].add(notion.id)
    return adjacency


# --- the four kinds ---------------------------------------------------------


def _person_unlinked(
    snapshot: SourceSnapshot, graph: MemoryGraph
) -> list[dict[str, Any]]:
    """People whose memories are many but all of degree zero."""
    by_person: dict[str, list[Memory]] = defaultdict(list)
    for memory in snapshot.memories:
        if graph.degree.get(memory.id, 0) != 0:
            continue
        for person_id in _unique(memory.involved_person_ids):
            by_person[person_id].append(memory)

    ranked: list[tuple[int, str, list[str]]] = []
    for person_id, memories in by_person.items():
        if len(memories) < HOLES_PERSON_MIN:
            continue
        evidence = sorted(
            memories,
            key=lambda memory: (
                -memory.importance,
                -_epoch(memory.timestamp),
                memory.id,
            ),
        )
        ids = [memory.id for memory in evidence[:HOLES_MEMORY_IDS]]
        ranked.append((len(memories), person_id, ids))

    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    return [
        {
            "key": f"holes:person_unlinked:{person_id}",
            "kind": "person_unlinked",
            "person_id": person_id,
            "memory_ids": memory_ids,
            "count": count,
        }
        for count, person_id, memory_ids in ranked[:HOLES_PERSON_LIMIT]
    ]


def _worn_isolated(
    snapshot: SourceSnapshot, graph: MemoryGraph
) -> list[dict[str, Any]]:
    """Memories returned to often that are linked to nothing."""
    candidates = [
        memory
        for memory in snapshot.memories
        if graph.degree.get(memory.id, 0) == 0
        and memory.access_count >= HOLES_WORN_ACCESS_MIN
    ]
    candidates.sort(
        key=lambda memory: (
            -memory.access_count,
            -_epoch(memory.timestamp),
            memory.id,
        )
    )
    return [
        {
            "key": f"holes:worn_isolated:{memory.id}",
            "kind": "worn_isolated",
            "memory_id": memory.id,
            "access_count": memory.access_count,
        }
        for memory in candidates[:HOLES_WORN_LIMIT]
    ]


def _tag_without_notion(
    snapshot: SourceSnapshot, graph: MemoryGraph
) -> list[dict[str, Any]]:
    """Tags carried by many memories that no notion holds."""
    held: set[str] = set()
    for notion in snapshot.notions:
        for raw_tag in notion.tags:
            tag = normalize_tag(raw_tag)
            if tag:
                held.add(tag)

    by_tag: dict[str, list[Memory]] = defaultdict(list)
    for memory in snapshot.memories:
        seen: set[str] = set()
        for raw_tag in memory.tags:
            tag = normalize_tag(raw_tag)
            if not tag or tag in seen:
                continue
            seen.add(tag)
            by_tag[tag].append(memory)

    ranked: list[tuple[int, str, list[str]]] = []
    for tag, memories in by_tag.items():
        if len(memories) < HOLES_TAG_MIN or tag in held:
            continue
        evidence = sorted(
            memories,
            key=lambda memory: (-_epoch(memory.timestamp), memory.id),
        )
        ids = [memory.id for memory in evidence[:HOLES_MEMORY_IDS]]
        ranked.append((len(memories), tag, ids))

    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    return [
        {
            "key": f"holes:tag_without_notion:{tag}",
            "kind": "tag_without_notion",
            "tag": tag,
            "memory_ids": memory_ids,
            "count": count,
        }
        for count, tag, memory_ids in ranked[:HOLES_TAG_LIMIT]
    ]


def _straddling(snapshot: SourceSnapshot, graph: MemoryGraph) -> list[dict[str, Any]]:
    """Memories that stand between notions that are not related to each other."""
    adjacency = _notion_adjacency(snapshot.notions)

    ranked: list[tuple[int, float, str, list[str]]] = []
    for memory in snapshot.memories:
        notion_ids = sorted(graph.notions_of_memory.get(memory.id, set()))
        if len(notion_ids) < 2:
            continue
        pairs = [
            [left, right]
            for index, left in enumerate(notion_ids)
            for right in notion_ids[index + 1 :]
            if right not in adjacency.get(left, set())
        ]
        if not pairs:
            continue
        ranked.append((len(pairs), _epoch(memory.timestamp), memory.id, pairs[0]))

    ranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
    return [
        {
            "key": f"holes:straddling:{memory_id}",
            "kind": "straddling",
            "memory_id": memory_id,
            "notion_ids": notion_ids,
        }
        for _count, _epoch_value, memory_id, notion_ids in ranked[
            :HOLES_STRADDLING_LIMIT
        ]
    ]


_Builder = Callable[[SourceSnapshot, MemoryGraph], list[dict[str, Any]]]

_BUILDERS: dict[str, _Builder] = {
    "person_unlinked": _person_unlinked,
    "worn_isolated": _worn_isolated,
    "tag_without_notion": _tag_without_notion,
    "straddling": _straddling,
}


class HolesLens:
    """Where the memory graph has density but no form (D3)."""

    name = LENS_NAME
    needs_embeddings = False
    ttl_hours = HOLES_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        """Return up to :data:`HOLES_MAX_ITEMS` holes in fixed kind order.

        Private memories are counted like any other: this is a measurement of
        shape, and the shape includes what is not shown to anyone.
        """
        graph = build_memory_graph(snapshot)
        items: list[dict[str, Any]] = []
        for kind in HOLES_KIND_ORDER:
            items.extend(_BUILDERS[kind](snapshot, graph))
        return items[:HOLES_MAX_ITEMS]
