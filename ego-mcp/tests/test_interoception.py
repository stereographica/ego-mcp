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
