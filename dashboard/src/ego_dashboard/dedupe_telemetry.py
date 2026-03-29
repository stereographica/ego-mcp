from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation

from ego_dashboard.ingestor import _resolve_source_files
from ego_dashboard.models import DashboardEvent, LogEvent
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.telemetry_identity import dashboard_event_dedupe_key, log_event_dedupe_key

_BATCH_SIZE = 1000


@dataclass(frozen=True)
class CleanupStats:
    backfilled_tool_events: int
    backfilled_log_events: int
    deleted_tool_duplicates: int
    deleted_log_duplicates: int
    initialized_checkpoints: int


def _iter_cursor_rows(cursor: Any, *, batch_size: int = _BATCH_SIZE) -> list[tuple[Any, ...]]:
    fetchmany = getattr(cursor, "fetchmany", None)
    if callable(fetchmany):
        rows: list[tuple[Any, ...]] = []
        while True:
            batch = fetchmany(batch_size)
            if not batch:
                return rows
            rows.extend(batch)
    return list(cursor.fetchall())


def build_tool_event_dedupe_updates(
    rows: list[tuple[Any, ...]],
) -> list[tuple[str, object, str]]:
    updates: list[tuple[str, object, str]] = []
    for row in rows:
        if len(row) != 13:
            continue
        (
            ctid,
            ts,
            event_type,
            tool_name,
            ok,
            duration_ms,
            emotion_primary,
            emotion_intensity,
            numeric_metrics,
            string_metrics,
            params,
            private,
            message,
        ) = row
        if not isinstance(ctid, str):
            continue
        event = DashboardEvent(
            ts=ts,
            event_type=str(event_type),
            tool_name=str(tool_name),
            ok=bool(ok),
            duration_ms=duration_ms if isinstance(duration_ms, int) else None,
            emotion_primary=emotion_primary if isinstance(emotion_primary, str) else None,
            emotion_intensity=(
                float(emotion_intensity) if isinstance(emotion_intensity, (int, float)) else None
            ),
            numeric_metrics=numeric_metrics if isinstance(numeric_metrics, dict) else {},
            string_metrics=string_metrics if isinstance(string_metrics, dict) else {},
            params=params if isinstance(params, dict) else {},
            private=bool(private),
            message=message if isinstance(message, str) else None,
        )
        updates.append((ctid, ts, dashboard_event_dedupe_key(event)))
    return updates


def build_log_event_dedupe_updates(rows: list[tuple[Any, ...]]) -> list[tuple[str, object, str]]:
    updates: list[tuple[str, object, str]] = []
    for row in rows:
        if len(row) != 7:
            continue
        ctid, ts, level, logger, message, private, fields = row
        if not isinstance(ctid, str):
            continue
        event = LogEvent(
            ts=ts,
            level=str(level),
            logger=str(logger),
            message=str(message),
            private=bool(private),
            fields=fields if isinstance(fields, dict) else {},
        )
        updates.append((ctid, ts, log_event_dedupe_key(event)))
    return updates


def partition_dedupe_updates(
    rows: list[tuple[str, object, str]],
    *,
    existing: set[tuple[object, str]] | None = None,
) -> tuple[list[tuple[str, object, str]], list[str]]:
    updates: list[tuple[str, object, str]] = []
    duplicate_ctids: list[str] = []
    seen = set(existing or set())
    for ctid, ts, dedupe_key in rows:
        identity = (ts, dedupe_key)
        if identity in seen:
            duplicate_ctids.append(ctid)
            continue
        seen.add(identity)
        updates.append((ctid, ts, dedupe_key))
    return updates, duplicate_ctids


def _apply_backfill_updates(
    cursor: Any,
    *,
    table: str,
    updates: list[tuple[str, object, str]],
) -> tuple[int, int]:
    if table not in {"tool_events", "log_events"}:
        raise ValueError(f"unsupported table: {table}")

    updated_rows = 0
    deleted_duplicates = 0

    for ctid, ts, dedupe_key in updates:
        cursor.execute(
            f"""
            SELECT 1
            FROM {table}
            WHERE ts = %s
              AND dedupe_key = %s
            LIMIT 1
            """,
            (ts, dedupe_key),
        )
        if cursor.fetchone() is not None:
            cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE ctid = %s::tid
                """,
                (ctid,),
            )
            deleted_now = getattr(cursor, "rowcount", 0)
            if isinstance(deleted_now, int) and deleted_now > 0:
                deleted_duplicates += deleted_now
            continue

        cursor.execute("SAVEPOINT dedupe_backfill_row")
        try:
            cursor.execute(
                f"""
                UPDATE {table}
                SET dedupe_key = %s
                WHERE ctid = %s::tid
                """,
                (dedupe_key, ctid),
            )
            updated_now = getattr(cursor, "rowcount", 0)
        except UniqueViolation:
            cursor.execute("ROLLBACK TO SAVEPOINT dedupe_backfill_row")
            cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE ctid = %s::tid
                """,
                (ctid,),
            )
            deleted_duplicates += 1
            cursor.execute("RELEASE SAVEPOINT dedupe_backfill_row")
            continue
        cursor.execute("RELEASE SAVEPOINT dedupe_backfill_row")

        if isinstance(updated_now, int) and updated_now > 0:
            updated_rows += updated_now

    return updated_rows, deleted_duplicates


def _backfill_tool_event_dedupe_keys(cursor: Any, *, dry_run: bool) -> tuple[int, int]:
    cursor.execute(
        """
        SELECT ts, dedupe_key
        FROM tool_events
        WHERE dedupe_key IS NOT NULL
        """
    )
    seen: set[tuple[object, str]] = {
        (ts, dedupe_key)
        for ts, dedupe_key in _iter_cursor_rows(cursor)
        if isinstance(dedupe_key, str)
    }
    cursor.execute(
        """
        SELECT ctid::text,
               ts,
               event_type,
               tool_name,
               ok,
               duration_ms,
               emotion_primary,
               emotion_intensity,
               numeric_metrics,
               string_metrics,
               params,
               private,
               message
        FROM tool_events
        WHERE dedupe_key IS NULL
        ORDER BY ts ASC
        """
    )
    raw_updates = build_tool_event_dedupe_updates(_iter_cursor_rows(cursor))
    updates, duplicate_ctids = partition_dedupe_updates(raw_updates, existing=seen)
    if dry_run:
        return (len(updates), len(duplicate_ctids))
    for ctid in duplicate_ctids:
        cursor.execute(
            """
            DELETE FROM tool_events
            WHERE ctid = %s::tid
            """,
            (ctid,),
        )
    updated_rows, deleted_on_conflict = _apply_backfill_updates(
        cursor, table="tool_events", updates=updates
    )
    return (updated_rows, len(duplicate_ctids) + deleted_on_conflict)


def _backfill_log_event_dedupe_keys(cursor: Any, *, dry_run: bool) -> tuple[int, int]:
    cursor.execute(
        """
        SELECT ts, dedupe_key
        FROM log_events
        WHERE dedupe_key IS NOT NULL
        """
    )
    seen: set[tuple[object, str]] = {
        (ts, dedupe_key)
        for ts, dedupe_key in _iter_cursor_rows(cursor)
        if isinstance(dedupe_key, str)
    }
    cursor.execute(
        """
        SELECT ctid::text,
               ts,
               level,
               logger,
               message,
               private,
               fields
        FROM log_events
        WHERE dedupe_key IS NULL
        ORDER BY ts ASC
        """
    )
    raw_updates = build_log_event_dedupe_updates(_iter_cursor_rows(cursor))
    updates, duplicate_ctids = partition_dedupe_updates(raw_updates, existing=seen)
    if dry_run:
        return (len(updates), len(duplicate_ctids))
    for ctid in duplicate_ctids:
        cursor.execute(
            """
            DELETE FROM log_events
            WHERE ctid = %s::tid
            """,
            (ctid,),
        )
    updated_rows, deleted_on_conflict = _apply_backfill_updates(
        cursor, table="log_events", updates=updates
    )
    return (updated_rows, len(duplicate_ctids) + deleted_on_conflict)


def _delete_tool_event_duplicates(cursor: Any, *, dry_run: bool) -> int:
    if dry_run:
        cursor.execute(
            """
            WITH ranked AS (
              SELECT row_number() OVER (PARTITION BY ts, dedupe_key ORDER BY ctid) AS row_num
              FROM tool_events
              WHERE dedupe_key IS NOT NULL
            )
            SELECT count(*)
            FROM ranked
            WHERE row_num > 1
            """
        )
        row = cursor.fetchone()
        return int(row[0]) if row and isinstance(row[0], int) else 0

    cursor.execute(
        """
        WITH ranked AS (
          SELECT ctid,
                 row_number() OVER (PARTITION BY ts, dedupe_key ORDER BY ctid) AS row_num
          FROM tool_events
          WHERE dedupe_key IS NOT NULL
        )
        DELETE FROM tool_events AS target
        USING ranked
        WHERE target.ctid = ranked.ctid
          AND ranked.row_num > 1
        """
    )
    deleted = getattr(cursor, "rowcount", 0)
    return int(deleted) if isinstance(deleted, int) and deleted > 0 else 0


def _delete_log_event_duplicates(cursor: Any, *, dry_run: bool) -> int:
    if dry_run:
        cursor.execute(
            """
            WITH ranked AS (
              SELECT row_number() OVER (PARTITION BY ts, dedupe_key ORDER BY ctid) AS row_num
              FROM log_events
              WHERE dedupe_key IS NOT NULL
            )
            SELECT count(*)
            FROM ranked
            WHERE row_num > 1
            """
        )
        row = cursor.fetchone()
        return int(row[0]) if row and isinstance(row[0], int) else 0

    cursor.execute(
        """
        WITH ranked AS (
          SELECT ctid,
                 row_number() OVER (PARTITION BY ts, dedupe_key ORDER BY ctid) AS row_num
          FROM log_events
          WHERE dedupe_key IS NOT NULL
        )
        DELETE FROM log_events AS target
        USING ranked
        WHERE target.ctid = ranked.ctid
          AND ranked.row_num > 1
        """
    )
    deleted = getattr(cursor, "rowcount", 0)
    return int(deleted) if isinstance(deleted, int) and deleted > 0 else 0


def _initialize_checkpoints(cursor: Any, log_path: str, *, dry_run: bool) -> int:
    count = 0
    for resolved_path in _resolve_source_files(log_path):
        stat = os.stat(resolved_path)
        count += 1
        if dry_run:
            continue
        cursor.execute(
            """
            INSERT INTO ingestion_checkpoints (path, inode, byte_offset, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (path) DO UPDATE
            SET inode = EXCLUDED.inode,
                byte_offset = EXCLUDED.byte_offset,
                updated_at = EXCLUDED.updated_at
            """,
            (resolved_path, stat.st_ino, stat.st_size),
        )
    return count


def run_cleanup(
    *,
    database_url: str,
    log_path: str | None = None,
    dry_run: bool = False,
) -> CleanupStats:
    SqlTelemetryStore(database_url, "redis://unused").initialize()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            backfilled_tool_events, backfilled_tool_from_null = _backfill_tool_event_dedupe_keys(
                cur, dry_run=dry_run
            )
            backfilled_log_events, backfilled_log_from_null = _backfill_log_event_dedupe_keys(
                cur, dry_run=dry_run
            )
            deleted_tool_duplicates = backfilled_tool_from_null + _delete_tool_event_duplicates(
                cur, dry_run=dry_run
            )
            deleted_log_duplicates = backfilled_log_from_null + _delete_log_event_duplicates(
                cur, dry_run=dry_run
            )
            initialized_checkpoints = (
                _initialize_checkpoints(cur, log_path, dry_run=dry_run) if log_path else 0
            )
        if not dry_run:
            conn.commit()

    return CleanupStats(
        backfilled_tool_events=backfilled_tool_events,
        backfilled_log_events=backfilled_log_events,
        deleted_tool_duplicates=deleted_tool_duplicates,
        deleted_log_duplicates=deleted_log_duplicates,
        initialized_checkpoints=initialized_checkpoints,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill dedupe keys and remove replay duplicates"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DASHBOARD_DATABASE_URL"),
        help="TimescaleDB/PostgreSQL connection string",
    )
    parser.add_argument(
        "--log-path",
        default=os.getenv("DASHBOARD_LOG_PATH"),
        help="Optional file/glob used to initialize ingestion checkpoints to current EOF",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    database_url = args.database_url
    if not isinstance(database_url, str) or not database_url:
        parser.error("database URL is required via --database-url or DASHBOARD_DATABASE_URL")

    stats = run_cleanup(
        database_url=database_url,
        log_path=args.log_path if isinstance(args.log_path, str) and args.log_path else None,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(asdict(stats), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
