"""Tests for derived/affect.py (P2 S1) — the lens side only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ego_mcp.derived.affect import (
    AFFECT_TTL_HOURS,
    AffectLens,
    arousal_direction,
    valence_direction,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import EmotionalTrace, Memory

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)
TODAY = NOW.date().isoformat()


def _memory(
    memory_id: str,
    *,
    age_days: float,
    persons: list[str],
    valence: float = 0.0,
    arousal: float = 0.5,
    is_private: bool = False,
    timestamp: str | None = None,
) -> Memory:
    stamp = (
        timestamp
        if timestamp is not None
        else (NOW - timedelta(days=age_days)).isoformat()
    )
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=stamp,
        emotional_trace=EmotionalTrace(valence=valence, arousal=arousal),
        involved_person_ids=list(persons),
        is_private=is_private,
    )


def _snapshot(
    memories: list[Memory],
    relationships: dict[str, dict[str, Any]] | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=None,
        notions=[],
        question_log=[],
        relationships=(
            relationships if relationships is not None else {"p1": {"name": "P1"}}
        ),
        surfaced={},
        co_retrievals=[],
    )


def _window(
    person: str,
    *,
    prefix: str,
    count: int,
    age_days: float,
    valence: float = 0.0,
    arousal: float = 0.5,
) -> list[Memory]:
    """``count`` memories shared with ``person``, all at the same age."""
    return [
        _memory(
            f"{prefix}{index}",
            age_days=age_days,
            persons=[person],
            valence=valence,
            arousal=arousal,
        )
        for index in range(count)
    ]


def _compute(
    memories: list[Memory],
    relationships: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return AffectLens().compute(_snapshot(memories, relationships))


def _balanced(
    person: str = "p1",
    *,
    recent_valence: float = 0.0,
    prior_valence: float = 0.0,
    recent_arousal: float = 0.5,
    prior_arousal: float = 0.5,
    n_recent: int = 4,
    n_prior: int = 4,
) -> list[Memory]:
    """A person with full windows on both sides."""
    return _window(
        person,
        prefix=f"{person}r",
        count=n_recent,
        age_days=10,
        valence=recent_valence,
        arousal=recent_arousal,
    ) + _window(
        person,
        prefix=f"{person}p",
        count=n_prior,
        age_days=60,
        valence=prior_valence,
        arousal=prior_arousal,
    )


# --- lens metadata ----------------------------------------------------------


def test_lens_metadata() -> None:
    lens = AffectLens()
    assert lens.name == "affect"
    assert lens.needs_embeddings is False
    assert lens.ttl_hours == AFFECT_TTL_HOURS == 168.0


# --- direction thresholds ---------------------------------------------------


def test_valence_direction_boundaries() -> None:
    assert valence_direction(0.20) == "brighter"
    assert valence_direction(0.199) == "steady"
    assert valence_direction(0.0) == "steady"
    assert valence_direction(-0.199) == "steady"
    assert valence_direction(-0.20) == "darker"


def test_arousal_direction_boundaries() -> None:
    assert arousal_direction(0.15) == "livelier"
    assert arousal_direction(0.149) == "steady"
    assert arousal_direction(0.0) == "steady"
    assert arousal_direction(-0.149) == "steady"
    assert arousal_direction(-0.15) == "quieter"


def test_compute_valence_at_the_step_is_brighter() -> None:
    # 0.5 - 0.3 is 0.19999999999999996 in binary floating point; the lens
    # rounds before thresholding, so the exact step still counts.
    items = _compute(_balanced(recent_valence=0.5, prior_valence=0.3))
    assert [(item["dv"], item["valence_direction"]) for item in items] == [
        (0.2, "brighter")
    ]


def test_compute_valence_just_below_the_step_is_steady() -> None:
    items = _compute(_balanced(recent_valence=0.499, prior_valence=0.3))
    assert items[0]["dv"] == 0.199
    assert items[0]["valence_direction"] == "steady"


def test_compute_valence_at_the_negative_step_is_darker() -> None:
    items = _compute(_balanced(recent_valence=-0.3, prior_valence=-0.1))
    assert items[0]["dv"] == -0.2
    assert items[0]["valence_direction"] == "darker"


def test_compute_arousal_at_the_step_is_livelier() -> None:
    items = _compute(_balanced(recent_arousal=0.65, prior_arousal=0.5))
    assert items[0]["da"] == 0.15
    assert items[0]["arousal_direction"] == "livelier"


def test_compute_arousal_just_below_the_step_is_steady() -> None:
    items = _compute(_balanced(recent_arousal=0.649, prior_arousal=0.5))
    assert items[0]["da"] == 0.149
    assert items[0]["arousal_direction"] == "steady"


def test_compute_arousal_at_the_negative_step_is_quieter() -> None:
    items = _compute(_balanced(recent_arousal=0.35, prior_arousal=0.5))
    assert items[0]["da"] == -0.15
    assert items[0]["arousal_direction"] == "quieter"


def test_both_steady_person_is_still_emitted() -> None:
    items = _compute(_balanced(recent_valence=0.1, prior_valence=0.0))
    assert len(items) == 1
    assert items[0]["valence_direction"] == "steady"
    assert items[0]["arousal_direction"] == "steady"
    assert items[0]["dv"] == 0.1
    assert items[0]["da"] == 0.0


# --- window split -----------------------------------------------------------


def test_age_exactly_thirty_days_belongs_to_the_prior_window() -> None:
    memories = _window("p1", prefix="r", count=4, age_days=29.9, valence=0.5) + _window(
        "p1", prefix="p", count=4, age_days=30, valence=0.0
    )
    items = _compute(memories)
    assert items[0]["n_recent"] == 4
    assert items[0]["n_prior"] == 4
    assert items[0]["dv"] == 0.5


def test_age_just_under_thirty_days_belongs_to_the_recent_window() -> None:
    # Everything lands in "recent": the prior window is empty, so no judgement.
    memories = _window("p1", prefix="a", count=8, age_days=29.999)
    assert _compute(memories) == []


def test_age_exactly_one_hundred_twenty_days_is_outside_both_windows() -> None:
    memories = _window("p1", prefix="r", count=4, age_days=10) + _window(
        "p1", prefix="p", count=4, age_days=120
    )
    assert _compute(memories) == []


def test_age_just_under_one_hundred_twenty_days_is_prior() -> None:
    memories = _window("p1", prefix="r", count=4, age_days=10) + _window(
        "p1", prefix="p", count=4, age_days=119.999
    )
    items = _compute(memories)
    assert items[0]["n_prior"] == 4


def test_unusable_timestamp_is_excluded_from_both_windows() -> None:
    memories = _balanced() + [
        _memory("broken", age_days=0, persons=["p1"], timestamp="not-a-date"),
        _memory("blank", age_days=0, persons=["p1"], timestamp=""),
    ]
    items = _compute(memories)
    assert items[0]["n_recent"] == 4
    assert items[0]["n_prior"] == 4


# --- count conditions -------------------------------------------------------


def test_too_few_recent_memories_are_not_judged() -> None:
    assert _compute(_balanced(n_recent=3)) == []


def test_too_few_prior_memories_are_not_judged() -> None:
    assert _compute(_balanced(n_prior=3)) == []


def test_exactly_four_in_each_window_is_judged() -> None:
    items = _compute(_balanced(n_recent=4, n_prior=4))
    assert len(items) == 1
    assert (items[0]["n_recent"], items[0]["n_prior"]) == (4, 4)


def test_no_shared_memories_at_all_is_not_judged() -> None:
    assert _compute(_balanced("p2"), {"p1": {"name": "P1"}}) == []


# --- interlocutor filter ----------------------------------------------------


def test_mentioned_person_is_excluded() -> None:
    items = _compute(_balanced("p1"), {"p1": {"relation_kind": "mentioned"}})
    assert items == []


def test_missing_relation_kind_counts_as_interlocutor() -> None:
    items = _compute(_balanced("p1"), {"p1": {"name": "P1"}})
    assert [item["person_id"] for item in items] == ["p1"]


def test_explicit_interlocutor_is_included() -> None:
    items = _compute(_balanced("p1"), {"p1": {"relation_kind": "interlocutor"}})
    assert [item["person_id"] for item in items] == ["p1"]


def test_person_without_a_relationship_model_is_not_judged() -> None:
    items = _compute(_balanced("ghost"), {"p1": {"name": "P1"}})
    assert items == []


# --- item shape -------------------------------------------------------------


def test_key_format_and_item_fields() -> None:
    items = _compute(_balanced(recent_valence=0.5, prior_valence=0.3))
    assert items[0] == {
        "key": f"affect:p1:{TODAY}",
        "person_id": "p1",
        "dv": 0.2,
        "da": 0.0,
        "valence_direction": "brighter",
        "arousal_direction": "steady",
        "n_recent": 4,
        "n_prior": 4,
    }


def test_values_are_rounded_to_three_decimals() -> None:
    memories = _window("p1", prefix="r", count=4, age_days=10, valence=0.1234567) + (
        _window("p1", prefix="p", count=4, age_days=60, valence=0.0)
    )
    assert _compute(memories)[0]["dv"] == 0.123


def test_items_are_sorted_by_person_id() -> None:
    memories = _balanced("pb") + _balanced("pa") + _balanced("pc")
    relationships: dict[str, dict[str, Any]] = {"pc": {}, "pa": {}, "pb": {}}
    items = _compute(memories, relationships)
    assert [item["person_id"] for item in items] == ["pa", "pb", "pc"]


def test_private_memories_are_included() -> None:
    memories = _balanced() + [
        _memory("secret", age_days=5, persons=["p1"], valence=0.8, is_private=True)
    ]
    items = _compute(memories)
    assert items[0]["n_recent"] == 5
    assert items[0]["dv"] == 0.16


def test_shared_memory_counts_for_every_person_involved() -> None:
    memories = [
        _memory(f"m{index}", age_days=10, persons=["p1", "p2"], valence=0.4)
        for index in range(4)
    ] + [
        _memory(f"o{index}", age_days=60, persons=["p1", "p2"], valence=0.0)
        for index in range(4)
    ]
    items = _compute(memories, {"p1": {}, "p2": {}})
    assert [(item["person_id"], item["dv"]) for item in items] == [
        ("p1", 0.4),
        ("p2", 0.4),
    ]
