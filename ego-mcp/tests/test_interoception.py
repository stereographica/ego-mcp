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


class TestSystemLoad:
    def test_system_load_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 0.2)
        assert interoception.system_load() == "low"

    def test_system_load_medium(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 0.8)
        assert interoception.system_load() == "medium"

    def test_system_load_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 1.5)
        assert interoception.system_load() == "high"


class TestGetBodyState:
    def test_all_time_phases_via_get_body_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercise the time_phase() call inside get_body_state for various hours."""
        from unittest.mock import MagicMock

        from ego_mcp import timezone_utils as tz

        # Simulate psutil available with boot_time
        mock_psutil = MagicMock()
        mock_psutil.boot_time.return_value = 1000.0
        monkeypatch.setattr(interoception, "psutil", mock_psutil)
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 0.1)

        phases_seen: set[str] = set()
        for hour in (2, 5, 8, 14, 18, 22):
            monkeypatch.setattr(tz, "now", lambda _h=hour: datetime(2026, 3, 15, _h, 30, 0))
            state = interoception.get_body_state()
            phases_seen.add(state["time_phase"])
            assert "system_load" in state
            assert "uptime_hours" in state

        assert phases_seen == {
            "late_night",
            "early_morning",
            "morning",
            "afternoon",
            "evening",
            "night",
        }

    def test_get_body_state_psutil_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When psutil.boot_time() raises, uptime_hours falls back to 0.0."""
        from unittest.mock import MagicMock

        mock_psutil = MagicMock()
        mock_psutil.boot_time.side_effect = RuntimeError("fail")
        monkeypatch.setattr(interoception, "psutil", mock_psutil)
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 0.1)

        state = interoception.get_body_state()
        assert state["uptime_hours"] == "0.0"

    def test_get_body_state_no_psutil(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When psutil is None, uptime_hours is 0.0."""
        monkeypatch.setattr(interoception, "psutil", None)
        monkeypatch.setattr(interoception, "_load_ratio", lambda: 0.1)

        state = interoception.get_body_state()
        assert state["uptime_hours"] == "0.0"
