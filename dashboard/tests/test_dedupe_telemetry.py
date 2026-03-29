from __future__ import annotations

from datetime import UTC, datetime

from ego_dashboard.dedupe_telemetry import (
    build_log_event_dedupe_updates,
    build_tool_event_dedupe_updates,
    partition_dedupe_updates,
)


def test_partition_tool_event_updates_drops_only_exact_duplicates() -> None:
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    rows: list[tuple[object, ...]] = [
        (
            "(0,1)",
            ts,
            "tool_call_completed",
            "remember",
            True,
            10,
            None,
            None,
            {},
            {},
            {},
            False,
            "ok",
        ),
        (
            "(0,2)",
            ts,
            "tool_call_completed",
            "remember",
            True,
            10,
            None,
            None,
            {},
            {},
            {},
            False,
            "ok",
        ),
        (
            "(0,3)",
            ts,
            "tool_call_failed",
            "remember",
            False,
            10,
            None,
            None,
            {},
            {},
            {},
            False,
            "ng",
        ),
    ]

    updates, duplicates = partition_dedupe_updates(build_tool_event_dedupe_updates(rows))

    assert len(updates) == 2
    assert duplicates == ["(0,2)"]


def test_partition_log_event_updates_preserves_distinct_rows() -> None:
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    rows: list[tuple[object, ...]] = [
        (
            "(1,1)",
            ts,
            "INFO",
            "ego_mcp.server",
            "Tool invocation",
            False,
            {"tool_name": "remember"},
        ),
        (
            "(1,2)",
            ts,
            "INFO",
            "ego_mcp.server",
            "Tool invocation",
            False,
            {"tool_name": "remember"},
        ),
        (
            "(1,3)",
            ts,
            "ERROR",
            "ego_mcp.server",
            "Tool execution failed",
            False,
            {"tool_name": "remember"},
        ),
    ]

    updates, duplicates = partition_dedupe_updates(build_log_event_dedupe_updates(rows))

    assert len(updates) == 2
    assert duplicates == ["(1,2)"]
