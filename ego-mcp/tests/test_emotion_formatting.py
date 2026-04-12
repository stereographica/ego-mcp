"""Tests for _server_emotion_formatting helpers."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest

from ego_mcp._server_emotion_formatting import (
    _format_month_emotion_layer,
    _format_recent_emotion_layer,
    _format_week_emotion_layer,
    _memories_within_days,
    _parse_iso_datetime,
    _secondary_weighted_counts,
    _truncate_for_log,
    _truncate_for_quote,
    _valence_arousal_to_impression,
    configure_overrides,
)
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory

NOW = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)


def _make_memory(
    *,
    id: str = "m1",
    content: str = "a memory",
    hours_ago: float = 1.0,
    primary: Emotion = Emotion.CURIOUS,
    secondary: list[Emotion] | None = None,
    intensity: float = 0.5,
    valence: float = 0.0,
    arousal: float = 0.5,
    importance: int = 3,
) -> Memory:
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return Memory(
        id=id,
        content=content,
        timestamp=ts,
        emotional_trace=EmotionalTrace(
            primary=primary,
            secondary=secondary or [],
            intensity=intensity,
            valence=valence,
            arousal=arousal,
        ),
        category=Category.DAILY,
        importance=importance,
    )


# ---------------------------------------------------------------------------
# _parse_iso_datetime
# ---------------------------------------------------------------------------


class TestParseIsoDatetime:
    def test_valid_tz_aware(self) -> None:
        result = _parse_iso_datetime("2026-04-10T12:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_valid_naive_gets_tz(self) -> None:
        result = _parse_iso_datetime("2026-04-10T12:00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_invalid_returns_none(self) -> None:
        assert _parse_iso_datetime("not-a-date") is None

    def test_empty_returns_none(self) -> None:
        assert _parse_iso_datetime("") is None


# ---------------------------------------------------------------------------
# _memories_within_days
# ---------------------------------------------------------------------------


class TestMemoriesWithinDays:
    def test_filters_by_window(self) -> None:
        recent = _make_memory(id="r1", hours_ago=12)
        old = _make_memory(id="r2", hours_ago=200)
        result = _memories_within_days([recent, old], 3, now=NOW)
        assert len(result) == 1
        assert result[0].id == "r1"

    def test_empty_list(self) -> None:
        assert _memories_within_days([], 7, now=NOW) == []

    def test_invalid_timestamp_skipped(self) -> None:
        bad = Memory(id="bad", content="x", timestamp="garbage")
        good = _make_memory(id="g1", hours_ago=1)
        result = _memories_within_days([bad, good], 7, now=NOW)
        assert len(result) == 1
        assert result[0].id == "g1"

    def test_results_sorted_reverse_chronological(self) -> None:
        older = _make_memory(id="older", hours_ago=48)
        newer = _make_memory(id="newer", hours_ago=2)
        result = _memories_within_days([older, newer], 7, now=NOW)
        assert result[0].id == "newer"
        assert result[1].id == "older"

    def test_uses_default_now_when_none(self) -> None:
        """Ensure it doesn't crash when now=None (uses timezone_utils.now())."""
        m = _make_memory(id="x", hours_ago=0.5)
        # Should not raise; just check it runs
        _memories_within_days([m], 1)


# ---------------------------------------------------------------------------
# _secondary_weighted_counts
# ---------------------------------------------------------------------------


class TestSecondaryWeightedCounts:
    def test_counts_secondary_emotions(self) -> None:
        m1 = _make_memory(
            id="a", primary=Emotion.HAPPY, secondary=[Emotion.NOSTALGIC, Emotion.CALM]
        )
        m2 = _make_memory(id="b", primary=Emotion.HAPPY, secondary=[Emotion.NOSTALGIC])
        result = _secondary_weighted_counts([m1, m2])
        assert result["nostalgic"] == pytest.approx(0.8)
        assert result["calm"] == pytest.approx(0.4)

    def test_no_secondary(self) -> None:
        m = _make_memory(id="a")
        assert _secondary_weighted_counts([m]) == {}


# ---------------------------------------------------------------------------
# _valence_arousal_to_impression
# ---------------------------------------------------------------------------


class TestValenceArousalToImpression:
    def test_high_valence_high_arousal(self) -> None:
        assert _valence_arousal_to_impression(0.5, 0.7) == "an energetic, fulfilling month"

    def test_high_valence_low_arousal(self) -> None:
        assert _valence_arousal_to_impression(0.5, 0.3) == "a quietly content month"

    def test_low_valence_high_arousal(self) -> None:
        assert _valence_arousal_to_impression(-0.5, 0.7) == "a turbulent, unsettled month"

    def test_low_valence_low_arousal(self) -> None:
        assert _valence_arousal_to_impression(-0.5, 0.3) == "a heavy, draining month"

    def test_neutral_valence_low_arousal(self) -> None:
        assert _valence_arousal_to_impression(0.0, 0.2) == "a numb, uneventful month"

    def test_mixed_feelings(self) -> None:
        # Neutral valence, moderate arousal -> falls through to mixed
        assert _valence_arousal_to_impression(0.1, 0.6) == "a month of mixed feelings"


# ---------------------------------------------------------------------------
# _truncate_for_quote / _truncate_for_log
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_truncate_for_quote_short_text(self) -> None:
        assert _truncate_for_quote("hello") == "hello"

    def test_truncate_for_quote_long_text(self) -> None:
        text = "a" * 250
        result = _truncate_for_quote(text)
        assert result.endswith("...")
        assert len(result) <= 220

    def test_truncate_for_log_short_text(self) -> None:
        text, truncated = _truncate_for_log("short text")
        assert text == "short text"
        assert truncated is False

    def test_truncate_for_log_long_text(self) -> None:
        text = "b" * 1500
        result, truncated = _truncate_for_log(text)
        assert result.endswith("...")
        assert truncated is True


# ---------------------------------------------------------------------------
# _format_recent_emotion_layer
# ---------------------------------------------------------------------------


class TestFormatRecentEmotionLayer:
    @pytest.fixture(autouse=True)
    def _override_time(self) -> Generator[None, None, None]:
        configure_overrides(
            relative_time=lambda ts, now: "1h ago",
            calculate_time_decay_fn=lambda *a, **kw: 0.9,
        )
        yield
        configure_overrides()

    def test_empty_memories(self) -> None:
        result = _format_recent_emotion_layer([], NOW)
        assert "No recent emotional events" in result

    def test_single_memory(self) -> None:
        m = _make_memory(id="x1", content="felt curious", hours_ago=10)
        result = _format_recent_emotion_layer([m], NOW)
        assert "felt curious" in result
        assert "peak intensity" in result

    def test_multiple_memories_peak_selection(self) -> None:
        """Peak memory should be included even if not in top 3 by recency."""
        memories = [
            _make_memory(id="r1", content="one", hours_ago=2, intensity=0.3),
            _make_memory(id="r2", content="two", hours_ago=4, intensity=0.2),
            _make_memory(id="r3", content="three", hours_ago=6, intensity=0.1),
            _make_memory(id="peak", content="peak moment", hours_ago=50, intensity=0.99),
        ]
        result = _format_recent_emotion_layer(memories, NOW)
        assert "peak moment" in result
        assert "peak intensity 1.0" in result

    def test_secondary_undercurrent_shown(self) -> None:
        m = _make_memory(
            id="s1",
            content="complex feeling",
            hours_ago=5,
            secondary=[Emotion.NOSTALGIC],
        )
        result = _format_recent_emotion_layer([m], NOW)
        assert "undercurrent: nostalgic" in result


# ---------------------------------------------------------------------------
# _format_week_emotion_layer
# ---------------------------------------------------------------------------


class TestFormatWeekEmotionLayer:
    @pytest.fixture(autouse=True)
    def _override_time(self) -> Generator[None, None, None]:
        configure_overrides(
            relative_time=lambda ts, now: "2d ago",
            calculate_time_decay_fn=lambda *a, **kw: 0.8,
        )
        yield
        configure_overrides()

    def test_empty_memories(self) -> None:
        result = _format_week_emotion_layer([], NOW)
        assert "Not enough recent data" in result

    def test_dominant_emotions(self) -> None:
        memories = [
            _make_memory(id=f"d{i}", hours_ago=24 * (i + 1), primary=Emotion.HAPPY)
            for i in range(4)
        ] + [
            _make_memory(id="s1", hours_ago=30, primary=Emotion.SAD),
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "happy" in result.lower()

    def test_secondary_undercurrents(self) -> None:
        memories = [
            _make_memory(
                id=f"u{i}",
                hours_ago=24 * (i + 1),
                primary=Emotion.CALM,
                secondary=[Emotion.ANXIOUS],
            )
            for i in range(3)
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "anxious" in result.lower()

    def test_transition_first_last_differ(self) -> None:
        memories = [
            _make_memory(id="first", hours_ago=140, primary=Emotion.SAD),
            _make_memory(id="last", hours_ago=5, primary=Emotion.HAPPY),
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "started sad" in result.lower()
        assert "settled into happy" in result.lower()

    def test_no_transition_when_same_emotion(self) -> None:
        memories = [
            _make_memory(id="a", hours_ago=100, primary=Emotion.CALM),
            _make_memory(id="b", hours_ago=5, primary=Emotion.CALM),
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "started" not in result.lower()

    def test_cluster_detection_three_consecutive(self) -> None:
        """Three+ consecutive same-emotion memories trigger cluster note."""
        memories = [
            _make_memory(id="c1", hours_ago=100, primary=Emotion.ANXIOUS),
            _make_memory(id="c2", hours_ago=80, primary=Emotion.ANXIOUS),
            _make_memory(id="c3", hours_ago=60, primary=Emotion.ANXIOUS),
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "recurring note of anxious" in result.lower()

    def test_no_cluster_when_only_two_consecutive(self) -> None:
        memories = [
            _make_memory(id="c1", hours_ago=100, primary=Emotion.ANXIOUS),
            _make_memory(id="c2", hours_ago=80, primary=Emotion.ANXIOUS),
            _make_memory(id="c3", hours_ago=60, primary=Emotion.HAPPY),
        ]
        result = _format_week_emotion_layer(memories, NOW)
        assert "recurring note" not in result.lower()


# ---------------------------------------------------------------------------
# _format_month_emotion_layer
# ---------------------------------------------------------------------------


class TestFormatMonthEmotionLayer:
    @pytest.fixture(autouse=True)
    def _override_time(self) -> Generator[None, None, None]:
        configure_overrides(
            relative_time=lambda ts, now: "5d ago",
            calculate_time_decay_fn=lambda *a, **kw: 0.3,
        )
        yield
        configure_overrides()

    def test_empty_memories(self) -> None:
        result = _format_month_emotion_layer([], NOW)
        assert "not enough monthly data" in result.lower()

    def test_tone_description_present(self) -> None:
        memories = [
            _make_memory(
                id=f"t{i}",
                hours_ago=24 * (i + 1),
                primary=Emotion.EXCITED,
                valence=0.5,
                arousal=0.7,
                intensity=0.6,
            )
            for i in range(5)
        ]
        result = _format_month_emotion_layer(memories, NOW)
        assert "Tone:" in result
        assert "energetic, fulfilling month" in result

    def test_peak_and_end_memories(self) -> None:
        low = _make_memory(id="low", hours_ago=72, content="mundane day", intensity=0.2)
        high = _make_memory(id="high", hours_ago=48, content="incredible event", intensity=0.95)
        recent = _make_memory(id="end", hours_ago=12, content="calming end")
        result = _format_month_emotion_layer([low, high, recent], NOW)
        assert "Peak:" in result
        assert "incredible event" in result
        assert "End:" in result
        assert "calming end" in result

    def test_fading_emotion_detected(self) -> None:
        """Emotion present in month but absent from last 7 days should be marked fading."""
        # Old memories (>7 days ago) with SAD
        old_sad = [
            _make_memory(
                id=f"os{i}",
                hours_ago=24 * (10 + i),
                primary=Emotion.SAD,
                intensity=0.5,
            )
            for i in range(4)
        ]
        # Recent memories (<7 days) with HAPPY only
        recent_happy = [
            _make_memory(
                id=f"rh{i}",
                hours_ago=24 * (i + 1),
                primary=Emotion.HAPPY,
                intensity=0.5,
            )
            for i in range(3)
        ]
        result = _format_month_emotion_layer(old_sad + recent_happy, NOW)
        assert "fading" in result.lower()
        assert "sad" in result.lower()

    def test_no_fading_when_emotion_still_recent(self) -> None:
        """If the emotion is still in the recent week, no fading line."""
        memories = [
            _make_memory(
                id=f"x{i}",
                hours_ago=24 * (i + 1),
                primary=Emotion.HAPPY,
                intensity=0.5,
            )
            for i in range(5)
        ]
        result = _format_month_emotion_layer(memories, NOW)
        assert "fading" not in result.lower()

    def test_fading_not_shown_when_decay_high(self) -> None:
        """If decay is above 0.5, the fading line should not appear."""
        configure_overrides(
            relative_time=lambda ts, now: "10d ago",
            calculate_time_decay_fn=lambda *a, **kw: 0.8,
        )
        old_sad = [
            _make_memory(
                id=f"os{i}",
                hours_ago=24 * (10 + i),
                primary=Emotion.SAD,
                intensity=0.5,
            )
            for i in range(4)
        ]
        recent_happy = [
            _make_memory(
                id=f"rh{i}",
                hours_ago=24 * (i + 1),
                primary=Emotion.HAPPY,
                intensity=0.5,
            )
            for i in range(3)
        ]
        result = _format_month_emotion_layer(old_sad + recent_happy, NOW)
        assert "fading" not in result.lower()


# ---------------------------------------------------------------------------
# _relative_time (indirect via _call_relative_time without override)
# ---------------------------------------------------------------------------


class TestRelativeTimeDefault:
    """Test _relative_time through the no-override path."""

    @pytest.fixture(autouse=True)
    def _clear_overrides(self) -> Generator[None, None, None]:
        configure_overrides()
        yield
        configure_overrides()

    def test_no_override_calls_real_relative_time(self) -> None:
        from ego_mcp._server_emotion_formatting import _call_relative_time

        result = _call_relative_time(
            (NOW - timedelta(hours=2)).isoformat(),
            now=NOW,
        )
        assert "2h ago" == result

    def test_invalid_timestamp(self) -> None:
        from ego_mcp._server_emotion_formatting import _relative_time

        assert _relative_time("not-a-date", now=NOW) == "unknown time"

    def test_naive_timestamp_gets_tz(self) -> None:
        from ego_mcp._server_emotion_formatting import _relative_time

        result = _relative_time("2026-04-10T11:59:00", now=NOW)
        # Should produce "1m ago" or "just now" depending on tz
        assert result  # non-empty

    def test_naive_now_gets_tz(self) -> None:
        from ego_mcp._server_emotion_formatting import _relative_time

        naive_now = datetime(2026, 4, 10, 12, 0, 0)
        result = _relative_time(
            "2026-04-10T11:00:00+00:00",
            now=naive_now,
        )
        assert "ago" in result or result == "just now"


# ---------------------------------------------------------------------------
# _call_calculate_time_decay without override
# ---------------------------------------------------------------------------


class TestCallCalculateTimeDecayNoOverride:
    @pytest.fixture(autouse=True)
    def _clear_overrides(self) -> Generator[None, None, None]:
        configure_overrides()
        yield
        configure_overrides()

    def test_no_override_calls_real_decay(self) -> None:
        from ego_mcp._server_emotion_formatting import _call_calculate_time_decay

        ts = (NOW - timedelta(days=1)).isoformat()
        result = _call_calculate_time_decay(ts, now=NOW)
        assert 0.0 < result <= 1.0

    def test_override_is_used(self) -> None:
        from ego_mcp._server_emotion_formatting import _call_calculate_time_decay

        configure_overrides(calculate_time_decay_fn=lambda *a, **kw: 0.42)
        ts = NOW.isoformat()
        assert _call_calculate_time_decay(ts, now=NOW) == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# _format_recall_entry edge cases
# ---------------------------------------------------------------------------


class TestFormatRecallEntry:
    @pytest.fixture(autouse=True)
    def _override_time(self) -> Generator[None, None, None]:
        configure_overrides(
            relative_time=lambda ts, now: "3h ago",
            calculate_time_decay_fn=lambda *a, **kw: 0.9,
        )
        yield
        configure_overrides()

    def test_default_now_used_when_none(self) -> None:
        from ego_mcp._server_emotion_formatting import _format_recall_entry
        from ego_mcp.types import MemorySearchResult

        m = _make_memory(id="r1", content="test content", hours_ago=1)
        result_obj = MemorySearchResult(memory=m, score=0.75, decay=0.85)
        text = _format_recall_entry(1, result_obj)
        assert "test content" in text or "1." in text

    def test_empty_formatted_uses_truncated_content(self) -> None:
        from ego_mcp._server_emotion_formatting import _format_recall_entry
        from ego_mcp.types import MemorySearchResult

        m = _make_memory(id="r2", content="short note", hours_ago=1)
        result_obj = MemorySearchResult(memory=m, score=0.5, decay=0.05)
        text = _format_recall_entry(1, result_obj, now=NOW)
        assert "1." in text
        assert "score: 0.50" in text
