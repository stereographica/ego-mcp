"""Tests for derived/chapters.py (D5 S1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from ego_mcp.derived.chapters import (
    CHAPTER_MAX_ITEMS,
    CHAPTER_TTL_HOURS,
    CHAPTER_WINDOW_WEEKS,
    LENS_NAME,
    ChaptersLens,
    WeekBucket,
    _boundary_score,
    _bucket_by_week,
    _carry_over_key,
    _is_local_max,
    _nearest_memory_id,
    _window,
)
from ego_mcp.derived.lenses import Lens
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import EmotionalTrace, Memory

NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=timezone.utc)
BASE_MONDAY = date(2025, 1, 6)
DIM = 4


@pytest.fixture(autouse=True)
def _utc_timezone(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "UTC")
    yield


def _unit(axis: int) -> np.ndarray:
    vector = np.zeros(DIM, dtype=np.float32)
    vector[axis] = 1.0
    return vector


def _mixed(first: int, second: int, weight: float) -> np.ndarray:
    vector = weight * _unit(first) + float(np.sqrt(1.0 - weight**2)) * _unit(second)
    return vector.astype(np.float32)


def _week_start(week: int) -> date:
    return BASE_MONDAY + timedelta(days=7 * week)


def _memory(
    memory_id: str,
    when: datetime,
    *,
    valence: float = 0.0,
    people: Sequence[str] = (),
) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=when.isoformat(),
        emotional_trace=EmotionalTrace(valence=valence),
        involved_person_ids=list(people),
    )


def _store(
    topics: Sequence[int],
    *,
    per_week: int = 2,
    people: Callable[[int], Sequence[str]] | None = None,
    valence: Callable[[int], float] | None = None,
) -> tuple[list[Memory], dict[str, np.ndarray]]:
    """Build ``len(topics)`` consecutive weeks of memories, one axis per week."""
    memories: list[Memory] = []
    embeddings: dict[str, np.ndarray] = {}
    for week, axis in enumerate(topics):
        for slot in range(per_week):
            memory_id = f"w{week:03d}s{slot}"
            moment = datetime.combine(
                _week_start(week) + timedelta(days=slot),
                time(9, 0),
                tzinfo=timezone.utc,
            )
            memories.append(
                _memory(
                    memory_id,
                    moment,
                    valence=0.0 if valence is None else valence(week),
                    people=() if people is None else people(week),
                )
            )
            embeddings[memory_id] = _unit(axis)
    return memories, embeddings


def _snapshot(
    memories: list[Memory],
    embeddings: dict[str, np.ndarray] | None,
    *,
    surfaced: dict[str, str] | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=embeddings,
        notions=[],
        question_log=[],
        relationships={},
        surfaced=surfaced or {},
        co_retrievals=[],
    )


def _compute(
    topics: Sequence[int],
    *,
    per_week: int = 2,
    people: Callable[[int], Sequence[str]] | None = None,
    valence: Callable[[int], float] | None = None,
    surfaced: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    memories, embeddings = _store(
        topics, per_week=per_week, people=people, valence=valence
    )
    return ChaptersLens().compute(_snapshot(memories, embeddings, surfaced=surfaced))


# --- _bucket_by_week --------------------------------------------------------


def test_bucket_by_week_keeps_empty_weeks_for_continuity() -> None:
    memories, embeddings = _store([0, 0, 0, 0])
    kept = [memory for memory in memories if not memory.id.startswith(("w001", "w002"))]
    buckets = _bucket_by_week(kept, embeddings)
    assert [bucket.week_start for bucket in buckets] == [
        _week_start(i) for i in range(4)
    ]
    assert [len(bucket.memory_ids) for bucket in buckets] == [2, 0, 0, 2]
    assert buckets[1].centroid is None
    assert buckets[1].mean_valence == 0.0
    assert buckets[1].people == frozenset()


def test_bucket_by_week_starts_on_monday() -> None:
    sunday = datetime.combine(
        _week_start(0) + timedelta(days=6), time(23, 30), tzinfo=timezone.utc
    )
    next_monday = datetime.combine(_week_start(1), time(0, 30), tzinfo=timezone.utc)
    memories = [_memory("sun", sunday), _memory("mon", next_monday)]
    embeddings = {"sun": _unit(0), "mon": _unit(0)}
    buckets = _bucket_by_week(memories, embeddings)
    assert [bucket.memory_ids for bucket in buckets] == [["sun"], ["mon"]]
    assert buckets[0].week_start == _week_start(0)
    assert buckets[0].week_start.weekday() == 0


def test_bucket_by_week_ignores_memories_without_an_embedding() -> None:
    memories, embeddings = _store([0])
    embeddings.pop("w000s1")
    buckets = _bucket_by_week(memories, embeddings)
    assert [bucket.memory_ids for bucket in buckets] == [["w000s0"]]


def test_bucket_by_week_ignores_unparsable_timestamps() -> None:
    memories = [Memory(id="bad", timestamp="not-a-date"), Memory(id="blank")]
    buckets = _bucket_by_week(memories, {"bad": _unit(0), "blank": _unit(0)})
    assert buckets == []


def test_bucket_by_week_aggregates_valence_and_people() -> None:
    memories, embeddings = _store(
        [0], valence=lambda _week: 0.0, people=lambda _week: ("p1",)
    )
    memories[0].emotional_trace.valence = 0.8
    memories[1].emotional_trace.valence = -0.2
    memories[1].involved_person_ids = ["p2"]
    bucket = _bucket_by_week(memories, embeddings)[0]
    assert bucket.mean_valence == pytest.approx(0.3)
    assert bucket.people == frozenset({"p1", "p2"})
    assert bucket.memory_ids == ["w000s0", "w000s1"]
    assert bucket.centroid is not None


def test_bucket_by_week_orders_memories_oldest_first() -> None:
    memories, embeddings = _store([0], per_week=3)
    buckets = _bucket_by_week(list(reversed(memories)), embeddings)
    assert buckets[0].memory_ids == ["w000s0", "w000s1", "w000s2"]


# --- _window ----------------------------------------------------------------


def test_window_collects_ids_people_and_weighted_valence() -> None:
    buckets = [
        WeekBucket(_week_start(0), ["a", "b"], _unit(0), 1.0, frozenset({"p1"})),
        WeekBucket(_week_start(1), [], None, 0.0, frozenset()),
        WeekBucket(_week_start(2), ["c"], _unit(0), -0.5, frozenset({"p2"})),
        WeekBucket(_week_start(3), [], None, 0.0, frozenset()),
    ]
    stats = _window(buckets, 0, 4)
    assert stats.memory_ids == ["a", "b", "c"]
    assert stats.people == frozenset({"p1", "p2"})
    # Weighted by memory count: (1.0*2 + -0.5*1) / 3, not the mean of the weeks.
    assert stats.mean_valence == pytest.approx(1.5 / 3.0)
    assert stats.centroid is not None


def test_window_over_empty_buckets_has_no_centroid() -> None:
    buckets = [WeekBucket(_week_start(i), [], None, 0.0, frozenset()) for i in range(4)]
    stats = _window(buckets, 0, 4)
    assert stats.centroid is None
    assert stats.memory_ids == []
    assert stats.mean_valence == 0.0


def test_window_is_also_a_plain_tuple() -> None:
    buckets = [WeekBucket(_week_start(0), ["a"], _unit(0), 0.0, frozenset())]
    centroid, mean_valence, people, memory_ids = _window(buckets, 0, 1)
    assert memory_ids == ["a"]
    assert mean_valence == 0.0
    assert people == frozenset()
    assert centroid is not None


# --- _boundary_score --------------------------------------------------------


def _stats(axis: int | None, valence: float, people: Sequence[str]) -> Any:
    buckets = [
        WeekBucket(
            _week_start(0),
            ["x"] if axis is not None else [],
            _unit(axis) if axis is not None else None,
            valence,
            frozenset(people),
        )
    ]
    return _window(buckets, 0, 1)


def test_boundary_score_orthogonal_topics() -> None:
    score = _boundary_score(_stats(0, 0.0, ()), _stats(1, 0.0, ()))
    assert score == pytest.approx(1.0)


def test_boundary_score_identical_windows_is_zero() -> None:
    score = _boundary_score(_stats(0, 0.5, ("p1",)), _stats(0, 0.5, ("p1",)))
    assert score == pytest.approx(0.0)


def test_boundary_score_adds_valence_and_people_terms() -> None:
    before = _stats(0, 1.0, ("p1",))
    after = _stats(0, -1.0, ("p2",))
    # d_topic 0 + 0.5 * |1 - -1| + 0.5 * jaccard distance 1.0
    assert _boundary_score(before, after) == pytest.approx(1.5)


def test_boundary_score_partial_people_overlap() -> None:
    before = _stats(0, 0.0, ("p1", "p2"))
    after = _stats(0, 0.0, ("p2", "p3"))
    # Jaccard distance = 1 - 1/3
    assert _boundary_score(before, after) == pytest.approx(0.5 * (1.0 - 1.0 / 3.0))


def test_boundary_score_without_centroids_ignores_topic() -> None:
    assert _boundary_score(_stats(None, 0.0, ()), _stats(1, 0.0, ())) == 0.0


# --- _nearest_memory_id -----------------------------------------------------


def test_nearest_memory_id_picks_the_closest_vector() -> None:
    embeddings = {"a": _unit(0), "b": _mixed(0, 1, 0.9), "c": _unit(1)}
    assert _nearest_memory_id(["c", "b", "a"], embeddings, _unit(0)) == "a"


def test_nearest_memory_id_keeps_the_first_on_a_tie() -> None:
    embeddings = {"a": _unit(0), "b": _unit(0)}
    assert _nearest_memory_id(["a", "b"], embeddings, _unit(0)) == "a"
    assert _nearest_memory_id(["b", "a"], embeddings, _unit(0)) == "b"


def test_nearest_memory_id_without_a_centre_is_blank() -> None:
    assert _nearest_memory_id(["a"], {"a": _unit(0)}, None) == ""
    assert _nearest_memory_id([], {}, _unit(0)) == ""


# --- _is_local_max ----------------------------------------------------------


def test_is_local_max_within_two_weeks() -> None:
    scores = {4: 0.4, 5: 0.6, 6: 0.9, 7: 0.5, 8: 0.3}
    assert _is_local_max(scores, 6) is True
    assert _is_local_max(scores, 5) is False
    assert _is_local_max(scores, 4) is False


def test_is_local_max_ignores_weeks_further_than_the_radius() -> None:
    scores = {1: 5.0, 4: 0.5}
    assert _is_local_max(scores, 4) is True


# --- _carry_over_key --------------------------------------------------------


def test_carry_over_key_uses_the_exact_week_when_it_is_known() -> None:
    week = _week_start(10)
    assert _carry_over_key(week, [week], set()) == f"chapter:{week.isoformat()}"


def test_carry_over_key_adopts_a_known_week_one_week_away() -> None:
    week = _week_start(10)
    known = _week_start(9)
    assert _carry_over_key(week, [known], set()) == f"chapter:{known.isoformat()}"
    later = _week_start(11)
    assert _carry_over_key(week, [later], set()) == f"chapter:{later.isoformat()}"


def test_carry_over_key_ignores_a_known_week_two_weeks_away() -> None:
    week = _week_start(10)
    assert _carry_over_key(week, [_week_start(8)], set()) == (
        f"chapter:{week.isoformat()}"
    )


def test_carry_over_key_prefers_the_nearest_known_week() -> None:
    week = _week_start(10) + timedelta(days=1)
    known = [_week_start(9), _week_start(10)]
    assert _carry_over_key(week, known, set()) == f"chapter:{_week_start(10)}"


def test_carry_over_key_does_not_reuse_a_key_already_taken() -> None:
    week = _week_start(10)
    taken = {f"chapter:{_week_start(9).isoformat()}"}
    assert _carry_over_key(week, [_week_start(9)], taken) == (
        f"chapter:{week.isoformat()}"
    )


# --- ChaptersLens -----------------------------------------------------------


def test_lens_satisfies_the_protocol() -> None:
    lens: Lens = ChaptersLens()
    assert lens.name == LENS_NAME == "chapters"
    assert lens.needs_embeddings is True
    assert lens.ttl_hours == CHAPTER_TTL_HOURS


def test_compute_without_embeddings_is_empty() -> None:
    memories, _ = _store([0] * 20)
    assert ChaptersLens().compute(_snapshot(memories, None)) == []


def test_compute_without_enough_weeks_is_empty() -> None:
    assert _compute([0] * 4 + [1] * 3) == []


def test_compute_finds_one_boundary_where_the_topic_turns() -> None:
    items = _compute([0] * 10 + [1] * 10)
    assert len(items) == 1
    item = items[0]
    assert item["boundary_week"] == _week_start(10).isoformat()
    assert item["key"] == f"chapter:{_week_start(10).isoformat()}"
    assert item["score"] == pytest.approx(1.0)
    assert item["before_memory_id"].startswith(("w006", "w007", "w008", "w009"))
    assert item["after_memory_id"].startswith(("w010", "w011", "w012", "w013"))
    assert item["people_before"] == []
    assert item["people_after"] == []


def test_compute_reports_the_people_on_each_side() -> None:
    items = _compute(
        [0] * 10 + [1] * 10,
        people=lambda week: ("p1",) if week < 10 else ("p2",),
    )
    assert len(items) == 1
    assert items[0]["people_before"] == ["p1"]
    assert items[0]["people_after"] == ["p2"]


def test_compute_skips_windows_with_too_few_memories() -> None:
    # One memory a week leaves four per window, below the minimum of six.
    assert _compute([0] * 10 + [1] * 10, per_week=1) == []


def test_compute_requires_the_minimum_score() -> None:
    memories, embeddings = _store([0] * 10 + [1] * 10)
    for memory_id in list(embeddings):
        if embeddings[memory_id][1] == 1.0:
            # A turn far too gentle to be a chapter boundary.
            embeddings[memory_id] = _mixed(0, 1, 0.9)
    assert ChaptersLens().compute(_snapshot(memories, embeddings)) == []


def test_compute_does_not_see_a_turn_in_the_most_recent_weeks() -> None:
    # The turn is at week eighteen of twenty: no window reaches past it.
    assert _compute([0] * 18 + [1] * 2) == []


def test_compute_never_reports_a_boundary_in_the_trailing_window() -> None:
    items = _compute([0] * 16 + [1] * 4)
    latest_judged = _week_start(20 - CHAPTER_WINDOW_WEEKS - 1)
    assert items
    for item in items:
        assert date.fromisoformat(item["boundary_week"]) <= latest_judged


def test_compute_suppresses_a_second_boundary_within_the_gap() -> None:
    # Two turns four weeks apart; only the stronger one survives.
    items = _compute(
        [0] * 6 + [1] * 4 + [2] * 14,
        people=lambda week: ("p1",) if week < 10 else ("p2",),
    )
    assert len(items) == 1
    assert items[0]["boundary_week"] == _week_start(10).isoformat()


def test_compute_keeps_boundaries_further_apart_than_the_gap() -> None:
    items = _compute([0] * 8 + [1] * 8 + [2] * 8)
    assert [item["boundary_week"] for item in items] == [
        _week_start(16).isoformat(),
        _week_start(8).isoformat(),
    ]


def test_compute_orders_newest_first_and_caps_the_item_count() -> None:
    topics: list[int] = []
    for block in range(16):
        topics.extend([block % 2] * 8)
    items = _compute(topics)
    assert len(items) == CHAPTER_MAX_ITEMS
    weeks = [item["boundary_week"] for item in items]
    assert weeks == sorted(weeks, reverse=True)


def test_compute_key_is_stable_across_runs() -> None:
    first = _compute([0] * 10 + [1] * 10)
    second = _compute([0] * 10 + [1] * 10)
    assert first == second


def test_compute_carries_over_a_key_from_one_week_earlier() -> None:
    known = _week_start(9).isoformat()
    items = _compute(
        [0] * 10 + [1] * 10, surfaced={f"chapter:{known}": NOW.isoformat()}
    )
    assert items[0]["key"] == f"chapter:{known}"
    # The boundary itself still reports the week it was measured at.
    assert items[0]["boundary_week"] == _week_start(10).isoformat()


def test_compute_does_not_carry_over_a_key_two_weeks_away() -> None:
    known = _week_start(8).isoformat()
    items = _compute(
        [0] * 10 + [1] * 10, surfaced={f"chapter:{known}": NOW.isoformat()}
    )
    assert items[0]["key"] == f"chapter:{_week_start(10).isoformat()}"


def test_compute_ignores_unrelated_and_malformed_surfaced_keys() -> None:
    surfaced = {
        "recurrence:mem_a:2026-09-16": NOW.isoformat(),
        "chapter:not-a-date": NOW.isoformat(),
    }
    items = _compute([0] * 10 + [1] * 10, surfaced=surfaced)
    assert items[0]["key"] == f"chapter:{_week_start(10).isoformat()}"
