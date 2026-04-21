"""Tests for interoception helpers."""

from __future__ import annotations

from datetime import datetime

import pytest

from ego_mcp import interoception


class TestTimePhase:
    @pytest.mark.parametrize(
        ("hour", "expected"),
        [
            (2, "late_night"),
            (5, "early_morning"),
            (8, "morning"),
            (14, "afternoon"),
            (18, "evening"),
            (22, "night"),
        ],
    )
    def test_time_phase(self, hour: int, expected: str) -> None:
        now = datetime(2026, 2, 20, hour, 0, 0)
        assert interoception.time_phase(now) == expected


class TestGetBodyState:
    def test_all_time_phases_via_get_body_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercise the time_phase() call inside get_body_state for various hours."""
        from ego_mcp import timezone_utils as tz

        phases_seen: set[str] = set()
        for hour in (2, 5, 8, 14, 18, 22):
            monkeypatch.setattr(tz, "now", lambda _h=hour: datetime(2026, 3, 15, _h, 30, 0))
            state = interoception.get_body_state()
            phases_seen.add(state["time_phase"])
            assert set(state.keys()) == {"time_phase"}

        assert phases_seen == {
            "late_night",
            "early_morning",
            "morning",
            "afternoon",
            "evening",
            "night",
        }
