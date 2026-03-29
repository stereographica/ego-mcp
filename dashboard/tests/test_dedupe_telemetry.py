from __future__ import annotations

from datetime import UTC, datetime

from psycopg.errors import UniqueViolation

from ego_dashboard.dedupe_telemetry import (
    _apply_backfill_updates,
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
    assert updates[0][0] == "(0,1)"
    assert updates[1][0] == "(0,3)"


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


def test_apply_backfill_updates_deletes_rows_that_conflict_during_update() -> None:
    class _Cursor:
        def __init__(self) -> None:
            self.rowcount = 0
            self.updated: list[str] = []
            self.deleted: list[str] = []

        def execute(self, query: object, params: object | None = None) -> None:
            sql = str(query)
            tuple_params = params if isinstance(params, tuple) else ()
            if sql.lstrip().startswith("DELETE FROM tool_events") and "EXISTS" in sql:
                ctid = str(tuple_params[0])
                self.rowcount = 1 if ctid == "(0,1)" else 0
                if self.rowcount == 1:
                    self.deleted.append(ctid)
                return
            if sql.lstrip().startswith("UPDATE tool_events"):
                ctid = str(tuple_params[1])
                if ctid == "(0,3)":
                    raise UniqueViolation("duplicate key value violates unique constraint")
                self.rowcount = 1
                self.updated.append(ctid)
                return
            if sql.lstrip().startswith("DELETE FROM tool_events"):
                ctid = str(tuple_params[0])
                self.rowcount = 1
                self.deleted.append(ctid)
                return
            self.rowcount = 0

    cursor = _Cursor()
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    updated, deleted = _apply_backfill_updates(
        cursor,
        table="tool_events",
        updates=[
            ("(0,1)", ts, "existing"),
            ("(0,2)", ts, "fresh"),
            ("(0,3)", ts, "race"),
        ],
    )

    assert updated == 1
    assert deleted == 2
    assert cursor.updated == ["(0,2)"]
    assert cursor.deleted == ["(0,1)", "(0,3)"]
