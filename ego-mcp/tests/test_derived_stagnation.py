"""Tests for derived/stagnation.py (D6 S1)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from ego_mcp.derived.graph import MemoryGraph, build_memory_graph
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.derived.stagnation import (
    STAGNATION_BAND_CIRCLING,
    STAGNATION_BAND_FLOWING,
    STAGNATION_BAND_STUCK,
    STAGNATION_CIRCLING_MIN,
    STAGNATION_MIN_MEMORIES,
    STAGNATION_MODULATION_ENABLED,
    STAGNATION_OLD_LINK_DAYS,
    STAGNATION_ROLLING_DAYS,
    STAGNATION_STUCK_MIN,
    STAGNATION_TTL_HOURS,
    STAGNATION_W,
    STAGNATION_WINDOW_DAYS,
    StagnationLens,
    band_for,
    compose_score,
    introspection_sameness,
    link_novelty,
    memory_times,
    question_births,
    theme_repetition,
)
from ego_mcp.types import Category, LinkType, Memory, MemoryLink

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=TZ)

UNIT_A = np.array([1.0, 0.0], dtype=np.float32)
UNIT_B = np.array([0.0, 1.0], dtype=np.float32)
UNIT_DIAGONAL = np.array([0.6, 0.8], dtype=np.float32)


def _memory(
    memory_id: str,
    *,
    age_days: float = 0.0,
    category: Category = Category.OBSERVATION,
    tags: list[str] | None = None,
    links: list[str] | None = None,
) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=(NOW - timedelta(days=age_days)).isoformat(),
        category=category,
        tags=list(tags or []),
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED)
            for target in (links or [])
        ],
    )


def _snapshot(
    memories: list[Memory],
    *,
    embeddings: dict[str, np.ndarray] | None = None,
    question_log: list[dict[str, Any]] | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=embeddings if embeddings is not None else {},
        notions=[],
        question_log=question_log or [],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


# --- lens identity ----------------------------------------------------------


def test_lens_identity() -> None:
    lens = StagnationLens()
    assert lens.name == "stagnation"
    assert lens.needs_embeddings is True
    assert lens.ttl_hours == STAGNATION_TTL_HOURS == 36.0
    assert STAGNATION_MODULATION_ENABLED is False
    assert STAGNATION_W == {
        "sameness": 0.35,
        "repetition": 0.35,
        "novelty": 0.20,
        "births": 0.10,
    }


# --- introspection_sameness -------------------------------------------------


def test_sameness_of_identical_introspections_is_one() -> None:
    memories = [
        _memory("i1", category=Category.INTROSPECTION, age_days=2),
        _memory("i2", category=Category.INTROSPECTION, age_days=1),
        _memory("i3", category=Category.INTROSPECTION, age_days=0),
    ]
    embeddings = {"i1": UNIT_A, "i2": UNIT_A, "i3": UNIT_A}
    assert introspection_sameness(memories, embeddings) == 1.0


def test_sameness_of_orthogonal_introspections_is_zero() -> None:
    memories = [
        _memory("i1", category=Category.INTROSPECTION, age_days=2),
        _memory("i2", category=Category.INTROSPECTION, age_days=1),
    ]
    assert introspection_sameness(memories, {"i1": UNIT_A, "i2": UNIT_B}) == 0.0


def test_sameness_uses_chronological_order() -> None:
    memories = [
        _memory("newest", category=Category.INTROSPECTION, age_days=0),
        _memory("oldest", category=Category.INTROSPECTION, age_days=2),
        _memory("middle", category=Category.INTROSPECTION, age_days=1),
    ]
    embeddings = {"oldest": UNIT_A, "middle": UNIT_DIAGONAL, "newest": UNIT_B}
    value = introspection_sameness(memories, embeddings)
    assert value is not None
    # dot(A, diagonal) = 0.6 and dot(diagonal, B) = 0.8 -> mean 0.7
    assert abs(value - 0.7) < 1e-6


def test_sameness_needs_two_introspections_with_embeddings() -> None:
    lonely = [_memory("i1", category=Category.INTROSPECTION)]
    assert introspection_sameness(lonely, {"i1": UNIT_A}) is None

    pair = [
        _memory("i1", category=Category.INTROSPECTION, age_days=1),
        _memory("i2", category=Category.INTROSPECTION),
    ]
    assert introspection_sameness(pair, {"i1": UNIT_A}) is None
    assert introspection_sameness(pair, None) is None


def test_sameness_ignores_other_categories() -> None:
    memories = [
        _memory("i1", category=Category.INTROSPECTION, age_days=1),
        _memory("d1", category=Category.DAILY),
    ]
    embeddings = {"i1": UNIT_A, "d1": UNIT_A}
    assert introspection_sameness(memories, embeddings) is None


# --- theme_repetition -------------------------------------------------------


def test_theme_repetition_rolling_window() -> None:
    memories = [
        _memory("m1", age_days=1, category=Category.TECHNICAL, tags=["rain"]),
        _memory("m2", age_days=0, category=Category.TECHNICAL, tags=["rain"]),
    ]
    # Day two repeats both themes of day one; day one had nothing before it.
    assert theme_repetition(memories, NOW) == 0.5


def test_theme_repetition_forgets_beyond_five_days() -> None:
    memories = [
        _memory("old", age_days=STAGNATION_ROLLING_DAYS + 1, tags=["rain"]),
        _memory("new", age_days=0, tags=["rain"]),
    ]
    assert theme_repetition(memories, NOW) == 0.0

    inside = [
        _memory("old", age_days=STAGNATION_ROLLING_DAYS, tags=["rain"]),
        _memory("new", age_days=0, tags=["rain"]),
    ]
    assert theme_repetition(inside, NOW) == 0.5


def test_theme_repetition_excludes_generic_categories() -> None:
    generic = [
        _memory("m1", age_days=1, category=Category.DAILY),
        _memory("m2", age_days=0, category=Category.DAILY),
        _memory("m3", age_days=1, category=Category.CONVERSATION),
        _memory("m4", age_days=0, category=Category.CONVERSATION),
    ]
    # Nothing is a theme, so there is no theme-bearing day at all.
    assert theme_repetition(generic, NOW) is None

    tagged = [
        _memory("m1", age_days=1, category=Category.DAILY, tags=["rain"]),
        _memory("m2", age_days=0, category=Category.DAILY, tags=["rain"]),
    ]
    # Only the tag counts, and it repeats on the second day.
    assert theme_repetition(tagged, NOW) == 0.5


def test_theme_repetition_partial_day() -> None:
    memories = [
        _memory("m1", age_days=1, category=Category.TECHNICAL, tags=["rain"]),
        _memory("m2", age_days=0, category=Category.TECHNICAL, tags=["rain"]),
        _memory("m3", age_days=0, category=Category.TECHNICAL, tags=["snow"]),
    ]
    # Day two is the multiset [tag:rain, category:technical, tag:snow,
    # category:technical]; three of its four entries appeared the day before.
    value = theme_repetition(memories, NOW)
    assert value is not None
    assert abs(value - (0.0 + 0.75) / 2) < 1e-6


def test_theme_repetition_without_memories_is_missing() -> None:
    assert theme_repetition([], NOW) is None


# --- link_novelty -----------------------------------------------------------


def _novelty(memories: list[Memory]) -> float | None:
    snapshot = _snapshot(memories)
    graph = build_memory_graph(snapshot)
    return link_novelty(
        memories, graph, NOW, timestamps=memory_times(snapshot.memories)
    )


def test_link_novelty_old_target_counts_as_novel() -> None:
    memories = [
        _memory("new", links=["old"]),
        _memory("old", age_days=STAGNATION_OLD_LINK_DAYS),
    ]
    assert _novelty(memories) == 1.0


def test_link_novelty_recent_target_is_not_novel() -> None:
    memories = [
        _memory("new", links=["recent"]),
        _memory("recent", age_days=STAGNATION_OLD_LINK_DAYS - 1),
    ]
    assert _novelty(memories) == 0.0


def test_link_novelty_is_missing_without_live_links() -> None:
    assert _novelty([_memory("alone")]) is None
    # Dead and self links do not count either.
    assert _novelty([_memory("alone", links=["ghost", "alone", ""])]) is None


def test_link_novelty_share() -> None:
    memories = [
        _memory("a", links=["old", "b"]),
        _memory("b"),
        _memory("old", age_days=STAGNATION_OLD_LINK_DAYS + 5),
    ]
    assert _novelty(memories) == 0.5


def test_link_novelty_counts_a_target_in_another_component_as_novel() -> None:
    # A hand-built graph where the endpoints sit in different components; with
    # a real graph an edge always joins them, so this exercises the rule only.
    graph = MemoryGraph(
        adjacency={"a": set(), "b": set()},
        degree={"a": 0, "b": 0},
        components=[{"a"}, {"b"}],
        component_of={"a": 0, "b": 1},
        notion_members={},
        notions_of_memory={},
    )
    memories = [_memory("a", links=["b"]), _memory("b")]
    times = memory_times(memories)
    assert link_novelty(memories, graph, NOW, timestamps=times) == 1.0


# --- question_births --------------------------------------------------------


def test_question_births_counts_only_the_window() -> None:
    window_start = NOW - timedelta(days=STAGNATION_WINDOW_DAYS)
    log = [
        {"created_at": (NOW - timedelta(days=1)).isoformat()},
        {"created_at": (NOW - timedelta(days=20)).isoformat()},
        {"created_at": window_start.isoformat()},
        {"created_at": ""},
        {"created_at": "not-a-date"},
        {},
    ]
    assert question_births(log, window_start) == 2


# --- compose_score / band_for -----------------------------------------------


def test_compose_score_full_stagnation() -> None:
    components: dict[str, float | None] = {
        "sameness": 1.0,
        "repetition": 1.0,
        "novelty": 0.0,
        "births": 0.0,
    }
    assert compose_score(components) == 1.0


def test_compose_score_full_flow() -> None:
    components: dict[str, float | None] = {
        "sameness": 0.0,
        "repetition": 0.0,
        "novelty": 1.0,
        "births": 3.0,
    }
    assert compose_score(components) == 0.0


def test_compose_score_weights_each_component() -> None:
    components: dict[str, float | None] = {
        "sameness": 1.0,
        "repetition": 0.0,
        "novelty": 1.0,
        "births": 1.0,
    }
    assert compose_score(components) == 0.35


def test_compose_score_redistributes_missing_components() -> None:
    components: dict[str, float | None] = {
        "sameness": None,
        "repetition": 1.0,
        "novelty": 1.0,
        "births": 2.0,
    }
    # 0.35 of a remaining 0.65 of weight.
    assert compose_score(components) == round(0.35 / 0.65, 3)

    only_births: dict[str, float | None] = {
        "sameness": None,
        "repetition": None,
        "novelty": None,
        "births": 0.0,
    }
    assert compose_score(only_births) == 1.0


def test_compose_score_without_any_component_is_zero() -> None:
    assert compose_score({"sameness": None, "births": None}) == 0.0


def test_band_boundaries() -> None:
    assert band_for(0.0) == STAGNATION_BAND_FLOWING
    assert band_for(STAGNATION_CIRCLING_MIN - 0.001) == STAGNATION_BAND_FLOWING
    assert band_for(STAGNATION_CIRCLING_MIN) == STAGNATION_BAND_CIRCLING
    assert band_for(STAGNATION_STUCK_MIN - 0.001) == STAGNATION_BAND_CIRCLING
    assert band_for(STAGNATION_STUCK_MIN) == STAGNATION_BAND_STUCK
    assert band_for(1.0) == STAGNATION_BAND_STUCK


# --- the lens ---------------------------------------------------------------


def _window_memories(count: int, **kwargs: Any) -> list[Memory]:
    return [_memory(f"m{i}", age_days=i % 10, **kwargs) for i in range(count)]


def test_lens_is_silent_below_the_minimum() -> None:
    memories = _window_memories(STAGNATION_MIN_MEMORIES - 1)
    assert StagnationLens().compute(_snapshot(memories)) == []


def test_lens_ignores_memories_outside_the_window() -> None:
    inside = _window_memories(STAGNATION_MIN_MEMORIES - 1)
    outside = [
        _memory(f"old{i}", age_days=STAGNATION_WINDOW_DAYS + 1 + i) for i in range(5)
    ]
    assert StagnationLens().compute(_snapshot(inside + outside)) == []


def test_lens_emits_one_item_with_the_expected_shape() -> None:
    memories = _window_memories(STAGNATION_MIN_MEMORIES, tags=["rain"])
    log = [{"created_at": (NOW - timedelta(days=1)).isoformat()}]
    items = StagnationLens().compute(_snapshot(memories, question_log=log))
    assert len(items) == 1
    item = items[0]
    assert set(item) == {"key", "band", "score", "components", "memory_count"}
    assert item["key"] == f"stagnation:{NOW.date().isoformat()}"
    assert item["memory_count"] == STAGNATION_MIN_MEMORIES
    assert item["band"] == band_for(item["score"])
    assert set(item["components"]) == set(STAGNATION_W)


def test_lens_components_are_floats_or_null() -> None:
    memories = _window_memories(STAGNATION_MIN_MEMORIES, tags=["rain"])
    item = StagnationLens().compute(_snapshot(memories))[0]
    components = item["components"]
    # No introspection memories and no links: both components are missing.
    assert components["sameness"] is None
    assert components["novelty"] is None
    assert isinstance(components["repetition"], float)
    assert components["births"] == 0.0
    payload = json.loads(json.dumps(item))
    assert payload["components"]["sameness"] is None


def test_lens_key_is_stable_across_runs() -> None:
    memories = _window_memories(STAGNATION_MIN_MEMORIES, tags=["rain"])
    first = StagnationLens().compute(_snapshot(memories))
    second = StagnationLens().compute(_snapshot(list(reversed(memories))))
    assert first == second


def test_lens_reports_a_stuck_loop() -> None:
    memories = [
        _memory(
            f"i{i}",
            age_days=i,
            category=Category.INTROSPECTION,
            tags=["rain"],
        )
        for i in range(STAGNATION_MIN_MEMORIES)
    ]
    embeddings = {memory.id: UNIT_A for memory in memories}
    item = StagnationLens().compute(_snapshot(memories, embeddings=embeddings))[0]
    assert item["components"]["sameness"] == 1.0
    assert item["band"] == STAGNATION_BAND_STUCK


def test_lens_reports_a_flowing_window() -> None:
    categories = [
        Category.PHILOSOPHICAL,
        Category.TECHNICAL,
        Category.MEMORY,
        Category.OBSERVATION,
        Category.FEELING,
        Category.RELATIONSHIP,
        Category.SELF_DISCOVERY,
        Category.DREAM,
    ]
    memories = [
        _memory(
            f"m{i}",
            age_days=i,
            category=categories[i],
            tags=[f"tag{i}"],
            links=["anchor"],
        )
        for i in range(STAGNATION_MIN_MEMORIES)
    ]
    memories.append(_memory("anchor", age_days=STAGNATION_OLD_LINK_DAYS + 1))
    log = [{"created_at": (NOW - timedelta(days=2)).isoformat()}]
    item = StagnationLens().compute(_snapshot(memories, question_log=log))[0]
    assert item["components"]["repetition"] == 0.0
    assert item["components"]["novelty"] == 1.0
    assert item["components"]["births"] == 1.0
    assert item["score"] == 0.0
    assert item["band"] == STAGNATION_BAND_FLOWING
