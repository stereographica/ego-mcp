"""Tests for derived/drift.py (D4 S1) — the lens half of the notion drift design."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from ego_mcp.derived.drift import (
    DRIFT_DISPERSION_FLOOR,
    DRIFT_MAX_DRIFT_ITEMS,
    DRIFT_MAX_STALE_ITEMS,
    DRIFT_MIN_DISTANCE,
    DRIFT_MIN_HALF,
    DRIFT_MIN_SOURCES,
    DRIFT_RATIO_MIN,
    DRIFT_STALE_DAYS,
    DRIFT_TTL_HOURS,
    LENS_NAME,
    DriftLens,
    _dispersion,
    _split_halves,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory, Notion

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)
TODAY = "2026-09-16"

#: Orthogonal halves: the most unambiguous drift there is.
WIDE_ANGLE = math.pi / 2


# --- fixtures ---------------------------------------------------------------


def _unit(angle: float) -> np.ndarray:
    """A 2-D unit vector at ``angle`` radians."""
    return np.array([math.cos(angle), math.sin(angle)], dtype=np.float32)


def _fan(center: float, spread: float) -> list[float]:
    """Three angles symmetric around ``center`` — centroid lands exactly on it."""
    return [center - spread, center, center + spread]


def _angle_for_distance(distance: float) -> float:
    """The angle between two unit vectors whose cosine distance is ``distance``."""
    return math.acos(1.0 - distance)


def _spread_for_dispersion(dispersion: float) -> float:
    """The :func:`_fan` spread that makes a half's dispersion ``dispersion``.

    A fan of three has mean distance ``2 * (1 - cos(spread)) / 3`` from its own
    centroid, so ``cos(spread) = 1 - 1.5 * dispersion``.
    """
    return math.acos(1.0 - 1.5 * dispersion)


def _memory(memory_id: str, *, days_ago: float) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=(NOW - timedelta(days=days_ago)).isoformat(),
    )


def _notion(
    notion_id: str,
    source_memory_ids: list[str],
    *,
    confidence: float = 0.5,
    reinforcement_count: int = 0,
    last_reinforced: str = "",
) -> Notion:
    return Notion(
        id=notion_id,
        label=f"label of {notion_id}",
        confidence=confidence,
        source_memory_ids=source_memory_ids,
        reinforcement_count=reinforcement_count,
        created=(NOW - timedelta(days=500)).isoformat(),
        last_reinforced=last_reinforced,
    )


def _conviction(notion_id: str, *, days_since_reinforced: float) -> Notion:
    return _notion(
        notion_id,
        [],
        confidence=0.8,
        reinforcement_count=5,
        last_reinforced=(NOW - timedelta(days=days_since_reinforced)).isoformat(),
    )


def _snapshot(
    memories: list[Memory],
    notions: list[Notion],
    embeddings: dict[str, np.ndarray] | None,
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=embeddings,
        notions=notions,
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


def _sources(
    notion_id: str, angles: list[float], *, newest_days_ago: float = 10.0
) -> tuple[list[Memory], dict[str, np.ndarray], list[str]]:
    """Build one notion's source memories, oldest first, 10 days apart."""
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    ids: list[str] = []
    count = len(angles)
    for index, angle in enumerate(angles):
        memory_id = f"{notion_id}_m{index}"
        days_ago = newest_days_ago + (count - 1 - index) * 10
        memories.append(_memory(memory_id, days_ago=days_ago))
        embeddings[memory_id] = _unit(angle)
        ids.append(memory_id)
    return memories, embeddings, ids


def _one_notion_snapshot(
    old_angles: list[float],
    new_angles: list[float],
    *,
    notion_id: str = "notion_a",
) -> SourceSnapshot:
    memories, embeddings, ids = _sources(notion_id, [*old_angles, *new_angles])
    return _snapshot(memories, [_notion(notion_id, ids)], embeddings)


def _compute(snapshot: SourceSnapshot) -> list[dict[str, Any]]:
    return DriftLens().compute(snapshot)


# --- lens identity ----------------------------------------------------------


def test_lens_identity() -> None:
    lens = DriftLens()
    assert lens.name == LENS_NAME == "drift"
    assert lens.needs_embeddings is True
    assert lens.ttl_hours == DRIFT_TTL_HOURS == 168.0


def test_constants_match_the_design() -> None:
    assert DRIFT_MIN_SOURCES == 6
    assert DRIFT_MIN_HALF == 3
    assert DRIFT_MIN_DISTANCE == 0.20
    assert DRIFT_RATIO_MIN == 1.5
    assert DRIFT_DISPERSION_FLOOR == 0.05
    assert DRIFT_STALE_DAYS == 45
    assert DRIFT_MAX_DRIFT_ITEMS == 3
    assert DRIFT_MAX_STALE_ITEMS == 2


# --- _split_halves ----------------------------------------------------------


def _numbered(count: int) -> list[Memory]:
    return [_memory(f"m{index}", days_ago=count - index) for index in range(count)]


def test_split_halves_even_count_is_balanced() -> None:
    older, newer = _split_halves(_numbered(6))
    assert [memory.id for memory in older] == ["m0", "m1", "m2"]
    assert [memory.id for memory in newer] == ["m3", "m4", "m5"]


def test_split_halves_odd_count_gives_the_extra_to_the_newer_half() -> None:
    older, newer = _split_halves(_numbered(7))
    assert [memory.id for memory in older] == ["m0", "m1", "m2"]
    assert [memory.id for memory in newer] == ["m3", "m4", "m5", "m6"]


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, (0, 0)), (1, (0, 1)), (2, (1, 1)), (5, (2, 3)), (9, (4, 5)), (10, (5, 5))],
)
def test_split_halves_sizes(count: int, expected: tuple[int, int]) -> None:
    older, newer = _split_halves(_numbered(count))
    assert (len(older), len(newer)) == expected


def test_split_halves_does_not_alias_the_input() -> None:
    memories = _numbered(4)
    older, newer = _split_halves(memories)
    older.append(memories[0])
    assert len(memories) == 4
    assert len(newer) == 2


# --- _dispersion ------------------------------------------------------------


def test_dispersion_of_identical_vectors_is_zero() -> None:
    vector = _unit(0.3)
    assert _dispersion([vector, vector, vector], vector) == pytest.approx(0.0, abs=1e-6)


def test_dispersion_of_an_empty_set_is_zero() -> None:
    assert _dispersion([], _unit(0.0)) == 0.0


def test_dispersion_is_the_mean_cosine_distance_from_the_centre() -> None:
    center = _unit(0.0)
    vectors = [_unit(0.0), _unit(math.pi / 2), _unit(math.pi)]
    # 0 + 1 + 2, over three vectors.
    assert _dispersion(vectors, center) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("target", [0.05, 0.12, 0.2, 0.4])
def test_spread_for_dispersion_helper_is_self_consistent(target: float) -> None:
    """The fixture the threshold tests lean on must really produce ``target``."""
    spread = _spread_for_dispersion(target)
    vectors = [_unit(angle) for angle in _fan(0.0, spread)]
    assert _dispersion(vectors, _unit(0.0)) == pytest.approx(target, abs=1e-5)


# --- drift detection --------------------------------------------------------


def test_clearly_separated_halves_produce_one_drift_item() -> None:
    items = _compute(
        _one_notion_snapshot(_fan(0.0, 0.02), _fan(WIDE_ANGLE, 0.02))
    )
    assert len(items) == 1
    item = items[0]
    assert item["key"] == f"drift:notion_a:{TODAY}"
    assert item["kind"] == "drift"
    assert item["notion_id"] == "notion_a"
    assert item["distance"] == pytest.approx(1.0, abs=1e-3)
    # The fan is tight, so the dispersion floor sets the ratio: 1.0 / 0.05.
    assert item["ratio"] == pytest.approx(20.0, abs=0.2)


def test_halves_that_did_not_move_produce_nothing() -> None:
    assert _compute(_one_notion_snapshot(_fan(0.0, 0.3), _fan(0.0, 0.3))) == []


def test_item_carries_no_memory_text() -> None:
    items = _compute(_one_notion_snapshot(_fan(0.0, 0.02), _fan(WIDE_ANGLE, 0.02)))
    assert set(items[0]) == {
        "key",
        "kind",
        "notion_id",
        "distance",
        "ratio",
        "newest_source_memory_id",
    }


# --- threshold boundaries ---------------------------------------------------


@pytest.mark.parametrize(
    ("distance", "expected_items"),
    [(0.195, 0), (0.205, 1), (0.30, 1)],
)
def test_distance_threshold_boundary(distance: float, expected_items: int) -> None:
    # Zero spread inside each half, so the dispersion floor (0.05) decides the
    # ratio and only the distance can fail the test.
    angle = _angle_for_distance(distance)
    items = _compute(_one_notion_snapshot([0.0] * 3, [angle] * 3))
    assert len(items) == expected_items


@pytest.mark.parametrize(
    ("dispersion", "expected_items"),
    [(0.19, 1), (0.21, 0)],
)
def test_ratio_threshold_boundary(dispersion: float, expected_items: int) -> None:
    # distance is pinned at 0.30, so ratio = 0.30 / dispersion crosses 1.5
    # exactly at dispersion = 0.20.
    angle = _angle_for_distance(0.30)
    spread = _spread_for_dispersion(dispersion)
    items = _compute(
        _one_notion_snapshot(_fan(0.0, spread), _fan(angle, spread))
    )
    assert len(items) == expected_items


def test_dispersion_floor_keeps_a_tight_cluster_from_exploding_the_ratio() -> None:
    # Identical vectors inside each half: real dispersion is 0, so the ratio is
    # distance / 0.05 rather than infinity.
    angle = _angle_for_distance(0.25)
    items = _compute(_one_notion_snapshot([0.0] * 3, [angle] * 3))
    assert items[0]["ratio"] == pytest.approx(5.0, abs=0.05)


def test_a_wide_spread_beats_a_real_move() -> None:
    # distance 0.30 but each half is spread by 0.40 -> ratio 0.75.
    angle = _angle_for_distance(0.30)
    spread = _spread_for_dispersion(0.40)
    assert _compute(_one_notion_snapshot(_fan(0.0, spread), _fan(angle, spread))) == []


# --- source counting --------------------------------------------------------


def test_five_sources_are_too_few_and_six_are_enough() -> None:
    angle = WIDE_ANGLE
    assert _compute(_one_notion_snapshot([0.0] * 2, [angle] * 3)) == []
    assert len(_compute(_one_notion_snapshot([0.0] * 3, [angle] * 3))) == 1


def test_deleted_source_ids_do_not_count() -> None:
    memories, embeddings, ids = _sources(
        "notion_a", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    notion = _notion("notion_a", [*ids, "ghost_1", "ghost_2"])
    # Eight ids, but only six memories exist: still exactly at the minimum.
    assert len(_compute(_snapshot(memories, [notion], embeddings))) == 1

    # Drop one real memory and the notion falls below the minimum.
    survivors = [memory for memory in memories if memory.id != ids[0]]
    assert _compute(_snapshot(survivors, [notion], embeddings)) == []


def test_sources_without_an_embedding_do_not_count() -> None:
    memories, embeddings, ids = _sources(
        "notion_a", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    notion = _notion("notion_a", ids)
    assert len(_compute(_snapshot(memories, [notion], embeddings))) == 1

    # The snapshot's dimension filter dropped one vector.
    thinned = {
        memory_id: vector
        for memory_id, vector in embeddings.items()
        if memory_id != ids[5]
    }
    assert _compute(_snapshot(memories, [notion], thinned)) == []


def test_repeated_source_ids_count_once() -> None:
    memories, embeddings, ids = _sources(
        "notion_a", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE]
    )
    notion = _notion("notion_a", [*ids, ids[0], ids[1]])
    assert _compute(_snapshot(memories, [notion], embeddings)) == []


def test_sources_with_an_unparsable_timestamp_do_not_count() -> None:
    memories, embeddings, ids = _sources(
        "notion_a", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    memories[0].timestamp = "not-a-timestamp"
    assert _compute(_snapshot(memories, [_notion("notion_a", ids)], embeddings)) == []


def test_missing_embeddings_block_disables_drift_but_not_stale() -> None:
    memories, _embeddings, ids = _sources(
        "notion_a", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    stale = _conviction("notion_b", days_since_reinforced=90)
    items = _compute(_snapshot(memories, [_notion("notion_a", ids), stale], None))
    assert [item["notion_id"] for item in items] == ["notion_b"]


# --- newest_source_memory_id ------------------------------------------------


def test_newest_source_memory_id_is_the_newer_half_member_nearest_its_centroid() -> None:
    spread = 0.5
    snapshot = _one_notion_snapshot(_fan(0.0, 0.02), _fan(WIDE_ANGLE, spread))
    items = _compute(snapshot)
    # Sources are laid out oldest first: m3, m4, m5 are the newer half and m4
    # sits exactly on that half's centroid.
    assert items[0]["newest_source_memory_id"] == "notion_a_m4"


def test_newest_source_memory_id_breaks_ties_towards_the_newest_memory() -> None:
    # Seven sources: the odd one goes to the newer half, whose four vectors are
    # identical, so every one of them sits on the centroid.
    snapshot = _one_notion_snapshot([0.0] * 3, [WIDE_ANGLE] * 4)
    items = _compute(snapshot)
    assert items[0]["newest_source_memory_id"] == "notion_a_m6"


# --- stale convictions ------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected_items"),
    [(44.9, 0), (45.0, 1), (45.5, 1), (200.0, 1)],
)
def test_stale_conviction_day_boundary(days: float, expected_items: int) -> None:
    items = _compute(_snapshot([], [_conviction("notion_a", days_since_reinforced=days)], {}))
    assert len(items) == expected_items


def test_stale_conviction_item_shape() -> None:
    items = _compute(
        _snapshot([], [_conviction("notion_a", days_since_reinforced=60.7)], {})
    )
    assert items == [
        {
            "key": f"drift:notion_a:{TODAY}:stale",
            "kind": "stale_conviction",
            "notion_id": "notion_a",
            "days_since_reinforced": 60,
        }
    ]


@pytest.mark.parametrize(
    ("reinforcement_count", "confidence", "expected_items"),
    [(4, 0.8, 0), (5, 0.69, 0), (5, 0.7, 1), (9, 0.9, 1)],
)
def test_stale_only_applies_to_convictions(
    reinforcement_count: int, confidence: float, expected_items: int
) -> None:
    notion = _notion(
        "notion_a",
        [],
        confidence=confidence,
        reinforcement_count=reinforcement_count,
        last_reinforced=(NOW - timedelta(days=90)).isoformat(),
    )
    assert len(_compute(_snapshot([], [notion], {}))) == expected_items


def test_conviction_without_a_parsable_last_reinforced_is_skipped() -> None:
    blank = _notion("notion_a", [], confidence=0.8, reinforcement_count=5)
    broken = _notion(
        "notion_b",
        [],
        confidence=0.8,
        reinforcement_count=5,
        last_reinforced="whenever",
    )
    assert _compute(_snapshot([], [blank, broken], {})) == []


def test_a_conviction_reinforced_in_the_future_is_not_stale() -> None:
    notion = _conviction("notion_a", days_since_reinforced=-5)
    assert _compute(_snapshot([], [notion], {})) == []


# --- precedence, limits, ordering -------------------------------------------


def _drifting_conviction(
    notion_id: str, *, distance: float = 1.0
) -> tuple[list[Memory], dict[str, np.ndarray], Notion]:
    angle = _angle_for_distance(distance)
    memories, embeddings, ids = _sources(notion_id, [0.0] * 3 + [angle] * 3)
    notion = _notion(
        notion_id,
        ids,
        confidence=0.8,
        reinforcement_count=5,
        last_reinforced=(NOW - timedelta(days=200)).isoformat(),
    )
    return memories, embeddings, notion


def test_a_notion_that_is_both_is_reported_as_drift_only() -> None:
    memories, embeddings, notion = _drifting_conviction("notion_a")
    items = _compute(_snapshot(memories, [notion], embeddings))
    assert len(items) == 1
    assert items[0]["kind"] == "drift"
    assert items[0]["key"] == f"drift:notion_a:{TODAY}"


def test_drift_precedence_holds_even_when_the_drift_item_loses_its_slot() -> None:
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    notions: list[Notion] = []
    # Four drifting notions; the weakest one is also a stale conviction.
    for index, distance in enumerate([1.0, 0.9, 0.8]):
        notion_id = f"notion_strong_{index}"
        angle = _angle_for_distance(distance)
        part_memories, part_embeddings, ids = _sources(notion_id, [0.0] * 3 + [angle] * 3)
        memories.extend(part_memories)
        embeddings.update(part_embeddings)
        notions.append(_notion(notion_id, ids))
    weak_memories, weak_embeddings, weak = _drifting_conviction(
        "notion_weak", distance=0.25
    )
    memories.extend(weak_memories)
    embeddings.update(weak_embeddings)
    notions.append(weak)

    items = _compute(_snapshot(memories, notions, embeddings))
    assert len(items) == DRIFT_MAX_DRIFT_ITEMS
    assert all(item["kind"] == "drift" for item in items)
    assert "notion_weak" not in {item["notion_id"] for item in items}


def test_drift_items_are_capped_and_ordered_by_distance_descending() -> None:
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    notions: list[Notion] = []
    for index, distance in enumerate([0.40, 1.00, 0.60, 0.80, 0.25]):
        notion_id = f"notion_{index}"
        angle = _angle_for_distance(distance)
        part_memories, part_embeddings, ids = _sources(notion_id, [0.0] * 3 + [angle] * 3)
        memories.extend(part_memories)
        embeddings.update(part_embeddings)
        notions.append(_notion(notion_id, ids))

    items = _compute(_snapshot(memories, notions, embeddings))
    assert [item["notion_id"] for item in items] == ["notion_1", "notion_3", "notion_2"]
    distances = [float(item["distance"]) for item in items]
    assert distances == sorted(distances, reverse=True)


def test_stale_items_are_capped_and_ordered_by_days_descending() -> None:
    notions = [
        _conviction("notion_recent", days_since_reinforced=50),
        _conviction("notion_oldest", days_since_reinforced=300),
        _conviction("notion_middle", days_since_reinforced=120),
    ]
    items = _compute(_snapshot([], notions, {}))
    assert len(items) == DRIFT_MAX_STALE_ITEMS
    assert [item["notion_id"] for item in items] == ["notion_oldest", "notion_middle"]
    assert [item["days_since_reinforced"] for item in items] == [300, 120]


def test_drift_items_come_before_stale_items() -> None:
    memories, embeddings, ids = _sources(
        "notion_drift", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    notions = [
        _conviction("notion_stale", days_since_reinforced=90),
        _notion("notion_drift", ids),
    ]
    items = _compute(_snapshot(memories, notions, embeddings))
    assert [item["kind"] for item in items] == ["drift", "stale_conviction"]


def test_ties_are_broken_deterministically_by_notion_id() -> None:
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    notions: list[Notion] = []
    for notion_id in ["notion_c", "notion_a", "notion_b", "notion_d"]:
        part_memories, part_embeddings, ids = _sources(
            notion_id, [0.0] * 3 + [WIDE_ANGLE] * 3
        )
        memories.extend(part_memories)
        embeddings.update(part_embeddings)
        notions.append(_notion(notion_id, ids))

    snapshot = _snapshot(memories, notions, embeddings)
    first = _compute(snapshot)
    second = _compute(snapshot)
    assert first == second
    assert [item["notion_id"] for item in first] == [
        "notion_a",
        "notion_b",
        "notion_c",
    ]


# --- keys and stats ---------------------------------------------------------


def test_keys_carry_the_generation_date() -> None:
    memories, embeddings, ids = _sources(
        "notion_drift", [0.0, 0.0, 0.0, WIDE_ANGLE, WIDE_ANGLE, WIDE_ANGLE]
    )
    notions = [
        _notion("notion_drift", ids),
        _conviction("notion_stale", days_since_reinforced=90),
    ]
    snapshot = _snapshot(memories, notions, embeddings)
    assert [item["key"] for item in _compute(snapshot)] == [
        f"drift:notion_drift:{TODAY}",
        f"drift:notion_stale:{TODAY}:stale",
    ]

    tomorrow = SourceSnapshot(
        now=NOW + timedelta(days=1),
        memories=snapshot.memories,
        embeddings=snapshot.embeddings,
        notions=snapshot.notions,
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )
    assert [item["key"] for item in _compute(tomorrow)] == [
        "drift:notion_drift:2026-09-17",
        "drift:notion_stale:2026-09-17:stale",
    ]


def test_empty_snapshot_produces_nothing() -> None:
    assert _compute(_snapshot([], [], {})) == []


def test_stats_report_candidate_counts() -> None:
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    notions: list[Notion] = []
    for index, distance in enumerate([1.0, 0.9, 0.8, 0.7]):
        notion_id = f"notion_{index}"
        angle = _angle_for_distance(distance)
        part_memories, part_embeddings, ids = _sources(notion_id, [0.0] * 3 + [angle] * 3)
        memories.extend(part_memories)
        embeddings.update(part_embeddings)
        notions.append(_notion(notion_id, ids))
    notions.extend(
        [
            _conviction("notion_stale_1", days_since_reinforced=90),
            _conviction("notion_stale_2", days_since_reinforced=80),
            _conviction("notion_stale_3", days_since_reinforced=70),
        ]
    )

    lens = DriftLens()
    lens.compute(_snapshot(memories, notions, embeddings))
    assert lens.stats == {
        "notion_count": 7,
        "drift_candidates": 4,
        "stale_candidates": 3,
        "drift_items": 3,
        "stale_items": 2,
    }
