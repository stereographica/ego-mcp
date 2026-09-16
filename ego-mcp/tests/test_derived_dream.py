"""Tests for derived/dream.py (D2 S1)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from ego_mcp.derived.dream import (
    DREAM_MAX_ITEMS,
    DREAM_MIN_DISTANCE,
    DreamLens,
    _threads,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import (
    BodyState,
    Emotion,
    EmotionalTrace,
    LinkType,
    Memory,
    MemoryLink,
    Notion,
)

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _memory(
    memory_id: str,
    *,
    days_ago: float = 30.0,
    emotion: Emotion = Emotion.NEUTRAL,
    intensity: float = 0.5,
    time_phase: str | None = None,
    persons: Sequence[str] = (),
    tags: Sequence[str] = (),
    links: Sequence[str] = (),
) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=(NOW - timedelta(days=days_ago)).isoformat(),
        emotional_trace=EmotionalTrace(
            primary=emotion,
            intensity=intensity,
            body_state=None if time_phase is None else BodyState(time_phase=time_phase),
        ),
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED) for target in links
        ],
        tags=list(tags),
        involved_person_ids=list(persons),
    )


def _one_hot(index: int, dim: int = 8) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    vector[index] = 1.0
    return vector


def _angle(degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    return np.array(
        [math.cos(radians), math.sin(radians)],
        dtype=np.float32,
    )


def _snapshot(
    memories: Sequence[Memory],
    *,
    embeddings: dict[str, np.ndarray] | None = None,
    notions: Sequence[Notion] = (),
    surfaced: dict[str, str] | None = None,
    now: datetime = NOW,
) -> SourceSnapshot:
    if embeddings is None:
        embeddings = {
            memory.id: _one_hot(index) for index, memory in enumerate(memories)
        }
    return SourceSnapshot(
        now=now,
        memories=list(memories),
        embeddings=embeddings,
        notions=list(notions),
        question_log=[],
        relationships={},
        surfaced=dict(surfaced or {}),
        co_retrievals=[],
    )


def _keys(items: list[dict[str, Any]]) -> list[str]:
    return [str(item["key"]) for item in items]


# --- _threads ---------------------------------------------------------------


def test_thread_emotion_needs_same_primary_and_both_intense() -> None:
    left = _memory("a", emotion=Emotion.LONELY, intensity=0.6)
    right = _memory("b", emotion=Emotion.LONELY, intensity=0.5)
    assert _threads(left, right) == ["emotion"]


def test_thread_emotion_rejects_weak_intensity() -> None:
    left = _memory("a", emotion=Emotion.LONELY, intensity=0.6)
    right = _memory("b", emotion=Emotion.LONELY, intensity=0.49)
    assert _threads(left, right) == []


def test_thread_emotion_rejects_different_primary() -> None:
    left = _memory("a", emotion=Emotion.LONELY, intensity=0.9)
    right = _memory("b", emotion=Emotion.HOPEFUL, intensity=0.9)
    assert _threads(left, right) == []


def test_thread_hour_matches_time_phase() -> None:
    left = _memory("a", emotion=Emotion.LONELY, time_phase="deep_night")
    right = _memory("b", emotion=Emotion.HOPEFUL, time_phase="deep_night")
    assert _threads(left, right) == ["hour"]


def test_thread_hour_ignores_unknown_and_missing_body_state() -> None:
    unknown_left = _memory("a", emotion=Emotion.LONELY, time_phase="unknown")
    unknown_right = _memory("b", emotion=Emotion.HOPEFUL, time_phase="unknown")
    assert _threads(unknown_left, unknown_right) == []

    missing_left = _memory("c", emotion=Emotion.LONELY)
    missing_right = _memory("d", emotion=Emotion.HOPEFUL)
    assert _threads(missing_left, missing_right) == []


def test_thread_person_needs_a_shared_person() -> None:
    left = _memory("a", emotion=Emotion.LONELY, persons=["p1", "p2"])
    right = _memory("b", emotion=Emotion.HOPEFUL, persons=["p2"])
    assert _threads(left, right) == ["person"]

    stranger = _memory("c", emotion=Emotion.HOPEFUL, persons=["p9"])
    assert _threads(left, stranger) == []


def test_thread_tag_is_exactly_one_shared_tag() -> None:
    left = _memory("a", emotion=Emotion.LONELY, tags=["rain", "kitchen"])
    one = _memory("b", emotion=Emotion.HOPEFUL, tags=["rain", "train"])
    assert _threads(left, one) == ["tag"]

    two = _memory("c", emotion=Emotion.HOPEFUL, tags=["rain", "kitchen"])
    assert _threads(left, two) == []

    none = _memory("d", emotion=Emotion.HOPEFUL, tags=["train"])
    assert _threads(left, none) == []


def test_thread_tag_ignores_blank_tags() -> None:
    left = _memory("a", emotion=Emotion.LONELY, tags=["rain", ""])
    right = _memory("b", emotion=Emotion.HOPEFUL, tags=["rain", ""])
    assert _threads(left, right) == ["tag"]


def test_threads_are_listed_in_declaration_order() -> None:
    left = _memory(
        "a",
        emotion=Emotion.LONELY,
        intensity=0.8,
        time_phase="dawn",
        persons=["p1"],
        tags=["rain"],
    )
    right = _memory(
        "b",
        emotion=Emotion.LONELY,
        intensity=0.8,
        time_phase="dawn",
        persons=["p1"],
        tags=["rain"],
    )
    assert _threads(left, right) == ["emotion", "hour", "person", "tag"]


# --- compute: the happy path ------------------------------------------------


def _far_pair() -> list[Memory]:
    return [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"]),
    ]


def test_compute_emits_one_item_for_a_distant_unconnected_pair() -> None:
    items = DreamLens().compute(_snapshot(_far_pair()))
    assert items == [
        {
            "key": "dream:m1:m2",
            "memory_ids": ["m1", "m2"],
            "distance": 1.0,
            "threads": ["tag"],
        }
    ]


def test_compute_orders_pair_ids_lexicographically() -> None:
    memories = [
        _memory("zzz", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("aaa", emotion=Emotion.HOPEFUL, tags=["rain"]),
    ]
    items = DreamLens().compute(_snapshot(memories))
    assert _keys(items) == ["dream:aaa:zzz"]
    assert items[0]["memory_ids"] == ["aaa", "zzz"]


# --- compute: exclusions ----------------------------------------------------


def test_compute_excludes_pairs_that_are_too_close() -> None:
    memories = _far_pair()
    close = {"m1": _one_hot(0), "m2": _one_hot(0)}
    assert DreamLens().compute(_snapshot(memories, embeddings=close)) == []


def test_compute_keeps_a_pair_exactly_at_the_distance_floor() -> None:
    memories = _far_pair()
    # cos(theta) = 1 - DREAM_MIN_DISTANCE puts the pair right on the boundary.
    degrees = math.degrees(math.acos(1.0 - DREAM_MIN_DISTANCE))
    embeddings = {"m1": _angle(0.0), "m2": _angle(degrees)}
    items = DreamLens().compute(_snapshot(memories, embeddings=embeddings))
    assert _keys(items) == ["dream:m1:m2"]
    assert items[0]["distance"] == round(DREAM_MIN_DISTANCE, 3)


def test_compute_excludes_directly_linked_pairs() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"], links=["m2"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"]),
    ]
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_excludes_pairs_two_hops_apart() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"], links=["m1", "m3"]),
        _memory("m3", emotion=Emotion.CURIOUS, tags=["rain"]),
    ]
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_allows_pairs_three_hops_apart() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["x"], links=["m1"]),
        _memory("m3", emotion=Emotion.CURIOUS, tags=["y"], links=["m2"]),
        _memory("m4", emotion=Emotion.ANXIOUS, tags=["rain"], links=["m3"]),
    ]
    assert "dream:m1:m4" in _keys(DreamLens().compute(_snapshot(memories)))


def test_compute_excludes_pairs_sharing_a_notion() -> None:
    memories = _far_pair()
    notion = Notion(id="n1", label="rain", source_memory_ids=["m1", "m2"])
    assert DreamLens().compute(_snapshot(memories, notions=[notion])) == []


def test_compute_allows_pairs_in_different_notions() -> None:
    memories = _far_pair()
    notions = [
        Notion(id="n1", label="a", source_memory_ids=["m1"]),
        Notion(id="n2", label="b", source_memory_ids=["m2"]),
    ]
    assert _keys(DreamLens().compute(_snapshot(memories, notions=notions))) == [
        "dream:m1:m2"
    ]


def test_compute_excludes_memories_younger_than_the_age_floor() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"], days_ago=30.0),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"], days_ago=3.0),
    ]
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_keeps_memories_exactly_at_the_age_floor() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"], days_ago=7.0),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"], days_ago=7.0),
    ]
    assert _keys(DreamLens().compute(_snapshot(memories))) == ["dream:m1:m2"]


def test_compute_excludes_memories_with_an_unusable_timestamp() -> None:
    memories = _far_pair()
    memories[1].timestamp = "not a timestamp"
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_excludes_pairs_without_a_thread() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["train"]),
    ]
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_excludes_pairs_sharing_two_tags() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain", "kitchen"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain", "kitchen"]),
    ]
    assert DreamLens().compute(_snapshot(memories)) == []


def test_compute_excludes_memories_without_an_embedding() -> None:
    memories = _far_pair()
    assert DreamLens().compute(_snapshot(memories, embeddings={"m1": _one_hot(0)})) == []


def test_compute_returns_nothing_without_embeddings() -> None:
    snapshot = SourceSnapshot(
        now=NOW,
        memories=_far_pair(),
        embeddings=None,
        notions=[],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )
    assert DreamLens().compute(snapshot) == []


def test_compute_returns_nothing_for_an_empty_store() -> None:
    assert DreamLens().compute(_snapshot([])) == []


# --- compute: sampling, ordering, suppression -------------------------------


def _wheel(ids: Sequence[str], degrees: Sequence[float]) -> SourceSnapshot:
    memories = [_memory(memory_id, tags=["rain"]) for memory_id in ids]
    embeddings = {
        memory_id: _angle(angle) for memory_id, angle in zip(ids, degrees, strict=True)
    }
    return _snapshot(memories, embeddings=embeddings)


def test_compute_returns_the_three_most_distant_pairs_in_order() -> None:
    # Pairwise distances: m2/m4 1.996 > m1/m3 1.940 > m1/m4 1.342 > ...
    snapshot = _wheel(("m1", "m2", "m3", "m4"), (0.0, 75.0, 160.0, 250.0))
    items = DreamLens().compute(snapshot)
    assert len(items) == DREAM_MAX_ITEMS
    assert _keys(items) == ["dream:m2:m4", "dream:m1:m3", "dream:m1:m4"]
    distances = [float(item["distance"]) for item in items]
    assert distances == sorted(distances, reverse=True)


def test_compute_breaks_distance_ties_by_key() -> None:
    # Exact axis vectors: m1/m3 and m2/m4 are both 2.0; every other pair is 1.0.
    memories = [_memory(f"m{index}", tags=["rain"]) for index in range(1, 5)]
    embeddings = {
        "m1": np.array([1.0, 0.0], dtype=np.float32),
        "m2": np.array([0.0, 1.0], dtype=np.float32),
        "m3": np.array([-1.0, 0.0], dtype=np.float32),
        "m4": np.array([0.0, -1.0], dtype=np.float32),
    }
    snapshot = _snapshot(memories, embeddings=embeddings)
    assert _keys(DreamLens().compute(snapshot)) == [
        "dream:m1:m3",
        "dream:m2:m4",
        "dream:m1:m2",
    ]


def test_compute_is_reproducible_within_the_same_day() -> None:
    snapshot = _wheel(("m1", "m2", "m3", "m4", "m5"), (0.0, 71.0, 143.0, 214.0, 287.0))
    first = DreamLens().compute(snapshot)
    second = DreamLens().compute(snapshot)
    assert first == second

    later_same_day = _snapshot(
        snapshot.memories,
        embeddings=snapshot.embeddings,
        now=NOW + timedelta(hours=10),
    )
    assert DreamLens().compute(later_same_day) == first


def test_compute_never_repeats_a_pair_within_one_run() -> None:
    snapshot = _wheel(("m1", "m2", "m3", "m4"), (0.0, 75.0, 160.0, 250.0))
    keys = _keys(DreamLens().compute(snapshot))
    assert len(set(keys)) == len(keys)


def test_compute_skips_pairs_already_surfaced() -> None:
    surfaced = {"dream:m1:m2": NOW.isoformat()}
    assert DreamLens().compute(_snapshot(_far_pair(), surfaced=surfaced)) == []


def test_compute_skips_surfaced_pairs_written_in_either_order() -> None:
    surfaced = {"dream:m2:m1": NOW.isoformat()}
    assert DreamLens().compute(_snapshot(_far_pair(), surfaced=surfaced)) == []


def test_compute_ignores_malformed_and_foreign_surfaced_keys() -> None:
    surfaced = {
        "dream:m1": NOW.isoformat(),
        "dream::m2": NOW.isoformat(),
        "dream:m1:m2:m3": NOW.isoformat(),
        "recurrence:m1:m2": NOW.isoformat(),
    }
    assert _keys(DreamLens().compute(_snapshot(_far_pair(), surfaced=surfaced))) == [
        "dream:m1:m2"
    ]


def test_compute_drops_a_surfaced_pair_from_a_larger_candidate_set() -> None:
    snapshot = _wheel(("m1", "m2", "m3", "m4"), (0.0, 75.0, 160.0, 250.0))
    surfaced = _snapshot(
        snapshot.memories,
        embeddings=snapshot.embeddings,
        surfaced={"dream:m2:m4": NOW.isoformat()},
    )
    assert _keys(DreamLens().compute(surfaced)) == [
        "dream:m1:m3",
        "dream:m1:m4",
        "dream:m3:m4",
    ]


# --- behavioural evidence (D3) ----------------------------------------------


def test_stats_count_linked_and_unlinked_surfaced_pairs() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"], links=["m2"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"]),
        _memory("m3", emotion=Emotion.CURIOUS, tags=["rain"]),
        _memory("m4", emotion=Emotion.ANXIOUS, tags=["rain"]),
    ]
    surfaced = {
        "dream:m1:m2": NOW.isoformat(),
        "dream:m3:m4": NOW.isoformat(),
        "dream:m1:m4": NOW.isoformat(),
        "recurrence:m1:m3": NOW.isoformat(),
        "dream:broken": NOW.isoformat(),
    }
    lens = DreamLens()
    lens.compute(_snapshot(memories, surfaced=surfaced))
    assert lens.stats == {"dream_pairs_surfaced": 3, "dream_pairs_linked": 1}


def test_stats_count_a_link_recorded_in_the_reverse_direction() -> None:
    memories = [
        _memory("m1", emotion=Emotion.LONELY, tags=["rain"]),
        _memory("m2", emotion=Emotion.HOPEFUL, tags=["rain"], links=["m1"]),
    ]
    lens = DreamLens()
    lens.compute(_snapshot(memories, surfaced={"dream:m1:m2": NOW.isoformat()}))
    assert lens.stats == {"dream_pairs_surfaced": 1, "dream_pairs_linked": 1}


def test_stats_ignore_surfaced_pairs_whose_memories_are_gone() -> None:
    lens = DreamLens()
    lens.compute(_snapshot(_far_pair(), surfaced={"dream:gone1:gone2": NOW.isoformat()}))
    assert lens.stats == {"dream_pairs_surfaced": 1, "dream_pairs_linked": 0}


def test_stats_are_written_even_when_no_dream_is_possible() -> None:
    lens = DreamLens()
    lens.compute(_snapshot([], surfaced={"dream:m1:m2": NOW.isoformat()}))
    assert lens.stats == {"dream_pairs_surfaced": 1, "dream_pairs_linked": 0}


def test_stats_reset_between_runs() -> None:
    lens = DreamLens()
    lens.compute(_snapshot(_far_pair(), surfaced={"dream:m1:m2": NOW.isoformat()}))
    lens.compute(_snapshot(_far_pair()))
    assert lens.stats == {"dream_pairs_surfaced": 0, "dream_pairs_linked": 0}


# --- lens metadata ----------------------------------------------------------


def test_lens_metadata() -> None:
    lens = DreamLens()
    assert lens.name == "dream"
    assert lens.needs_embeddings is True
    assert lens.ttl_hours == 48.0
