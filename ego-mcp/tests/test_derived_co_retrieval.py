"""Tests for derived/co_retrieval.py (P1 S2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from ego_mcp.derived.co_retrieval import (
    CO_RETRIEVAL_MAX_IDS_PER_RECALL,
    CO_RETRIEVAL_MAX_LINKED,
    CO_RETRIEVAL_MAX_UNLINKED,
    CO_RETRIEVAL_MIN_WEIGHT,
    CoRetrievalLens,
    co_retrieval_key,
)
from ego_mcp.derived.lenses import Lens
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import LinkType, Memory, MemoryLink

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _memory(memory_id: str, *, links: list[str] | None = None) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=NOW.isoformat(),
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED)
            for target in (links or [])
        ],
    )


def _unit(dimension: int, axis: int) -> np.ndarray:
    vector = np.zeros(dimension, dtype=np.float32)
    vector[axis] = 1.0
    return vector


def _snapshot(
    memories: list[Memory],
    co_retrievals: list[tuple[datetime, list[str]]],
    *,
    embeddings: dict[str, np.ndarray] | None = None,
    now: datetime = NOW,
) -> SourceSnapshot:
    return SourceSnapshot(
        now=now,
        memories=memories,
        embeddings=embeddings,
        notions=[],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=co_retrievals,
    )


def _recalls(ids: list[str], times: int, *, age_days: int = 0) -> list[
    tuple[datetime, list[str]]
]:
    at = NOW - timedelta(days=age_days)
    return [(at, list(ids)) for _ in range(times)]


def _items(snapshot: SourceSnapshot) -> list[dict[str, Any]]:
    return CoRetrievalLens().compute(snapshot)


def _by_key(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["key"]): item for item in items}


# --- lens identity ----------------------------------------------------------


def test_lens_attributes() -> None:
    lens: Lens = CoRetrievalLens()  # structural conformance is checked by mypy
    assert lens.name == "coretrieval"
    assert lens.needs_embeddings is True
    assert lens.ttl_hours == 48.0


def test_empty_log_yields_no_items() -> None:
    assert _items(_snapshot([_memory("a"), _memory("b")], [])) == []


# --- weight -----------------------------------------------------------------


def test_weight_below_threshold_is_dropped() -> None:
    memories = [_memory("a"), _memory("b")]
    items = _items(_snapshot(memories, _recalls(["a", "b"], 2)))
    assert items == []


def test_weight_counts_one_per_recall() -> None:
    memories = [_memory("a"), _memory("b")]
    items = _items(_snapshot(memories, _recalls(["a", "b"], 3)))
    assert len(items) == 1
    assert items[0]["weight"] == 3.0
    assert items[0]["weight"] >= CO_RETRIEVAL_MIN_WEIGHT


def test_duplicate_ids_in_one_recall_count_once() -> None:
    memories = [_memory("a"), _memory("b")]
    log = _recalls(["a", "b", "a", "b", "a"], 3)
    items = _items(_snapshot(memories, log))
    assert len(items) == 1
    assert items[0]["weight"] == 3.0


def test_weight_decays_with_a_thirty_day_half_life() -> None:
    memories = [_memory("a"), _memory("b")]
    # Six recalls a month ago decay to 0.5 each -> 3.0, still above 2.5.
    items = _items(_snapshot(memories, _recalls(["a", "b"], 6, age_days=30)))
    assert len(items) == 1
    assert items[0]["weight"] == 3.0

    # Four decay to 2.0, below the 2.5 threshold.
    faded = _items(_snapshot(memories, _recalls(["a", "b"], 4, age_days=30)))
    assert faded == []


def test_future_timestamps_do_not_amplify_weight() -> None:
    memories = [_memory("a"), _memory("b")]
    log = _recalls(["a", "b"], 3, age_days=-90)
    items = _items(_snapshot(memories, log))
    assert len(items) == 1
    assert items[0]["weight"] == 3.0


def test_naive_log_timestamps_are_aligned_to_the_snapshot() -> None:
    memories = [_memory("a"), _memory("b")]
    naive = (NOW - timedelta(days=30)).replace(tzinfo=None)
    log = [(naive, ["a", "b"]) for _ in range(6)]
    items = _items(_snapshot(memories, log))
    assert len(items) == 1
    assert items[0]["weight"] == 3.0


# --- membership -------------------------------------------------------------


def test_deleted_memories_are_dropped_from_pairs() -> None:
    memories = [_memory("a"), _memory("b")]
    items = _items(_snapshot(memories, _recalls(["a", "gone", "b"], 3)))
    assert [item["memory_ids"] for item in items] == [["a", "b"]]


def test_recall_left_with_one_existing_id_forms_no_pair() -> None:
    memories = [_memory("a")]
    assert _items(_snapshot(memories, _recalls(["a", "gone"], 5))) == []


def test_recall_wider_than_the_cap_uses_only_the_first_ids() -> None:
    ids = [f"m{index:02d}" for index in range(CO_RETRIEVAL_MAX_IDS_PER_RECALL + 2)]
    memories = [_memory(memory_id) for memory_id in ids]
    last = ids[-1]
    log = _recalls(ids, 3) + _recalls([ids[0], last], 4)
    items = _by_key(_items(_snapshot(memories, log)))

    # Only the narrow recalls count: the wide ones dropped the eleventh id.
    assert items[co_retrieval_key(ids[0], last)]["weight"] == 4.0
    involved = {
        memory_id for item in items.values() for memory_id in item["memory_ids"]
    }
    assert ids[CO_RETRIEVAL_MAX_IDS_PER_RECALL] not in involved


def test_cap_applies_after_dropping_deleted_ids() -> None:
    # Eleven ids of which the second no longer exists: the eleventh still fits
    # in the cap window because deleted ids are removed before the cap.
    ids = [f"m{index:02d}" for index in range(11)]
    memories = [_memory(memory_id) for memory_id in ids if memory_id != "m01"]
    log = _recalls(ids, 3) + _recalls(["m00", "m10"], 4)
    items = _by_key(_items(_snapshot(memories, log)))
    # 3 from the wide recalls plus 4 from the narrow ones; it would be 4 alone
    # if the cap had counted the deleted id and pushed m10 out.
    assert items["coretrieval:m00:m10"]["weight"] == 7.0
    assert not any("m01" in item["memory_ids"] for item in items.values())


# --- distance ---------------------------------------------------------------


def test_close_pairs_are_dropped_when_both_embeddings_exist() -> None:
    memories = [_memory("a"), _memory("b")]
    shared = _unit(4, 0)
    embeddings = {"a": shared, "b": shared.copy()}
    items = _items(
        _snapshot(memories, _recalls(["a", "b"], 3), embeddings=embeddings)
    )
    assert items == []


def test_distant_pairs_carry_their_distance() -> None:
    memories = [_memory("a"), _memory("b")]
    embeddings = {"a": _unit(4, 0), "b": _unit(4, 1)}
    items = _items(
        _snapshot(memories, _recalls(["a", "b"], 3), embeddings=embeddings)
    )
    assert len(items) == 1
    assert items[0]["distance"] == 1.0


def test_distance_condition_is_skipped_when_an_embedding_is_missing() -> None:
    memories = [_memory("a"), _memory("b")]
    embeddings = {"a": _unit(4, 0)}
    items = _items(
        _snapshot(memories, _recalls(["a", "b"], 3), embeddings=embeddings)
    )
    assert len(items) == 1
    assert items[0]["distance"] is None


def test_distance_is_null_when_the_snapshot_has_no_embeddings() -> None:
    memories = [_memory("a"), _memory("b")]
    items = _items(_snapshot(memories, _recalls(["a", "b"], 3)))
    assert items[0]["distance"] is None


# --- kind -------------------------------------------------------------------


def test_linked_and_unlinked_pairs_are_split() -> None:
    memories = [_memory("a", links=["b"]), _memory("b"), _memory("c")]
    log = _recalls(["a", "b"], 3) + _recalls(["a", "c"], 3)
    items = _by_key(_items(_snapshot(memories, log)))
    assert items["coretrieval:a:b"]["kind"] == "linked"
    assert items["coretrieval:a:c"]["kind"] == "unlinked"


def test_a_reverse_link_also_counts_as_linked() -> None:
    memories = [_memory("a"), _memory("b", links=["a"])]
    items = _items(_snapshot(memories, _recalls(["b", "a"], 3)))
    assert items[0]["kind"] == "linked"


def test_unlinked_items_come_before_linked_items() -> None:
    memories = [_memory("a", links=["b"]), _memory("b"), _memory("c")]
    log = _recalls(["a", "b"], 9) + _recalls(["a", "c"], 3)
    items = _items(_snapshot(memories, log))
    assert [item["kind"] for item in items] == ["unlinked", "linked"]


# --- keys -------------------------------------------------------------------


def test_key_is_normalized_to_id_order() -> None:
    memories = [_memory("zeta"), _memory("alpha")]
    items = _items(_snapshot(memories, _recalls(["zeta", "alpha"], 3)))
    assert items[0]["key"] == "coretrieval:alpha:zeta"
    assert items[0]["memory_ids"] == ["alpha", "zeta"]


def test_key_is_stable_across_recall_orderings() -> None:
    memories = [_memory("zeta"), _memory("alpha")]
    log = _recalls(["zeta", "alpha"], 2) + _recalls(["alpha", "zeta"], 2)
    items = _items(_snapshot(memories, log))
    assert len(items) == 1
    assert items[0]["key"] == co_retrieval_key("zeta", "alpha")


def test_items_carry_no_memory_text() -> None:
    memories = [_memory("a"), _memory("b")]
    items = _items(_snapshot(memories, _recalls(["a", "b"], 3)))
    assert set(items[0]) == {"key", "memory_ids", "weight", "distance", "kind"}


# --- limits -----------------------------------------------------------------


def test_unlinked_items_are_capped_by_weight() -> None:
    ids = ["m0", "m1", "m2", "m3"]
    memories = [_memory(memory_id) for memory_id in ids]
    # Six pairs; give m0-m1 the heaviest weight so ordering is observable.
    log = _recalls(ids, 3) + _recalls(["m0", "m1"], 4)
    items = _items(_snapshot(memories, log))
    assert len(items) == CO_RETRIEVAL_MAX_UNLINKED
    assert items[0]["memory_ids"] == ["m0", "m1"]
    weights = [item["weight"] for item in items]
    assert weights == sorted(weights, reverse=True)


def test_linked_items_are_capped() -> None:
    ids = [f"m{index}" for index in range(7)]  # 21 pairs
    memories = [
        _memory(memory_id, links=[other for other in ids if other != memory_id])
        for memory_id in ids
    ]
    items = _items(_snapshot(memories, _recalls(ids, 3)))
    assert len(items) == CO_RETRIEVAL_MAX_LINKED
    assert {item["kind"] for item in items} == {"linked"}
