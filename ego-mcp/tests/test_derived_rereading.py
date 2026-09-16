"""Tests for derived/rereading.py (D7 S4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ego_mcp.derived.lenses import Lens, lens_stats
from ego_mcp.derived.rereading import (
    REREAD_MAX_ITEMS,
    REREAD_MIN_ACCESSES,
    RereadingLens,
    reread_key,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _entry(*, days_ago: int, mood: str, phase: str = "night") -> dict[str, str]:
    return {
        "at": (NOW - timedelta(days=days_ago)).isoformat(),
        "mood": mood,
        "phase": phase,
    }


def _memory(memory_id: str, log: list[dict[str, str]]) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=NOW.isoformat(),
        access_log=log,
    )


def _snapshot(memories: list[Memory], *, now: datetime = NOW) -> SourceSnapshot:
    return SourceSnapshot(
        now=now,
        memories=memories,
        embeddings=None,
        notions=[],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


def _compute(memories: list[Memory]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    lens = RereadingLens()
    items = lens.compute(_snapshot(memories))
    return items, dict(lens.stats)


# --- lens identity ----------------------------------------------------------


def test_lens_attributes() -> None:
    lens: Lens = RereadingLens()  # structural conformance is checked by mypy
    assert lens.name == "rereading"
    assert lens.needs_embeddings is False
    assert lens.ttl_hours == 36.0
    assert lens_stats(lens) == {
        "reread_memory_count": 0,
        "reread_multi_mood_count": 0,
    }


def test_empty_store_yields_no_items() -> None:
    items, stats = _compute([])
    assert items == []
    assert stats == {"reread_memory_count": 0, "reread_multi_mood_count": 0}


# --- threshold --------------------------------------------------------------


def test_fewer_than_three_accesses_is_not_an_item() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (5, 3)]
    items, stats = _compute([_memory("a", log)])
    assert items == []
    assert stats["reread_memory_count"] == 0


def test_three_accesses_is_an_item_even_with_one_mood() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    items, stats = _compute([_memory("a", log)])
    assert len(items) == 1
    assert items[0]["accesses"] == REREAD_MIN_ACCESSES
    assert items[0]["distinct_moods"] == 1
    assert items[0]["moods"] == ["calm"]
    assert stats == {"reread_memory_count": 1, "reread_multi_mood_count": 0}


def test_memory_without_access_log_is_ignored() -> None:
    items, stats = _compute([_memory("a", [])])
    assert items == []
    assert stats["reread_memory_count"] == 0


# --- item shape -------------------------------------------------------------


def test_item_shape_and_key() -> None:
    log = [
        _entry(days_ago=10, mood="anxious"),
        _entry(days_ago=4, mood="calm"),
        _entry(days_ago=0, mood="grateful"),
    ]
    items, _ = _compute([_memory("mem_a", log)])
    assert items[0] == {
        "key": "reread:mem_a:3",
        "memory_id": "mem_a",
        "accesses": 3,
        "distinct_moods": 3,
        "span_days": 10,
        "moods": ["anxious", "calm", "grateful"],
    }
    assert items[0]["key"] == reread_key("mem_a", 3)


def test_key_changes_when_the_log_grows() -> None:
    base = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    before, _ = _compute([_memory("a", base)])
    after, _ = _compute([_memory("a", base + [_entry(days_ago=0, mood="calm")])])
    assert before[0]["key"] != after[0]["key"]
    assert after[0]["key"] == "reread:a:4"


def test_moods_are_distinct_in_first_seen_order() -> None:
    log = [
        _entry(days_ago=12, mood="calm"),
        _entry(days_ago=8, mood="anxious"),
        _entry(days_ago=4, mood="calm"),
        _entry(days_ago=1, mood="anxious"),
    ]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["moods"] == ["calm", "anxious"]
    assert items[0]["distinct_moods"] == 2


def test_empty_moods_do_not_count() -> None:
    log = [
        _entry(days_ago=6, mood=""),
        _entry(days_ago=4, mood="calm"),
        _entry(days_ago=2, mood=""),
    ]
    items, stats = _compute([_memory("a", log)])
    assert items[0]["accesses"] == 3
    assert items[0]["distinct_moods"] == 1
    assert items[0]["moods"] == ["calm"]
    assert stats == {"reread_memory_count": 1, "reread_multi_mood_count": 0}


def test_items_carry_no_memory_text() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    items, _ = _compute([_memory("a", log)])
    assert set(items[0]) == {
        "key",
        "memory_id",
        "accesses",
        "distinct_moods",
        "span_days",
        "moods",
    }


# --- span_days --------------------------------------------------------------


def test_span_days_spans_first_to_last() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (40, 20, 2)]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["span_days"] == 38


def test_span_days_is_zero_within_one_day() -> None:
    log = [_entry(days_ago=0, mood="calm") for _ in range(3)]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["span_days"] == 0


def test_unparsable_timestamps_do_not_break_the_span() -> None:
    log = [
        {"at": "not-a-date", "mood": "calm", "phase": "night"},
        _entry(days_ago=7, mood="anxious"),
        _entry(days_ago=1, mood="calm"),
    ]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["accesses"] == 3
    assert items[0]["span_days"] == 6


def test_single_parsable_timestamp_gives_a_zero_span() -> None:
    log = [
        {"at": "", "mood": "calm", "phase": "night"},
        {"at": "nope", "mood": "anxious", "phase": "day"},
        _entry(days_ago=3, mood="calm"),
    ]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["span_days"] == 0


def test_naive_timestamps_are_aligned_to_the_snapshot() -> None:
    log = [
        {"at": (NOW - timedelta(days=9)).replace(tzinfo=None).isoformat(), "mood": "a"},
        _entry(days_ago=5, mood="b"),
        _entry(days_ago=0, mood="c"),
    ]
    items, _ = _compute([_memory("a", log)])
    assert items[0]["span_days"] == 9


# --- ordering and limits ----------------------------------------------------


def test_sorted_by_distinct_moods_then_accesses() -> None:
    many_accesses = [_entry(days_ago=day, mood="calm") for day in range(9, 0, -1)]
    two_moods = [
        _entry(days_ago=6, mood="calm"),
        _entry(days_ago=4, mood="anxious"),
        _entry(days_ago=2, mood="calm"),
    ]
    three_accesses = [_entry(days_ago=day, mood="calm") for day in (5, 3, 1)]
    items, _ = _compute(
        [
            _memory("one_mood_many", many_accesses),
            _memory("two_moods", two_moods),
            _memory("one_mood_few", three_accesses),
        ]
    )
    assert [item["memory_id"] for item in items] == [
        "two_moods",
        "one_mood_many",
        "one_mood_few",
    ]


def test_ties_break_on_memory_id() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    items, _ = _compute([_memory("b", log), _memory("a", log)])
    assert [item["memory_id"] for item in items] == ["a", "b"]


def test_items_are_capped() -> None:
    log = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    memories = [_memory(f"m{index:03d}", list(log)) for index in range(40)]
    items, stats = _compute(memories)
    assert len(items) == REREAD_MAX_ITEMS
    assert stats["reread_memory_count"] == 40


# --- stats ------------------------------------------------------------------


def test_stats_count_reread_and_multi_mood_memories() -> None:
    below = [_entry(days_ago=day, mood="calm") for day in (4, 2)]
    single = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    multi = [
        _entry(days_ago=9, mood="calm"),
        _entry(days_ago=5, mood="anxious"),
        _entry(days_ago=1, mood="grateful"),
    ]
    _, stats = _compute(
        [_memory("a", below), _memory("b", single), _memory("c", multi)]
    )
    assert stats == {"reread_memory_count": 2, "reread_multi_mood_count": 1}


def test_stats_count_every_reread_memory_not_only_the_reported_ones() -> None:
    multi = [
        _entry(days_ago=9, mood="calm"),
        _entry(days_ago=5, mood="anxious"),
        _entry(days_ago=1, mood="grateful"),
    ]
    memories = [_memory(f"m{index:03d}", list(multi)) for index in range(35)]
    items, stats = _compute(memories)
    assert len(items) == REREAD_MAX_ITEMS
    assert stats == {"reread_memory_count": 35, "reread_multi_mood_count": 35}


def test_stats_reach_the_cli_log_extra() -> None:
    lens = RereadingLens()
    multi = [
        _entry(days_ago=9, mood="calm"),
        _entry(days_ago=5, mood="anxious"),
        _entry(days_ago=1, mood="grateful"),
    ]
    lens.compute(_snapshot([_memory("a", multi)]))
    assert lens_stats(lens) == {
        "reread_memory_count": 1,
        "reread_multi_mood_count": 1,
    }


def test_stats_are_reset_between_runs() -> None:
    lens = RereadingLens()
    log = [_entry(days_ago=day, mood="calm") for day in (9, 5, 1)]
    lens.compute(_snapshot([_memory("a", log)]))
    assert lens.stats["reread_memory_count"] == 1
    lens.compute(_snapshot([]))
    assert lens.stats == {"reread_memory_count": 0, "reread_multi_mood_count": 0}
