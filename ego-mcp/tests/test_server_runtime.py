"""Tests for _server_runtime module."""

from __future__ import annotations

import pytest

from ego_mcp._server_runtime import (
    clear_tool_completion_metadata,
    get_episodes,
    get_tool_metadata,
    reset_tool_metadata,
    take_tool_completion_metadata,
    update_tool_completion_metadata,
    update_tool_metadata,
)


class TestToolCompletionMetadata:
    def test_update_and_take(self) -> None:
        clear_tool_completion_metadata()
        update_tool_completion_metadata(key1="val1", key2=42)
        result = take_tool_completion_metadata()
        assert result == {"key1": "val1", "key2": 42}

    def test_take_clears(self) -> None:
        clear_tool_completion_metadata()
        update_tool_completion_metadata(x=1)
        take_tool_completion_metadata()
        assert take_tool_completion_metadata() == {}

    def test_clear(self) -> None:
        update_tool_completion_metadata(a="b")
        clear_tool_completion_metadata()
        assert take_tool_completion_metadata() == {}


class TestToolMetadata:
    def test_reset_and_update(self) -> None:
        reset_tool_metadata()
        update_tool_metadata(desire_levels={"curiosity": 0.5})
        result = get_tool_metadata()
        assert result["desire_levels"] == {"curiosity": 0.5}

    def test_none_values_skipped(self) -> None:
        reset_tool_metadata()
        update_tool_metadata(a=1, b=None)
        result = get_tool_metadata()
        assert "a" in result
        assert "b" not in result


class TestGetEpisodes:
    def test_raises_when_not_configured(self) -> None:
        import ego_mcp._server_runtime as rt
        original = rt._episodes_getter
        try:
            rt._episodes_getter = None
            with pytest.raises(RuntimeError, match="not configured"):
                get_episodes()
        finally:
            rt._episodes_getter = original
