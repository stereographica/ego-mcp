"""Tests for derived/holes.py (D3 S1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ego_mcp.derived.holes import (
    HOLES_KIND_ORDER,
    HOLES_MAX_ITEMS,
    HOLES_PERSON_MIN,
    HOLES_TAG_MIN,
    HOLES_TTL_HOURS,
    HOLES_WORN_ACCESS_MIN,
    HolesLens,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import LinkType, Memory, MemoryLink, Notion

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _memory(
    memory_id: str,
    *,
    links: list[str] | None = None,
    tags: list[str] | None = None,
    persons: list[str] | None = None,
    access_count: int = 0,
    importance: int = 3,
    is_private: bool = False,
    age_days: float = 0.0,
) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=(NOW - timedelta(days=age_days)).isoformat(),
        importance=importance,
        tags=list(tags or []),
        involved_person_ids=list(persons or []),
        access_count=access_count,
        is_private=is_private,
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED)
            for target in (links or [])
        ],
    )


def _notion(
    notion_id: str,
    *,
    tags: list[str] | None = None,
    sources: list[str] | None = None,
    related: list[str] | None = None,
) -> Notion:
    return Notion(
        id=notion_id,
        label=f"label {notion_id}",
        tags=list(tags or []),
        source_memory_ids=list(sources or []),
        related_notion_ids=list(related or []),
        created=NOW.isoformat(),
    )


def _snapshot(
    memories: list[Memory], notions: list[Notion] | None = None
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=None,
        notions=notions or [],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


def _compute(
    memories: list[Memory], notions: list[Notion] | None = None
) -> list[dict[str, Any]]:
    return HolesLens().compute(_snapshot(memories, notions))


def _of_kind(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [item for item in items if item["kind"] == kind]


# --- lens identity ----------------------------------------------------------


def test_lens_identity() -> None:
    lens = HolesLens()
    assert lens.name == "holes"
    assert lens.needs_embeddings is False
    assert lens.ttl_hours == HOLES_TTL_HOURS == 168.0
    assert HOLES_KIND_ORDER == (
        "person_unlinked",
        "worn_isolated",
        "tag_without_notion",
        "straddling",
    )


def test_empty_snapshot_has_no_items() -> None:
    assert _compute([]) == []


# --- person_unlinked --------------------------------------------------------


def test_person_unlinked_threshold_boundary() -> None:
    below = [_memory(f"m{i}", persons=["p1"]) for i in range(HOLES_PERSON_MIN - 1)]
    assert _of_kind(_compute(below), "person_unlinked") == []

    at = [_memory(f"m{i}", persons=["p1"]) for i in range(HOLES_PERSON_MIN)]
    items = _of_kind(_compute(at), "person_unlinked")
    assert len(items) == 1
    assert items[0]["person_id"] == "p1"
    assert items[0]["count"] == HOLES_PERSON_MIN
    assert items[0]["key"] == "holes:person_unlinked:p1"


def test_person_unlinked_ignores_linked_memories() -> None:
    memories = [_memory(f"m{i}", persons=["p1"]) for i in range(HOLES_PERSON_MIN)]
    # One of them gains a link, dropping the person below the threshold.
    memories.append(_memory("other"))
    memories[0].linked_ids = [
        MemoryLink(target_id="other", link_type=LinkType.RELATED)
    ]
    assert _of_kind(_compute(memories), "person_unlinked") == []


def test_person_unlinked_limits_to_two_people_by_count() -> None:
    memories: list[Memory] = []
    for person, total in (("p_small", 5), ("p_big", 7), ("p_mid", 6)):
        memories.extend(
            _memory(f"{person}_{i}", persons=[person]) for i in range(total)
        )
    items = _of_kind(_compute(memories), "person_unlinked")
    assert [item["person_id"] for item in items] == ["p_big", "p_mid"]
    assert [item["count"] for item in items] == [7, 6]


def test_person_unlinked_evidence_is_importance_first_and_capped() -> None:
    memories = [
        _memory(f"m{i}", persons=["p1"], importance=i, age_days=i) for i in range(1, 8)
    ]
    items = _of_kind(_compute(memories), "person_unlinked")
    assert items[0]["memory_ids"] == ["m7", "m6", "m5", "m4", "m3"]
    assert items[0]["count"] == 7


def test_person_unlinked_counts_private_memories() -> None:
    memories = [
        _memory(f"m{i}", persons=["p1"], is_private=i % 2 == 0)
        for i in range(HOLES_PERSON_MIN)
    ]
    items = _of_kind(_compute(memories), "person_unlinked")
    assert items[0]["count"] == HOLES_PERSON_MIN


# --- worn_isolated ----------------------------------------------------------


def test_worn_isolated_access_boundary() -> None:
    below = _memory("m1", access_count=HOLES_WORN_ACCESS_MIN - 1)
    assert _of_kind(_compute([below]), "worn_isolated") == []

    at = _memory("m1", access_count=HOLES_WORN_ACCESS_MIN)
    items = _of_kind(_compute([at]), "worn_isolated")
    assert items == [
        {
            "key": "holes:worn_isolated:m1",
            "kind": "worn_isolated",
            "memory_id": "m1",
            "access_count": HOLES_WORN_ACCESS_MIN,
        }
    ]


def test_worn_isolated_requires_degree_zero() -> None:
    memories = [
        _memory("m1", access_count=9, links=["m2"]),
        _memory("m2", access_count=9),
    ]
    items = _of_kind(_compute(memories), "worn_isolated")
    assert items == []


def test_worn_isolated_limit_and_order() -> None:
    memories = [_memory(f"m{i}", access_count=i) for i in range(3, 9)]
    items = _of_kind(_compute(memories), "worn_isolated")
    assert [item["memory_id"] for item in items] == ["m8", "m7", "m6"]
    assert [item["access_count"] for item in items] == [8, 7, 6]


def test_worn_isolated_counts_private_memories() -> None:
    memories = [_memory("secret", access_count=5, is_private=True)]
    items = _of_kind(_compute(memories), "worn_isolated")
    assert [item["memory_id"] for item in items] == ["secret"]


# --- tag_without_notion -----------------------------------------------------


def test_tag_without_notion_threshold_boundary() -> None:
    below = [_memory(f"m{i}", tags=["rain"]) for i in range(HOLES_TAG_MIN - 1)]
    assert _of_kind(_compute(below), "tag_without_notion") == []

    at = [_memory(f"m{i}", tags=["rain"]) for i in range(HOLES_TAG_MIN)]
    items = _of_kind(_compute(at), "tag_without_notion")
    assert len(items) == 1
    assert items[0]["tag"] == "rain"
    assert items[0]["count"] == HOLES_TAG_MIN
    assert items[0]["key"] == "holes:tag_without_notion:rain"


def test_tag_without_notion_suppressed_when_a_notion_holds_the_tag() -> None:
    memories = [_memory(f"m{i}", tags=["rain"]) for i in range(HOLES_TAG_MIN)]
    notions = [_notion("n1", tags=["rain"])]
    assert _of_kind(_compute(memories, notions), "tag_without_notion") == []


def test_tag_without_notion_normalizes_case_and_whitespace() -> None:
    memories = [
        _memory("m0", tags=["Rain"]),
        _memory("m1", tags=[" rain "]),
        _memory("m2", tags=["RAIN"]),
        _memory("m3", tags=["rain"]),
        _memory("m4", tags=["Rain "]),
        _memory("m5", tags=["rain"]),
    ]
    items = _of_kind(_compute(memories), "tag_without_notion")
    assert [item["tag"] for item in items] == ["rain"]
    assert items[0]["count"] == HOLES_TAG_MIN

    # A notion holding the tag in another spelling covers it too.
    notions = [_notion("n1", tags=[" RAIN"])]
    assert _of_kind(_compute(memories, notions), "tag_without_notion") == []


def test_tag_without_notion_evidence_is_newest_first_and_capped() -> None:
    memories = [
        _memory(f"m{i}", tags=["rain"], age_days=i) for i in range(HOLES_TAG_MIN + 1)
    ]
    items = _of_kind(_compute(memories), "tag_without_notion")
    assert items[0]["memory_ids"] == ["m0", "m1", "m2", "m3", "m4"]
    assert items[0]["count"] == HOLES_TAG_MIN + 1


def test_tag_without_notion_limits_to_three_tags_by_count() -> None:
    memories: list[Memory] = []
    for tag, total in (("a", 6), ("b", 9), ("c", 8), ("d", 7)):
        memories.extend(_memory(f"{tag}{i}", tags=[tag]) for i in range(total))
    items = _of_kind(_compute(memories), "tag_without_notion")
    assert [item["tag"] for item in items] == ["b", "c", "d"]


# --- straddling -------------------------------------------------------------


def test_straddling_detects_unrelated_notion_pair() -> None:
    memories = [_memory("m1")]
    notions = [_notion("n_b", sources=["m1"]), _notion("n_a", sources=["m1"])]
    items = _of_kind(_compute(memories, notions), "straddling")
    assert items == [
        {
            "key": "holes:straddling:m1",
            "kind": "straddling",
            "memory_id": "m1",
            "notion_ids": ["n_a", "n_b"],
        }
    ]


def test_straddling_skipped_when_notions_are_related() -> None:
    memories = [_memory("m1")]
    notions = [
        _notion("n_a", sources=["m1"], related=["n_b"]),
        _notion("n_b", sources=["m1"]),
    ]
    assert _of_kind(_compute(memories, notions), "straddling") == []


def test_straddling_needs_two_notions() -> None:
    memories = [_memory("m1")]
    notions = [_notion("n_a", sources=["m1"])]
    assert _of_kind(_compute(memories, notions), "straddling") == []


def test_straddling_orders_by_disconnected_pair_count_and_limits_to_three() -> None:
    memories = [_memory(f"m{i}") for i in range(1, 5)]
    notions = [
        _notion("n1", sources=["m1", "m2", "m3", "m4"]),
        _notion("n2", sources=["m1", "m2", "m3", "m4"]),
        # m1 belongs to three mutually unrelated notions: three broken pairs.
        _notion("n3", sources=["m1"]),
    ]
    items = _of_kind(_compute(memories, notions), "straddling")
    assert [item["memory_id"] for item in items] == ["m1", "m2", "m3"]
    assert items[0]["notion_ids"] == ["n1", "n2"]


# --- overall shape ----------------------------------------------------------


def _crowded_snapshot() -> tuple[list[Memory], list[Notion]]:
    memories: list[Memory] = []
    for person in ("p_a", "p_b", "p_c"):
        memories.extend(
            _memory(f"{person}_{i}", persons=[person], access_count=9)
            for i in range(6)
        )
    for tag, total in (("a", 6), ("b", 9), ("c", 8), ("d", 7)):
        memories.extend(_memory(f"{tag}{i}", tags=[tag]) for i in range(total))
    straddlers = [_memory(f"s{i}") for i in range(4)]
    memories.extend(straddlers)
    notions = [
        _notion("n1", sources=[memory.id for memory in straddlers]),
        _notion("n2", sources=[memory.id for memory in straddlers]),
    ]
    return memories, notions


def test_total_cap_and_kind_order() -> None:
    memories, notions = _crowded_snapshot()
    items = _compute(memories, notions)
    assert len(items) == HOLES_MAX_ITEMS
    kinds = [item["kind"] for item in items]
    assert kinds == [
        "person_unlinked",
        "person_unlinked",
        "worn_isolated",
        "worn_isolated",
        "worn_isolated",
        "tag_without_notion",
        "tag_without_notion",
        "tag_without_notion",
    ]
    # straddling exists but is cut by the overall cap, which is kind-ordered.
    assert "straddling" not in kinds


def test_keys_are_stable_across_runs() -> None:
    memories, notions = _crowded_snapshot()
    first = _compute(memories, notions)
    second = _compute(list(reversed(memories)), list(reversed(notions)))
    assert [item["key"] for item in first] == [item["key"] for item in second]
    assert first == second


def test_every_item_carries_a_string_key() -> None:
    memories, notions = _crowded_snapshot()
    for item in _compute(memories, notions):
        assert isinstance(item["key"], str)
        assert item["key"].startswith(f"holes:{item['kind']}:")
