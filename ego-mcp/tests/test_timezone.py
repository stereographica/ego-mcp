"""Tests for timezone_utils helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ego_mcp import timezone_utils


class TestAppTimezone:
    def test_invalid_timezone_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EGO_MCP_TIMEZONE", "Not/A/Valid/Timezone")
        with pytest.raises(ValueError, match="Invalid timezone"):
            timezone_utils.app_timezone()


class TestLocalize:
    def test_naive_datetime_gets_configured_tz(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EGO_MCP_TIMEZONE", "UTC")
        naive = datetime(2026, 6, 15, 12, 0, 0)
        result = timezone_utils.localize(naive)
        assert result.tzinfo is not None
        assert result.hour == 12

    def test_aware_datetime_converted_to_configured_tz(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EGO_MCP_TIMEZONE", "Asia/Tokyo")
        utc_dt = datetime(2026, 6, 15, 3, 0, 0, tzinfo=timezone.utc)
        result = timezone_utils.localize(utc_dt)
        # UTC 03:00 -> JST 12:00
        assert result.hour == 12
