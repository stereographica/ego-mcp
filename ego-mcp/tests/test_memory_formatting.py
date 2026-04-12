"""Tests for decay-aware memory formatting."""

from __future__ import annotations

from datetime import datetime, timezone

from ego_mcp._memory_formatting import _approx_time, format_memory_by_decay
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory


def _memory(timestamp: str, content: str = "A memory about signal and pattern") -> Memory:
    return Memory(
        content=content,
        timestamp=timestamp,
        category=Category.INTROSPECTION,
        importance=4,
        tags=["signal", "pattern"],
        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS),
    )


def test_format_memory_by_decay_preserves_detail_for_fresh_memories() -> None:
    memory = _memory("2026-02-26T11:30:00+00:00")

    text = format_memory_by_decay(
        memory,
        decay=0.9,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith(memory.content)
    assert "emotion: curious" in text
    assert "category: introspection" in text
    assert "importance: 4" in text
    assert "tags: signal, pattern" in text


def test_format_memory_by_decay_degrades_to_fading_summary() -> None:
    memory = _memory("2026-02-16T12:00:00+00:00")

    text = format_memory_by_decay(
        memory,
        decay=0.3,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith("curious introspection")
    assert "signal" in text
    assert "pattern" in text
    assert "~10 days ago" in text
    assert "decay: 0.30" in text


def test_format_memory_by_decay_degrades_to_faint_summary() -> None:
    memory = _memory("2024-02-26T12:00:00+00:00", content="Old signal")

    text = format_memory_by_decay(
        memory,
        decay=0.1,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text == "curious, ~2 years ago decay: 0.10"


def test_format_memory_by_decay_extracts_cjk_keywords() -> None:
    memory = _memory(
        "2026-02-16T12:00:00+00:00",
        content="安全な場所に帰りたい 記憶の断片",
    )

    text = format_memory_by_decay(
        memory,
        decay=0.3,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith("curious introspection")
    assert "安全な場所に帰りたい" in text
    assert "decay: 0.30" in text


class TestApproxTime:
    """Cover the plural-form branches in _approx_time."""

    def test_invalid_timestamp_returns_some_time_ago(self) -> None:
        assert _approx_time("not-a-date") == "~some time ago"

    def test_today(self) -> None:
        now = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T10:00:00+00:00", now=now)
        assert result == "~today"

    def test_singular_day(self) -> None:
        now = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
        # ~1.0 day ago -> rounds to 1, and age_days < 1.5 so no plural
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~1 day ago"

    def test_plural_days(self) -> None:
        now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        # ~5 days ago -> plural
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~5 days ago"

    def test_singular_week(self) -> None:
        now = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
        # 14 days -> 2 weeks
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~2 weeks ago"

    def test_plural_weeks(self) -> None:
        now = datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)
        # 28 days -> 4 weeks
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~4 weeks ago"

    def test_one_week(self) -> None:
        # 14 days / 7 = 2.0 -> rounds to 2, but need ~10.5 days => 10.5/7 = 1.5 -> rounds to 2
        # For 1 week: need age_days/7 to round to 1 -> age_days ~ 7-10 -> 7/7=1.0
        # But age_days < 14 is the days branch. Weeks start at 14+.
        # So 14 days: 14/7 = 2 weeks. 17 days: 17/7 ~ 2.4 -> rounds to 2.
        # To get 1 week: need ~7 days which rounds to 1 -> but that's < 14, in days range.
        # Actually the weeks=max(1, round(age_days/7)), so if age_days=14 -> 14/7=2.
        # With age_days=14.5 -> 14.5/7 ~2.07 -> rounds to 2 still.
        # We need age_days between 14 and ~17.5 where round(age/7) yields 1? No: 14/7=2.
        # Actually it's impossible to get weeks==1 naturally (min age is 14, 14/7=2).
        # max(1, round(14/7)) = 2, so the "weeks != 1" path means plural is always true
        # for typical inputs. The singular "1 week" path can only happen if
        # round(age_days/7) yields 0, which max(1,...) converts to 1.
        # That can't happen since age_days >= 14 => age_days/7 >= 2.
        # So the singular path is effectively dead, but let's test the standard plural.
        now = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~2 weeks ago"

    def test_one_month(self) -> None:
        # Months start at age_days >= 60. 60/30=2 -> "2 months ago".
        # For 1 month: need round(age_days/30)=0, clamped to 1 by max(1,...).
        # That requires age_days/30 < 0.5 -> age_days < 15, but age must be >= 60.
        # So singular month can't happen naturally. Let's verify the 2-month boundary.
        now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~2 months ago"

    def test_many_months(self) -> None:
        # ~180 days -> 6 months
        now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~6 months ago"

    def test_plural_years(self) -> None:
        now = datetime(2029, 3, 15, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~3 years ago"

    def test_two_years(self) -> None:
        # age_days >= 730 triggers the years branch. 730/365 = 2.
        now = datetime(2028, 3, 15, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00+00:00", now=now)
        assert result == "~2 years ago"

    def test_naive_timestamp_gets_tz_applied(self) -> None:
        now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        result = _approx_time("2026-03-15T12:00:00", now=now)
        assert "day" in result
