"""Tests for derived/recurrence.py (D1 S1)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from ego_mcp.derived.lenses import Lens
from ego_mcp.derived.recurrence import (
    LENS_NAME,
    RECURRENCE_HORIZON_DAYS,
    RECURRENCE_MAX_PER_DATE,
    RECURRENCE_TTL_HOURS,
    RecurrenceLens,
    _calendar_matches,
    _eligible,
    _score,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import EmotionalTrace, Memory

NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 16)


@pytest.fixture(autouse=True)
def _utc_timezone(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "UTC")
    yield


def _memory(
    memory_id: str,
    when: datetime | None,
    *,
    importance: int = 4,
    intensity: float = 0.5,
    people: Sequence[str] = (),
    anticipated_at: str = "",
) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp="" if when is None else when.isoformat(),
        importance=importance,
        emotional_trace=EmotionalTrace(intensity=intensity),
        involved_person_ids=list(people),
        anticipated_at=anticipated_at,
    )


def _at(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)


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


def _items_on(items: list[dict[str, Any]], on_date: date) -> list[dict[str, Any]]:
    return [item for item in items if item["on_date"] == on_date.isoformat()]


# --- _calendar_matches ------------------------------------------------------


def test_calendar_matches_one_year() -> None:
    assert _calendar_matches(date(2025, 9, 16), date(2026, 9, 16)) == ("year", 1)


def test_calendar_matches_several_years() -> None:
    assert _calendar_matches(date(2023, 9, 16), date(2026, 9, 16)) == ("year", 3)


def test_calendar_matches_same_year_is_not_a_recurrence() -> None:
    assert _calendar_matches(date(2026, 9, 16), date(2026, 9, 16)) is None


def test_calendar_matches_future_memory_is_not_a_recurrence() -> None:
    assert _calendar_matches(date(2027, 9, 16), date(2026, 9, 16)) is None


def test_calendar_matches_neighbouring_day_is_not_a_recurrence() -> None:
    assert _calendar_matches(date(2025, 9, 15), date(2026, 9, 16)) is None


def test_calendar_matches_leap_day_falls_on_the_28th_in_a_common_year() -> None:
    assert _calendar_matches(date(2024, 2, 29), date(2025, 2, 28)) == ("year", 1)
    assert _calendar_matches(date(2024, 2, 29), date(2025, 3, 1)) is None


def test_calendar_matches_leap_day_keeps_the_29th_in_a_leap_year() -> None:
    assert _calendar_matches(date(2024, 2, 29), date(2028, 2, 29)) == ("year", 4)
    assert _calendar_matches(date(2024, 2, 29), date(2028, 2, 28)) is None


def test_calendar_matches_28th_does_not_slide_onto_the_leap_day() -> None:
    assert _calendar_matches(date(2023, 2, 28), date(2024, 2, 29)) is None
    assert _calendar_matches(date(2023, 2, 28), date(2024, 2, 28)) == ("year", 1)


def test_calendar_matches_half_year() -> None:
    assert _calendar_matches(date(2026, 3, 16), date(2026, 9, 16)) == ("half_year", 1)


def test_calendar_matches_half_year_clamps_to_the_month_end() -> None:
    assert _calendar_matches(date(2026, 8, 31), date(2027, 2, 28)) == ("half_year", 1)
    assert _calendar_matches(date(2025, 10, 31), date(2026, 4, 30)) == ("half_year", 1)
    assert _calendar_matches(date(2026, 8, 31), date(2027, 3, 3)) is None


def test_calendar_matches_half_year_across_the_year_end() -> None:
    assert _calendar_matches(date(2025, 12, 16), date(2026, 6, 16)) == ("half_year", 1)


def test_calendar_matches_prefers_year_over_half_year() -> None:
    # An anniversary is never reported as a half-year echo.
    for years in (1, 2, 5):
        match = _calendar_matches(date(2026 - years, 9, 16), date(2026, 9, 16))
        assert match == ("year", years)


# --- _eligible --------------------------------------------------------------


def test_eligible_importance_gate() -> None:
    assert _eligible(_memory("a", _at(TODAY), importance=4), NOW) is True
    assert _eligible(_memory("a", _at(TODAY), importance=5), NOW) is True
    assert _eligible(_memory("a", _at(TODAY), importance=3), NOW) is False


def test_eligible_person_gate() -> None:
    low = _memory("a", _at(TODAY), importance=3, intensity=0.6, people=["p1"])
    assert _eligible(low, NOW) is True
    just_under = _memory("a", _at(TODAY), importance=3, intensity=0.59, people=["p1"])
    assert _eligible(just_under, NOW) is False


def test_eligible_person_gate_needs_a_person() -> None:
    strong_alone = _memory("a", _at(TODAY), importance=3, intensity=0.95)
    assert _eligible(strong_alone, NOW) is False


def test_eligible_excludes_unarrived_anticipation() -> None:
    future = _memory(
        "a",
        _at(TODAY),
        importance=5,
        anticipated_at=(NOW + timedelta(days=3)).isoformat(),
    )
    assert _eligible(future, NOW) is False


def test_eligible_keeps_arrived_anticipation() -> None:
    arrived = _memory(
        "a",
        _at(TODAY),
        importance=5,
        anticipated_at=(NOW - timedelta(days=3)).isoformat(),
    )
    assert _eligible(arrived, NOW) is True


# --- _score -----------------------------------------------------------------


def test_score_combines_importance_intensity_and_company() -> None:
    memory = _memory("a", _at(TODAY), importance=4, intensity=0.6, people=["p1"])
    assert _score(memory) == pytest.approx(0.8 + 0.3 + 0.3)


def test_score_without_people_has_no_bonus() -> None:
    memory = _memory("a", _at(TODAY), importance=5, intensity=0.0)
    assert _score(memory) == pytest.approx(1.0)


# --- RecurrenceLens ---------------------------------------------------------


def test_lens_satisfies_the_protocol() -> None:
    lens: Lens = RecurrenceLens()
    assert lens.name == LENS_NAME == "recurrence"
    assert lens.needs_embeddings is False
    assert lens.ttl_hours == RECURRENCE_TTL_HOURS


def test_compute_covers_the_whole_horizon_and_no_further() -> None:
    memories = [
        _memory(f"m{offset}", _at(date(2025, 9, 16) + timedelta(days=offset)))
        for offset in range(RECURRENCE_HORIZON_DAYS + 2)
    ]
    items = RecurrenceLens().compute(_snapshot(memories))
    on_dates = [item["on_date"] for item in items]
    assert on_dates == [
        (TODAY + timedelta(days=offset)).isoformat()
        for offset in range(RECURRENCE_HORIZON_DAYS + 1)
    ]
    assert (TODAY + timedelta(days=RECURRENCE_HORIZON_DAYS + 1)).isoformat() not in (
        on_dates
    )


def test_compute_item_shape() -> None:
    memory = _memory("mem_ab12", _at(date(2025, 9, 16)), importance=4, intensity=0.4)
    items = _items_on(RecurrenceLens().compute(_snapshot([memory])), TODAY)
    assert items == [
        {
            "key": "recurrence:mem_ab12:2026-09-16",
            "memory_id": "mem_ab12",
            "on_date": "2026-09-16",
            "period": "year",
            "span": 1,
            "score": 1.0,
        }
    ]


def test_compute_half_year_item() -> None:
    memory = _memory("mem_h", _at(date(2026, 3, 16)), importance=4, intensity=0.4)
    items = _items_on(RecurrenceLens().compute(_snapshot([memory])), TODAY)
    assert items[0]["period"] == "half_year"
    assert items[0]["span"] == 1


def test_compute_puts_year_before_half_year_even_when_it_scores_lower() -> None:
    year = _memory("year", _at(date(2025, 9, 16)), importance=4, intensity=0.2)
    half = _memory(
        "half",
        _at(date(2026, 3, 16)),
        importance=5,
        intensity=1.0,
        people=["p1"],
    )
    items = _items_on(RecurrenceLens().compute(_snapshot([half, year])), TODAY)
    assert [item["memory_id"] for item in items] == ["year", "half"]
    assert items[1]["score"] > items[0]["score"]


def test_compute_orders_by_score_then_by_the_older_memory() -> None:
    strong = _memory("strong", _at(date(2025, 9, 16)), importance=5, intensity=1.0)
    older = _memory("older", _at(date(2023, 9, 16)), importance=4, intensity=0.5)
    newer = _memory("newer", _at(date(2024, 9, 16)), importance=4, intensity=0.5)
    items = _items_on(
        RecurrenceLens().compute(_snapshot([newer, older, strong])), TODAY
    )
    assert [item["memory_id"] for item in items] == ["strong", "older", "newer"]
    assert items[1]["score"] == items[2]["score"]
    assert items[1]["span"] == 3
    assert items[2]["span"] == 2


def test_compute_keeps_at_most_three_per_date() -> None:
    memories = [
        _memory(f"m{index}", _at(date(2025 - index, 9, 16)), importance=4)
        for index in range(RECURRENCE_MAX_PER_DATE + 2)
    ]
    items = _items_on(RecurrenceLens().compute(_snapshot(memories)), TODAY)
    assert len(items) == RECURRENCE_MAX_PER_DATE


def test_compute_skips_ineligible_and_unarrived_memories() -> None:
    plain = _memory("plain", _at(date(2025, 9, 16)), importance=3, intensity=0.9)
    future = _memory(
        "future",
        _at(date(2025, 9, 16)),
        importance=5,
        anticipated_at=(NOW + timedelta(days=30)).isoformat(),
    )
    kept = _memory("kept", _at(date(2025, 9, 16)), importance=4)
    items = _items_on(RecurrenceLens().compute(_snapshot([plain, future, kept])), TODAY)
    assert [item["memory_id"] for item in items] == ["kept"]


def test_compute_skips_memories_without_a_usable_timestamp() -> None:
    blank = _memory("blank", None)
    broken = Memory(id="broken", timestamp="not-a-date", importance=5)
    items = RecurrenceLens().compute(_snapshot([blank, broken]))
    assert items == []


def test_compute_is_deterministic() -> None:
    memories = [
        _memory("a", _at(date(2025, 9, 16)), importance=4),
        _memory("b", _at(date(2024, 9, 18)), importance=5, people=["p1"]),
        _memory("c", _at(date(2026, 3, 20)), importance=4, intensity=0.8),
    ]
    lens = RecurrenceLens()
    assert lens.compute(_snapshot(memories)) == lens.compute(_snapshot(memories))


def test_compute_uses_the_snapshot_moment_as_today() -> None:
    memory = _memory("m", _at(date(2024, 12, 25)), importance=4)
    snapshot = _snapshot([memory], now=datetime(2026, 12, 25, 6, tzinfo=timezone.utc))
    items = RecurrenceLens().compute(snapshot)
    assert items[0]["on_date"] == "2026-12-25"
    assert items[0]["span"] == 2


def test_compute_without_memories_is_empty() -> None:
    assert RecurrenceLens().compute(_snapshot([])) == []
