from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import psycopg
from redis import Redis

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.models import DashboardEvent, LogEvent
from ego_dashboard.telemetry_identity import dashboard_event_dedupe_key, log_event_dedupe_key


def _escape_ilike_pattern(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_notion_confidences(value: object) -> dict[str, float]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    parsed: dict[str, float] = {}
    for notion_id, confidence in payload.items():
        if not isinstance(notion_id, str) or not isinstance(confidence, (int, float)):
            continue
        parsed[notion_id] = float(confidence)
    return parsed


def _fallback_notion_confidence(
    notion_id: str,
    confidence: object,
    *related_values: object,
) -> float | None:
    related_ids = {
        candidate.strip()
        for raw_value in related_values
        if isinstance(raw_value, str)
        for candidate in raw_value.split(",")
        if candidate.strip()
    }
    if notion_id in related_ids and len(related_ids) == 1 and isinstance(confidence, (int, float)):
        return float(confidence)
    return None


def _tool_name_from_fields(fields: object) -> str | None:
    if not isinstance(fields, dict):
        return None
    raw = fields.get("tool_name")
    return raw if isinstance(raw, str) and raw else None


def _dense_usage_rows(
    rows: list[tuple[datetime, str, int]],
    start: datetime,
    end: datetime,
    bucket: str,
) -> list[dict[str, object]]:
    if not rows:
        return []

    bucket_delta = _bucket_to_timedelta(bucket)
    tool_names = sorted({tool_name for _, tool_name, _ in rows})
    by_ts: dict[str, dict[str, object]] = {}
    for bucket_ts, tool_name, count in rows:
        aware = bucket_ts if bucket_ts.tzinfo is not None else bucket_ts.replace(tzinfo=UTC)
        key = aware.astimezone(UTC).isoformat()
        row = by_ts.get(key)
        if row is None:
            row = {"ts": key}
            by_ts[key] = row
        row[tool_name] = int(count)

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
                      message TEXT,
                      dedupe_key TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE tool_events
                    ADD COLUMN IF NOT EXISTS dedupe_key TEXT
                    """
                )
                cur.execute("SELECT create_hypertable('tool_events', 'ts', if_not_exists => TRUE)")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tool_events_tool_name_ts "
                    "ON tool_events (tool_name, ts DESC)"
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_events_ts_dedupe "
                    "ON tool_events (ts, dedupe_key) WHERE dedupe_key IS NOT NULL"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS log_events (
                      ts TIMESTAMPTZ NOT NULL,
                      level TEXT NOT NULL,
                      logger TEXT NOT NULL,
                      message TEXT NOT NULL,
                      private BOOLEAN NOT NULL,
                      fields JSONB NOT NULL DEFAULT '{}'::jsonb,
                      dedupe_key TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE log_events
                    ADD COLUMN IF NOT EXISTS fields JSONB NOT NULL DEFAULT '{}'::jsonb
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE log_events
                    ADD COLUMN IF NOT EXISTS dedupe_key TEXT
                    """
                )
                cur.execute("SELECT create_hypertable('log_events', 'ts', if_not_exists => TRUE)")
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_log_events_ts_dedupe "
                    "ON log_events (ts, dedupe_key) WHERE dedupe_key IS NOT NULL"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
                      path TEXT PRIMARY KEY,
                      inode BIGINT NOT NULL,
                      byte_offset BIGINT NOT NULL,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            conn.commit()

    def ingest(self, event: DashboardEvent) -> None:
        dedupe_key = dashboard_event_dedupe_key(event)
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tool_events (
                      ts, event_type, tool_name, ok, duration_ms, emotion_primary,
                      emotion_intensity, numeric_metrics, string_metrics, params, private,
                      message, dedupe_key
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (ts, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
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
                        dedupe_key,
                    ),
                )
            conn.commit()
        self._redis.set("dashboard:current", json.dumps(event.model_dump(mode="json")))

    def ingest_log(self, event: LogEvent) -> None:
        masked = "REDACTED" if event.private else event.message
        dedupe_key = log_event_dedupe_key(
            LogEvent(
                ts=event.ts,
                level=event.level,
                logger=event.logger,
                message=masked,
                private=event.private,
                fields=event.fields,
            )
        )
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO log_events (ts, level, logger, message, private, fields, dedupe_key)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (ts, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
                    """,
                    (
                        event.ts,
                        event.level.upper(),
                        event.logger,
                        masked,
                        event.private,
                        json.dumps(event.fields),
                        dedupe_key,
                    ),
                )
            conn.commit()

    def load_checkpoint(self, path: str) -> tuple[int, int] | None:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT inode, byte_offset
                    FROM ingestion_checkpoints
                    WHERE path = %s
                    """,
                    (path,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        inode, offset = row
        if not isinstance(inode, int) or not isinstance(offset, int):
            return None
        return (inode, offset)

    def save_checkpoint(self, path: str, inode: int, offset: int) -> None:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_checkpoints (path, inode, byte_offset, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (path) DO UPDATE
                    SET inode = EXCLUDED.inode,
                        byte_offset = EXCLUDED.byte_offset,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (path, inode, offset),
                )
            conn.commit()

    def tool_usage(self, start: datetime, end: datetime, bucket: str) -> list[dict[str, object]]:
        bucket_size = _bucket_to_sql(bucket)
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time_bucket(%s::interval, ts) AS b,
                           fields ->> 'tool_name' AS tool_name,
                           count(*)
                    FROM log_events
                    WHERE ts >= %s AND ts <= %s
                      AND message = 'Tool invocation'
                      AND fields ? 'tool_name'
                    GROUP BY b, tool_name
                    ORDER BY b ASC
                    """,
                    (bucket_size, start, end),
                )
                rows = cur.fetchall()
                if rows:
                    log_rows = [
                        (bucket_ts, str(tool_name), int(count))
                        for bucket_ts, tool_name, count in rows
                        if isinstance(bucket_ts, datetime) and isinstance(tool_name, str)
                    ]
                    return _dense_usage_rows(log_rows, start, end, bucket)

                cur.execute(
                    """
                    SELECT time_bucket(%s::interval, ts) AS b, tool_name, count(*)
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s
                      AND event_type IN ('tool_call_completed', 'tool_call_failed')
                    GROUP BY b, tool_name
                    ORDER BY b ASC
                    """,
                    (bucket_size, start, end),
                )
                fallback_rows = cur.fetchall()
        typed_rows = [
            (bucket_ts, str(tool_name), int(count))
            for bucket_ts, tool_name, count in fallback_rows
            if isinstance(bucket_ts, datetime) and isinstance(tool_name, str)
        ]
        return _dense_usage_rows(typed_rows, start, end, bucket)

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

    def desire_metric_keys(self, start: datetime, end: datetime) -> list[str]:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT numeric_metrics
                    FROM tool_events
                    WHERE ts >= %s AND ts <= %s AND tool_name = 'feel_desires'
                    ORDER BY ts ASC
                    """,
                    (start, end),
                )
                rows = cur.fetchall()

        keys: set[str] = set()
        for (numeric_metrics,) in rows:
            if not isinstance(numeric_metrics, dict):
                continue
            for key in numeric_metrics:
                if isinstance(key, str) and (key in DESIRE_METRIC_KEYS or "want" in key.lower()):
                    keys.add(key)
        return sorted(keys)

    def notion_history(
        self, notion_id: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      ts,
                      string_metrics ->> 'notion_confidences',
                      string_metrics ->> 'notion_created',
                      string_metrics ->> 'notion_reinforced',
                      string_metrics ->> 'notion_weakened',
                      string_metrics ->> 'notion_dormant',
                      string_metrics ->> 'notion_decayed',
                      string_metrics ->> 'notion_pruned',
                      string_metrics ->> 'notion_merged',
                      (numeric_metrics ->> 'notion_confidence')::double precision
                    FROM tool_events
                    WHERE ts >= %s
                      AND ts <= %s
                      AND (
                        string_metrics ? 'notion_confidences'
                        OR string_metrics ? 'notion_created'
                        OR string_metrics ? 'notion_reinforced'
                        OR string_metrics ? 'notion_weakened'
                        OR string_metrics ? 'notion_dormant'
                        OR string_metrics ? 'notion_decayed'
                        OR string_metrics ? 'notion_pruned'
                        OR string_metrics ? 'notion_merged'
                      )
                    ORDER BY ts ASC
                    """,
                    (start, end),
                )
                rows = cur.fetchall()

        grouped: dict[str, list[float]] = defaultdict(list)
        bucket_delta = _bucket_to_timedelta(bucket)
        for row in rows:
            if not isinstance(row, tuple) or len(row) < 2:
                continue
            ts = row[0]
            if len(row) >= 10:
                (
                    _ts,
                    confidence_map_raw,
                    created_raw,
                    reinforced_raw,
                    weakened_raw,
                    dormant_raw,
                    decayed_raw,
                    pruned_raw,
                    merged_raw,
                    fallback_confidence,
                ) = row[:10]
            elif len(row) >= 7:
                (
                    _ts,
                    confidence_map_raw,
                    created_raw,
                    reinforced_raw,
                    weakened_raw,
                    dormant_raw,
                    fallback_confidence,
                ) = row[:7]
                decayed_raw = None
                pruned_raw = None
                merged_raw = None
            else:
                confidence_map_raw = None
                created_raw = None
                reinforced_raw = notion_id
                weakened_raw = None
                dormant_raw = None
                decayed_raw = None
                pruned_raw = None
                merged_raw = None
                fallback_confidence = row[1]
            if not isinstance(ts, datetime):
                continue
            confidence = _parse_notion_confidences(confidence_map_raw).get(notion_id)
            if confidence is None:
                confidence = _fallback_notion_confidence(
                    notion_id,
                    fallback_confidence,
                    created_raw,
                    reinforced_raw,
                    weakened_raw,
                    dormant_raw,
                    decayed_raw,
                    pruned_raw,
                    merged_raw,
                )
            if confidence is None:
                continue
            bucket_ts = _bucket_floor(ts, bucket_delta)
            grouped[bucket_ts.isoformat()].append(confidence)

        return [
            {"ts": ts, "value": sum(values) / len(values)}
            for ts, values in sorted(grouped.items())
            if values
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
        self,
        start: datetime,
        end: datetime,
        level: str | None = None,
        *,
        search: str | None = None,
    ) -> list[dict[str, object]]:
        with psycopg.connect(self._db_url) as conn:
            with conn.cursor() as cur:
                where_clauses = ["ts >= %s", "ts <= %s"]
                params: list[object] = [start, end]

                if level:
                    where_clauses.append("level = %s")
                    params.append(level.upper())
                if search:
                    where_clauses.append(
                        "(message ILIKE %s ESCAPE '\\' OR fields::text ILIKE %s ESCAPE '\\')"
                    )
                    escaped = _escape_ilike_pattern(search)
                    needle = f"%{escaped}%"
                    params.extend([needle, needle])

                cur.execute(
                    f"""
                    SELECT ts, level, logger, message, private, fields
                    FROM log_events
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY ts ASC
                    LIMIT 300
                    """,
                    tuple(params),
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
                "latest_emotion": None,
                "latest_relationship": None,
                "tool_calls_per_min": 0,
                "error_rate": 0.0,
                "window_24h": {"tool_calls": 0, "error_rate": 0.0},
                "latest_desires": {},
                "latest_emergent_desires": {},
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
                      AND event_type IN ('tool_call_completed', 'tool_call_failed')
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
                      AND event_type IN ('tool_call_completed', 'tool_call_failed')
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
                cur.execute(
                    """
                    SELECT
                      ts,
                      emotion_primary,
                      emotion_intensity,
                      (numeric_metrics ->> 'valence')::double precision,
                      (numeric_metrics ->> 'arousal')::double precision
                    FROM tool_events
                    WHERE ts <= %s
                      AND (emotion_primary IS NOT NULL OR emotion_intensity IS NOT NULL)
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (latest_ts,),
                )
                latest_emotion_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                      (numeric_metrics ->> 'trust_level')::double precision,
                      (numeric_metrics ->> 'total_interactions')::double precision,
                      (numeric_metrics ->> 'shared_episodes_count')::double precision
                    FROM tool_events
                    WHERE ts <= %s AND numeric_metrics ? 'trust_level'
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (latest_ts,),
                )
                latest_relationship_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT numeric_metrics
                    FROM tool_events
                    WHERE ts <= %s AND tool_name = 'feel_desires'
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (latest_ts,),
                )
                latest_desire_row = cur.fetchone()
                latest_desires: dict[str, float] = {}
                if latest_desire_row is not None and isinstance(latest_desire_row[0], dict):
                    excluded = {"intensity", "valence", "arousal", "impulse_boost_amount"}
                    for key, value in latest_desire_row[0].items():
                        if key in excluded:
                            continue
                        if (
                            isinstance(key, str)
                            and (key in DESIRE_METRIC_KEYS or "want" in key.lower())
                            and isinstance(value, (int, float))
                        ):
                            latest_desires[key] = float(value)
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
        latest_emotion: dict[str, object] | None = None
        if latest_emotion_row is not None:
            (
                emotion_ts,
                emotion_primary,
                emotion_intensity,
                valence_raw,
                arousal_raw,
            ) = latest_emotion_row
            valence = float(valence_raw) if isinstance(valence_raw, (int, float)) else None
            arousal = float(arousal_raw) if isinstance(arousal_raw, (int, float)) else None
            latest_emotion = {
                "ts": emotion_ts.isoformat(),
                "emotion_primary": str(emotion_primary) if emotion_primary is not None else None,
                "emotion_intensity": (
                    float(emotion_intensity) if emotion_intensity is not None else None
                ),
                "valence": valence,
                "arousal": arousal,
            }
            if latest.get("emotion_primary") is None and emotion_primary is not None:
                latest["emotion_primary"] = str(emotion_primary)
            if latest.get("emotion_intensity") is None and emotion_intensity is not None:
                latest["emotion_intensity"] = float(emotion_intensity)
        latest_relationship: dict[str, float | None] | None = None
        if latest_relationship_row is not None:
            (
                trust_level_raw,
                total_interactions_raw,
                shared_episodes_count_raw,
            ) = latest_relationship_row
            latest_relationship = {
                "trust_level": (
                    float(trust_level_raw) if isinstance(trust_level_raw, (int, float)) else None
                ),
                "total_interactions": (
                    float(total_interactions_raw)
                    if isinstance(total_interactions_raw, (int, float))
                    else None
                ),
                "shared_episodes_count": (
                    float(shared_episodes_count_raw)
                    if isinstance(shared_episodes_count_raw, (int, float))
                    else None
                ),
            }
        latest_fixed_desires = {
            key: value for key, value in latest_desires.items() if key in DESIRE_METRIC_KEYS
        }
        latest_emergent_desires = {
            key: value for key, value in latest_desires.items() if key not in DESIRE_METRIC_KEYS
        }
        return {
            "latest": latest,
            "latest_emotion": latest_emotion,
            "latest_relationship": latest_relationship,
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
            "latest_desires": latest_fixed_desires,
            "latest_emergent_desires": latest_emergent_desires,
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
