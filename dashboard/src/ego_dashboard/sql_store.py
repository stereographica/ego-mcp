from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import psycopg
from redis import Redis

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.models import DashboardEvent, LogEvent


class SqlTelemetryStore:
    def __init__(self, database_url: str, redis_url: str) -> None:
        self._db_url = database_url
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def initialize(self) -> None:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tool_events (
                      ts TIMESTAMPTZ NOT NULL,
                      event_type TEXT NOT NULL,
                      tool_name TEXT NOT NULL,
                      ok BOOLEAN NOT NULL,
                      duration_ms INTEGER,
                      emotion_primary TEXT,
                      emotion_intensity DOUBLE PRECISION,
                      numeric_metrics JSONB NOT NULL,
                      string_metrics JSONB NOT NULL,
                      params JSONB NOT NULL,
                      private BOOLEAN NOT NULL,
                      message TEXT
                    )
                    """
                )
                cur.execute("SELECT create_hypertable('tool_events', 'ts', if_not_exists => TRUE)")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tool_events_tool_name_ts "
                    "ON tool_events (tool_name, ts DESC)"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS log_events (
                      ts TIMESTAMPTZ NOT NULL,
                      level TEXT NOT NULL,
                      logger TEXT NOT NULL,
                      message TEXT NOT NULL,
                      private BOOLEAN NOT NULL,
                      fields JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE log_events
                    ADD COLUMN IF NOT EXISTS fields JSONB NOT NULL DEFAULT '{}'::jsonb
                    """
                )
                cur.execute("SELECT create_hypertable('log_events', 'ts', if_not_exists => TRUE)")
            conn.commit()

    def ingest(self, event: DashboardEvent) -> None:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tool_events (
                      ts, event_type, tool_name, ok, duration_ms, emotion_primary,
                      emotion_intensity, numeric_metrics, string_metrics, params, private, message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                    """,
                    (
                        event.ts,
                        event.event_type,
                        event.tool_name,
                        event.ok,
                        event.duration_ms,
                        event.emotion_primary,
                        event.emotion_intensity,
                        json.dumps(event.numeric_metrics),
                        json.dumps(event.string_metrics),
                        json.dumps(event.params),
                        event.private,
                        event.message,
                    ),
                )
            conn.commit()
        self._redis.set("dashboard:current", json.dumps(event.model_dump(mode="json")))

    def ingest_log(self, event: LogEvent) -> None:
        masked = "REDACTED" if event.private else event.message
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO log_events (ts, level, logger, message, private, fields)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        event.ts,
                        event.level.upper(),
                        event.logger,
                        masked,
                        event.private,
                        json.dumps(event.fields),
                    ),
                )
            conn.commit()

    def tool_usage(self, start: datetime, end: datetime, bucket: str) -> list[dict[str, object]]:
        bucket_size = _bucket_to_sql(bucket)
        bucket_delta = _bucket_to_timedelta(bucket)
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time_bucket(%s::interval, ts) AS b, tool_name, count(*)
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s
                    GROUP BY b, tool_name
                    ORDER BY b ASC
                    """,
                    (bucket_size, start, end),
                )
                rows = cur.fetchall()
        if not rows:
            return []

        tool_names = sorted({str(tool_name) for _, tool_name, _ in rows})
        by_ts: dict[str, dict[str, object]] = {}
        for b, tool_name, count in rows:
            bucket_ts = b if b.tzinfo is not None else b.replace(tzinfo=UTC)
            key = bucket_ts.astimezone(UTC).isoformat()
            row = by_ts.get(key)
            if row is None:
                row = {"ts": key}
                by_ts[key] = row
            row[str(tool_name)] = int(count)

        first_bucket = _bucket_floor(start, bucket_delta)
        last_bucket = _bucket_floor(end, bucket_delta)
        cursor = first_bucket
        dense_rows: list[dict[str, object]] = []
        while cursor <= last_bucket:
            key = cursor.isoformat()
            row = dict(by_ts.get(key, {"ts": key}))
            for tool_name in tool_names:
                value = row.get(tool_name, 0)
                row[tool_name] = int(value) if isinstance(value, (int, float)) else 0
            dense_rows.append(row)
            cursor += bucket_delta
        return dense_rows

    def metric_history(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        bucket_size = _bucket_to_sql(bucket)
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time_bucket(%s::interval, ts) AS b,
                           avg((numeric_metrics ->> %s)::double precision)
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s AND numeric_metrics ? %s
                    GROUP BY b
                    ORDER BY b ASC
                    """,
                    (bucket_size, key, start, end, key),
                )
                rows = cur.fetchall()
        return [
            {"ts": ts.isoformat(), "value": float(value)} for ts, value in rows if value is not None
        ]

    def string_timeline(self, key: str, start: datetime, end: datetime) -> list[dict[str, str]]:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts, string_metrics ->> %s
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s AND string_metrics ? %s
                    ORDER BY ts ASC
                    """,
                    (key, start, end, key),
                )
                rows = cur.fetchall()
        return [
            {"ts": ts.isoformat(), "value": value} for ts, value in rows if isinstance(value, str)
        ]

    def string_heatmap(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        bucket_size = _bucket_to_sql(bucket)
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time_bucket(%s::interval, ts) AS b,
                           string_metrics ->> %s AS value,
                           count(*)
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s AND string_metrics ? %s
                    GROUP BY b, value
                    ORDER BY b ASC
                    """,
                    (bucket_size, key, start, end, key),
                )
                rows = cur.fetchall()
        grouped: dict[str, dict[str, int]] = defaultdict(dict)
        for ts, value, count in rows:
            if isinstance(value, str):
                grouped[ts.isoformat()][value] = int(count)
        return [{"ts": ts, "counts": counts} for ts, counts in grouped.items()]

    def logs(
        self, start: datetime, end: datetime, level: str | None = None, logger: str | None = None
    ) -> list[dict[str, object]]:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                if level and logger:
                    cur.execute(
                        """
                        SELECT ts, level, logger, message, private, fields
                        FROM log_events
                        WHERE ts >= %s AND ts <= %s AND level = %s AND logger ILIKE %s
                        ORDER BY ts ASC
                        LIMIT 300
                        """,
                        (start, end, level.upper(), f"%{logger}%"),
                    )
                elif level:
                    cur.execute(
                        """
                        SELECT ts, level, logger, message, private, fields
                        FROM log_events
                        WHERE ts >= %s AND ts <= %s AND level = %s
                        ORDER BY ts ASC
                        LIMIT 300
                        """,
                        (start, end, level.upper()),
                    )
                elif logger:
                    cur.execute(
                        """
                        SELECT ts, level, logger, message, private, fields
                        FROM log_events
                        WHERE ts >= %s AND ts <= %s AND logger ILIKE %s
                        ORDER BY ts ASC
                        LIMIT 300
                        """,
                        (start, end, f"%{logger}%"),
                    )
                else:
                    cur.execute(
                        """
                        SELECT ts, level, logger, message, private, fields
                        FROM log_events
                        WHERE ts >= %s AND ts <= %s
                        ORDER BY ts ASC
                        LIMIT 300
                        """,
                        (start, end),
                    )
                rows = cur.fetchall()
        return [
            {
                "ts": ts.isoformat(),
                "level": str(lvl),
                "logger": str(logger),
                "message": "REDACTED" if bool(private) else str(msg),
                "private": bool(private),
                "fields": fields if isinstance(fields, dict) else {},
            }
            for ts, lvl, logger, msg, private, fields in rows
        ]

    def anomaly_alerts(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        usage = self.tool_usage(start, end, bucket)
        intensity = self.metric_history("intensity", start, end, bucket)
        alerts: list[dict[str, object]] = []

        prev_total: int | None = None
        for row in usage:
            total = sum(v for k, v in row.items() if k != "ts" and isinstance(v, int))
            if prev_total is not None and prev_total > 0 and total >= prev_total * 2:
                alerts.append({"kind": "usage_spike", "ts": row["ts"], "value": total})
            prev_total = total

        prev_intensity: float | None = None
        for row in intensity:
            raw = row.get("value")
            if isinstance(raw, (int, float)):
                if prev_intensity is not None and raw - prev_intensity >= 0.4:
                    alerts.append({"kind": "intensity_spike", "ts": row["ts"], "value": raw})
                prev_intensity = float(raw)

        return alerts

    def current(self) -> dict[str, object]:
        latest_raw = self._redis.get("dashboard:current")
        latest_text = latest_raw if isinstance(latest_raw, str) else None
        latest = json.loads(latest_text) if latest_text else None
        if latest is None:
            return {
                "latest": None,
                "tool_calls_per_min": 0,
                "error_rate": 0.0,
                "window_24h": {"tool_calls": 0, "error_rate": 0.0},
                "latest_desires": {},
            }
        if isinstance(latest, dict) and latest.get("private") is True:
            latest["message"] = "REDACTED"

        latest_ts = datetime.fromisoformat(str(latest["ts"]).replace("Z", "+00:00"))
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*),
                           sum(CASE WHEN ok = false THEN 1 ELSE 0 END)
                    FROM tool_events
                    WHERE ts >= %s - interval '1 minute' AND ts <= %s
                    """,
                    (latest_ts, latest_ts),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    SELECT count(*),
                           sum(CASE WHEN ok = false THEN 1 ELSE 0 END)
                    FROM tool_events
                    WHERE ts >= %s - interval '24 hours' AND ts <= %s
                    """,
                    (latest_ts, latest_ts),
                )
                row_24h = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                      sum(
                        CASE
                          WHEN message = 'Tool invocation' AND fields ? 'tool_name' THEN 1
                          ELSE 0
                        END
                      ),
                      sum(CASE WHEN message = 'Tool execution failed' THEN 1 ELSE 0 END)
                    FROM log_events
                    WHERE ts >= %s - interval '1 minute' AND ts <= %s
                    """,
                    (latest_ts, latest_ts),
                )
                log_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                      sum(
                        CASE
                          WHEN message = 'Tool invocation' AND fields ? 'tool_name' THEN 1
                          ELSE 0
                        END
                      ),
                      sum(CASE WHEN message = 'Tool execution failed' THEN 1 ELSE 0 END)
                    FROM log_events
                    WHERE ts >= %s - interval '24 hours' AND ts <= %s
                    """,
                    (latest_ts, latest_ts),
                )
                log_row_24h = cur.fetchone()
                if latest.get("emotion_primary") is None or latest.get("emotion_intensity") is None:
                    cur.execute(
                        """
                        SELECT emotion_primary, emotion_intensity
                        FROM tool_events
                        WHERE ts <= %s
                          AND (emotion_primary IS NOT NULL OR emotion_intensity IS NOT NULL)
                        ORDER BY ts DESC
                        LIMIT 1
                        """,
                        (latest_ts,),
                    )
                    emotion_row = cur.fetchone()
                else:
                    emotion_row = None
                latest_desires: dict[str, float] = {}
                for key in DESIRE_METRIC_KEYS:
                    cur.execute(
                        """
                        SELECT (numeric_metrics ->> %s)::double precision
                        FROM tool_events
                        WHERE ts <= %s AND numeric_metrics ? %s
                        ORDER BY ts DESC
                        LIMIT 1
                        """,
                        (key, latest_ts, key),
                    )
                    desire_row = cur.fetchone()
                    if desire_row is None:
                        continue
                    desire_value = desire_row[0]
                    if desire_value is not None:
                        latest_desires[key] = float(desire_value)
        calls, errors = row if row is not None else (0, 0)
        total_calls = int(calls or 0)
        total_errors = int(errors or 0)
        calls_24h, errors_24h = row_24h if row_24h is not None else (0, 0)
        total_calls_24h = int(calls_24h or 0)
        total_errors_24h = int(errors_24h or 0)
        log_calls_raw, log_failures_raw = log_row if log_row is not None else (0, 0)
        log_calls = int(log_calls_raw or 0)
        log_failures = int(log_failures_raw or 0)
        log_calls_24h_raw, log_failures_24h_raw = log_row_24h if log_row_24h is not None else (0, 0)
        log_calls_24h = int(log_calls_24h_raw or 0)
        log_failures_24h = int(log_failures_24h_raw or 0)
        if emotion_row is not None:
            emotion_primary, emotion_intensity = emotion_row
            if latest.get("emotion_primary") is None and emotion_primary is not None:
                latest["emotion_primary"] = str(emotion_primary)
            if latest.get("emotion_intensity") is None and emotion_intensity is not None:
                latest["emotion_intensity"] = float(emotion_intensity)
        return {
            "latest": latest,
            "tool_calls_per_min": log_calls if log_calls > 0 else total_calls,
            "error_rate": (
                (log_failures / log_calls)
                if log_calls > 0
                else ((total_errors / total_calls) if total_calls else 0.0)
            ),
            "window_24h": {
                "tool_calls": (log_calls_24h if log_calls_24h > 0 else total_calls_24h),
                "error_rate": (
                    (log_failures_24h / log_calls_24h)
                    if log_calls_24h > 0
                    else ((total_errors_24h / total_calls_24h) if total_calls_24h else 0.0)
                ),
            },
            "latest_desires": latest_desires,
        }


def _bucket_to_sql(bucket: str) -> str:
    mapping = {"1m": "1 minute", "5m": "5 minute", "15m": "15 minute"}
    return mapping.get(bucket, "1 minute")


def _bucket_to_timedelta(bucket: str) -> timedelta:
    mapping = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "15m": timedelta(minutes=15)}
    return mapping.get(bucket, timedelta(minutes=1))


def _bucket_floor(value: datetime, delta: timedelta) -> datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    step = int(delta.total_seconds())
    elapsed = int((aware.astimezone(UTC) - epoch).total_seconds())
    floored = elapsed - (elapsed % step)
    return epoch + timedelta(seconds=floored)
