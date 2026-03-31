from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import pytest

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.desire_catalog import DesireCatalog, DesireCatalogItem
from ego_dashboard.sql_store import SqlTelemetryStore


class _FakeRedis:
    def __init__(self, payload: str | None) -> None:
        self._payload = payload

    def get(self, key: str) -> str | None:
        del key
        return self._payload


class _FakeCursor:
    def __init__(
        self,
        rows: list[tuple[Any, ...] | None],
        all_rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self._rows = rows
        self._all_rows = all_rows if all_rows is not None else []
        self._index = 0

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def fetchone(self) -> tuple[Any, ...] | None:
        value = self._rows[self._index]
        self._index += 1
        return value

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._all_rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False


class _FakeConnection:
    def __init__(
        self,
        rows: list[tuple[Any, ...] | None],
        all_rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self._cursor = _FakeCursor(rows, all_rows)

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False


def _patch_store(
    monkeypatch: pytest.MonkeyPatch,
    latest_payload: dict[str, object],
    rows: list[tuple[Any, ...] | None],
    *,
    desire_catalog: DesireCatalog | None = None,
) -> SqlTelemetryStore:
    fake_redis = _FakeRedis(json.dumps(latest_payload))
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: fake_redis,
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _FakeConnection(rows),
    )
    return SqlTelemetryStore(
        "postgresql://unused",
        "redis://unused",
        desire_catalog=desire_catalog,
    )


def _catalog(*fixed_ids: tuple[str, str, int] | tuple[str, str]) -> DesireCatalog:
    items = []
    for raw in fixed_ids:
        if len(raw) == 3:
            desire_id, display_name, maslow_level = raw
        else:
            desire_id, display_name = raw
            maslow_level = 1
        items.append(
            DesireCatalogItem(
                id=desire_id,
                display_name=display_name,
                satisfaction_hours=24.0,
                maslow_level=maslow_level,
            )
        )
    return DesireCatalog(version=1, fixed_desires=tuple(items))


def test_tool_usage_prefers_log_invocations(monkeypatch: pytest.MonkeyPatch) -> None:
    bucket_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    executed: list[str] = []

    class _Cursor:
        def __init__(self) -> None:
            self._sql = ""

        def execute(self, query: object, _params: object | None = None) -> None:
            self._sql = str(query)
            executed.append(self._sql)

        def fetchall(self) -> list[tuple[Any, ...]]:
            if "FROM log_events" in self._sql:
                return [(bucket_ts, "remember", 1)]
            if "FROM tool_events" in self._sql:
                return [(bucket_ts, "remember", 2)]
            return []

        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor()

        def __enter__(self) -> _Connection:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _Connection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    rows = store.tool_usage(bucket_ts, bucket_ts + timedelta(seconds=59), bucket="1m")

    assert rows == [{"ts": bucket_ts.isoformat(), "remember": 1}]
    assert sum("FROM tool_events" in sql for sql in executed) == 0


def test_sql_store_initialize_ingest_and_checkpoint_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ego_dashboard.models import DashboardEvent, LogEvent

    statements: list[tuple[str, tuple[Any, ...] | None]] = []
    commits = 0
    redis_values: dict[str, str] = {}

    class _RecordingRedis:
        def set(self, key: str, value: str) -> None:
            redis_values[key] = value

    class _RecordingCursor:
        def __init__(self) -> None:
            self._sql = ""

        def execute(self, query: object, params: object | None = None) -> None:
            self._sql = str(query)
            tuple_params: tuple[Any, ...] | None = None
            if isinstance(params, tuple):
                tuple_params = params
            statements.append((self._sql, tuple_params))

        def fetchone(self) -> tuple[Any, ...] | None:
            if "SELECT inode, byte_offset" in self._sql:
                return (42, 7)
            return None

        def fetchall(self) -> list[tuple[Any, ...]]:
            return []

        def __enter__(self) -> _RecordingCursor:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    class _RecordingConnection:
        def cursor(self) -> _RecordingCursor:
            return _RecordingCursor()

        def commit(self) -> None:
            nonlocal commits
            commits += 1

        def __enter__(self) -> _RecordingConnection:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _RecordingRedis(),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _RecordingConnection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    store.initialize()
    store.ingest(
        DashboardEvent(
            ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            event_type="tool_call_completed",
            tool_name="remember",
            ok=True,
            duration_ms=10,
            emotion_primary="curious",
            emotion_intensity=0.4,
            numeric_metrics={"intensity": 0.4},
            string_metrics={"time_phase": "night"},
            params={"time_phase": "night"},
            private=False,
            message="ok",
        )
    )
    store.ingest_log(
        LogEvent(
            ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            level="INFO",
            logger="ego_mcp.server",
            message="secret",
            private=True,
            fields={"tool_name": "remember"},
        )
    )

    assert "dashboard:current" in redis_values
    assert any("CREATE EXTENSION IF NOT EXISTS timescaledb" in sql for sql, _ in statements)
    assert any("INSERT INTO tool_events" in sql for sql, _ in statements)
    assert any("INSERT INTO log_events" in sql for sql, _ in statements)
    assert any("CREATE TABLE IF NOT EXISTS dashboard_migrations" in sql for sql, _ in statements)
    assert any(
        "numeric_metrics = numeric_metrics - 'tool_output_chars'" in sql for sql, _ in statements
    )
    assert any("INSERT INTO dashboard_migrations" in sql for sql, _ in statements)
    assert any(
        "INSERT INTO log_events" in sql and params is not None and params[3] == "REDACTED"
        for sql, params in statements
    )
    assert commits >= 3
    assert store.load_checkpoint("/tmp/ego.log") == (42, 7)

    store.save_checkpoint("/tmp/ego.log", 99, 123)

    assert any("INSERT INTO ingestion_checkpoints" in sql for sql, _ in statements)


def test_initialize_skips_cleanup_migration_when_already_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []

    class _RecordingRedis:
        def set(self, key: str, value: str) -> None:
            del key, value

    class _RecordingCursor:
        def __init__(self) -> None:
            self._sql = ""

        def execute(self, query: object, _params: object | None = None) -> None:
            self._sql = str(query)
            statements.append(self._sql)

        def fetchone(self) -> tuple[Any, ...] | None:
            if "SELECT 1 FROM dashboard_migrations" in self._sql:
                return (1,)
            return None

        def fetchall(self) -> list[tuple[Any, ...]]:
            return []

        def __enter__(self) -> _RecordingCursor:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    class _RecordingConnection:
        def cursor(self) -> _RecordingCursor:
            return _RecordingCursor()

        def commit(self) -> None:
            return None

        def __enter__(self) -> _RecordingConnection:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _RecordingRedis(),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _RecordingConnection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    store.initialize()

    assert any("SELECT 1 FROM dashboard_migrations" in sql for sql in statements)
    assert not any(
        "numeric_metrics = numeric_metrics - 'tool_output_chars'" in sql for sql in statements
    )
    assert not any("INSERT INTO dashboard_migrations" in sql for sql in statements)


def test_tool_usage_falls_back_to_terminal_events_when_logs_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    executed: list[str] = []

    class _Cursor:
        def __init__(self) -> None:
            self._sql = ""

        def execute(self, query: object, _params: object | None = None) -> None:
            self._sql = str(query)
            executed.append(self._sql)

        def fetchall(self) -> list[tuple[Any, ...]]:
            if "FROM log_events" in self._sql:
                return []
            if "FROM tool_events" in self._sql:
                return [(bucket_ts, "remember", 1)]
            return []

        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor()

        def __enter__(self) -> _Connection:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _Connection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    rows = store.tool_usage(bucket_ts, bucket_ts + timedelta(seconds=59), bucket="1m")

    assert rows == [{"ts": bucket_ts.isoformat(), "remember": 1}]
    assert sum("FROM tool_events" in sql for sql in executed) == 1


def test_current_includes_latest_emotion_and_backfills_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    emotion_ts = datetime(2026, 1, 1, 11, 58, tzinfo=UTC)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "wake_up",
            "emotion_primary": None,
            "emotion_intensity": None,
            "private": False,
        },
        rows=[
            (1, 0),  # 1m tool counts
            (5, 1),  # 24h tool counts
            (0, 0),  # 1m log counts
            (0, 0),  # 24h log counts
            (emotion_ts, "curious", 0.7, 0.2, 0.8),  # latest emotion row
            None,  # latest relationship row
            *([None] * len(DESIRE_METRIC_KEYS)),
        ],
    )

    current = store.current()
    latest = current["latest"]
    latest_emotion = current["latest_emotion"]

    assert isinstance(latest, dict)
    assert latest["emotion_primary"] == "curious"
    assert latest["emotion_intensity"] == 0.7

    assert isinstance(latest_emotion, dict)
    assert latest_emotion["ts"] == emotion_ts.isoformat()
    assert latest_emotion["emotion_primary"] == "curious"
    assert latest_emotion["emotion_intensity"] == 0.7
    assert latest_emotion["valence"] == 0.2
    assert latest_emotion["arousal"] == 0.8


def test_current_returns_default_payload_when_no_latest_event_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )

    def _unexpected_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("database should not be queried when dashboard:current is missing")

    monkeypatch.setattr("ego_dashboard.sql_store.psycopg.connect", _unexpected_connect)

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")

    assert store.current() == {
        "latest": None,
        "latest_emotion": None,
        "latest_relationship": None,
        "tool_calls_per_min": 0,
        "error_rate": 0.0,
        "window_24h": {"tool_calls": 0, "error_rate": 0.0},
        "latest_desires": {},
        "latest_emergent_desires": {},
    }


def test_current_latest_emotion_null_when_query_has_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "wake_up",
            "emotion_primary": None,
            "emotion_intensity": None,
            "private": False,
        },
        rows=[
            (1, 0),  # 1m tool counts
            (5, 1),  # 24h tool counts
            (0, 0),  # 1m log counts
            (0, 0),  # 24h log counts
            None,  # latest emotion row
            None,  # latest relationship row
            *([None] * len(DESIRE_METRIC_KEYS)),
        ],
    )

    current = store.current()
    assert current["latest_emotion"] is None


def test_current_latest_emotion_query_is_bounded_by_latest_ts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    executed: list[tuple[str, tuple[Any, ...] | None]] = []

    class _CapturingCursor(_FakeCursor):
        def execute(self, *args: object, **kwargs: object) -> None:
            query = args[0] if args else kwargs.get("query")
            params = args[1] if len(args) > 1 else kwargs.get("params")
            sql = str(query)
            tuple_params = params if isinstance(params, tuple) else None
            executed.append((sql, tuple_params))

    class _CapturingConnection(_FakeConnection):
        def __init__(self, rows: list[tuple[Any, ...] | None]) -> None:
            self._cursor = _CapturingCursor(rows)

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(
            json.dumps(
                {
                    "ts": latest_ts.isoformat(),
                    "tool_name": "wake_up",
                    "private": False,
                }
            )
        ),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _CapturingConnection(
            [
                (1, 0),  # 1m tool counts
                (5, 1),  # 24h tool counts
                (0, 0),  # 1m log counts
                (0, 0),  # 24h log counts
                None,  # latest emotion row
                None,  # latest relationship row
                *([None] * len(DESIRE_METRIC_KEYS)),
            ]
        ),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    store.current()

    emotion_queries = [
        (sql, params)
        for sql, params in executed
        if "numeric_metrics ->> 'valence'" in sql and "FROM tool_events" in sql
    ]
    assert len(emotion_queries) == 1
    sql, params = emotion_queries[0]
    compact_sql = " ".join(sql.split())
    assert "WHERE ts <= %s" in compact_sql
    assert "(numeric_metrics ->> 'valence')::double precision" in compact_sql
    assert "(numeric_metrics ->> 'arousal')::double precision" in compact_sql
    assert params == (latest_ts,)


def test_current_includes_latest_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relationship_row = (0.82, 15.0, 3.0)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "consider_them",
            "private": False,
        },
        rows=[
            (1, 0),  # 1m tool counts
            (5, 1),  # 24h tool counts
            (0, 0),  # 1m log counts
            (0, 0),  # 24h log counts
            None,  # latest emotion row
            relationship_row,  # latest relationship row
            *([None] * len(DESIRE_METRIC_KEYS)),
        ],
    )

    current = store.current()
    latest_relationship = current["latest_relationship"]

    assert isinstance(latest_relationship, dict)
    assert latest_relationship["trust_level"] == 0.82
    assert latest_relationship["total_interactions"] == 15.0
    assert latest_relationship["shared_episodes_count"] == 3.0


def test_current_redacts_private_latest_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "remember",
            "private": True,
            "message": "secret",
        },
        rows=[
            (1, 0),
            (5, 1),
            (0, 0),
            (0, 0),
            None,
            None,
            ({"curiosity": 0.8},),
        ],
    )

    current = store.current()
    latest = cast(dict[str, object], current["latest"])

    assert latest["message"] == "REDACTED"
    assert current["latest_desires"] == {"curiosity": 0.8}


def test_current_latest_relationship_query_filters_trust_level_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    executed: list[tuple[str, tuple[Any, ...] | None]] = []

    class _CapturingCursor(_FakeCursor):
        def execute(self, *args: object, **kwargs: object) -> None:
            query = args[0] if args else kwargs.get("query")
            params = args[1] if len(args) > 1 else kwargs.get("params")
            sql = str(query)
            tuple_params = params if isinstance(params, tuple) else None
            executed.append((sql, tuple_params))

    class _CapturingConnection(_FakeConnection):
        def __init__(self, rows: list[tuple[Any, ...] | None]) -> None:
            self._cursor = _CapturingCursor(rows)

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(
            json.dumps(
                {
                    "ts": latest_ts.isoformat(),
                    "tool_name": "wake_up",
                    "private": False,
                }
            )
        ),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _CapturingConnection(
            [
                (1, 0),  # 1m tool counts
                (5, 1),  # 24h tool counts
                (0, 0),  # 1m log counts
                (0, 0),  # 24h log counts
                None,  # latest emotion row
                None,  # latest relationship row
                *([None] * len(DESIRE_METRIC_KEYS)),
            ]
        ),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    store.current()

    relationship_queries = [
        (sql, params)
        for sql, params in executed
        if "numeric_metrics ->> 'trust_level'" in sql and "FROM tool_events" in sql
    ]
    assert len(relationship_queries) == 1
    sql, params = relationship_queries[0]
    compact_sql = " ".join(sql.split())
    assert "numeric_metrics ? 'trust_level'" in compact_sql
    assert "WHERE ts <= %s" in compact_sql
    assert params == (latest_ts,)


def test_desire_metric_keys_reads_dynamic_keys_from_feel_desires_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _FakeConnection(
            rows=[],
            all_rows=[
                (
                    {
                        "curiosity": 0.7,
                        "You want to feel safe.": 0.4,
                        "impulse_boost_amount": 0.2,
                        "tool_output_chars": 387,
                    },
                )
            ],
        ),
    )
    store = SqlTelemetryStore("postgresql://unused", "redis://unused")

    keys = store.desire_metric_keys(
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 10, tzinfo=UTC),
    )

    assert keys == ["You want to feel safe.", "curiosity"]


def test_current_and_desire_keys_follow_catalog_and_hide_removed_legacy_fixed_desires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "feel_desires",
            "private": False,
        },
        rows=[
            (1, 0),
            (5, 1),
            (0, 0),
            (0, 0),
            None,
            None,
            (
                {
                    "social_thirst": 0.4,
                    "custom_focus": 0.9,
                    "predictability": 0.6,
                    "You want to feel safe.": 0.5,
                    "impulse_boost_amount": 0.2,
                    "tool_output_chars": 387,
                },
            ),
        ],
        desire_catalog=_catalog(
            ("social_thirst", "Social Thirst"),
            ("custom_focus", "Custom Focus", 2),
        ),
    )

    current = store.current()
    assert current["latest_desires"] == {
        "social_thirst": 0.4,
        "custom_focus": 0.9,
    }
    assert current["latest_emergent_desires"] == {
        "You want to feel safe.": 0.5,
    }

    class _KeyConnection(_FakeConnection):
        def __init__(self) -> None:
            self._cursor = _FakeCursor(
                [],
                all_rows=[
                    (
                        {
                            "social_thirst": 0.4,
                            "custom_focus": 0.9,
                            "predictability": 0.6,
                            "You want to feel safe.": 0.5,
                            "impulse_boost_amount": 0.2,
                            "tool_output_chars": 387,
                        },
                    )
                ],
            )

    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _KeyConnection(),
    )
    keys = store.desire_metric_keys(latest_ts - timedelta(minutes=5), latest_ts)
    assert keys == ["You want to feel safe.", "custom_focus", "social_thirst"]


def test_notion_history_prefers_per_notion_confidence_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _FakeConnection(
            rows=[],
            all_rows=[
                (
                    datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                    '{"notion_1": 0.8, "notion_2": 0.95}',
                    None,
                    "notion_1,notion_2",
                    None,
                    None,
                    0.95,
                )
            ],
        ),
    )
    store = SqlTelemetryStore("postgresql://unused", "redis://unused")

    history = store.notion_history(
        "notion_1",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        "15m",
    )

    assert history == [{"ts": "2026-01-01T12:00:00+00:00", "value": 0.8}]


def test_logs_search_escapes_ilike_meta_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[tuple[str, tuple[Any, ...] | None]] = []

    class _CapturingCursor(_FakeCursor):
        def __init__(self) -> None:
            super().__init__(rows=[], all_rows=[])

        def execute(self, *args: object, **kwargs: object) -> None:
            query = args[0] if args else kwargs.get("query")
            params = args[1] if len(args) > 1 else kwargs.get("params")
            sql = str(query)
            tuple_params: tuple[Any, ...] | None = None
            if isinstance(params, tuple):
                tuple_params = params
            elif isinstance(params, list):
                tuple_params = tuple(params)
            executed.append((sql, tuple_params))

    class _CapturingConnection(_FakeConnection):
        def __init__(self) -> None:
            self._cursor = _CapturingCursor()

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _CapturingConnection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)

    store.logs(start, end, search=r"100%_done\path")

    assert len(executed) == 1
    sql, params = executed[0]
    compact_sql = " ".join(sql.split())
    assert "message ILIKE %s ESCAPE '\\'" in compact_sql
    assert "fields::text ILIKE %s ESCAPE '\\'" in compact_sql
    assert params == (
        start,
        end,
        r"%100\%\_done\\path%",
        r"%100\%\_done\\path%",
    )


def test_current_splits_fixed_and_emergent_desires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store = _patch_store(
        monkeypatch,
        latest_payload={
            "ts": latest_ts.isoformat(),
            "tool_name": "feel_desires",
            "private": False,
        },
        rows=[
            (1, 0),
            (5, 0),
            (0, 0),
            (0, 0),
            None,
            None,
            (
                {
                    "curiosity": 0.8,
                    "You want to feel safe.": 0.55,
                    "impulse_boost_amount": 0.15,
                },
            ),
        ],
    )

    current = store.current()

    assert current["latest_desires"] == {"curiosity": 0.8}
    assert current["latest_emergent_desires"] == {"You want to feel safe.": 0.55}


def test_notion_history_returns_bucketed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _FakeConnection(
            rows=[],
            all_rows=[
                (
                    datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                    None,
                    None,
                    "notion_1",
                    None,
                    None,
                    0.7,
                )
            ],
        ),
    )
    store = SqlTelemetryStore("postgresql://unused", "redis://unused")

    rows = store.notion_history(
        "notion_1",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        "15m",
    )

    assert rows == [{"ts": "2026-01-01T12:00:00+00:00", "value": 0.7}]


def test_notion_history_uses_exact_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[tuple[str, tuple[Any, ...] | None]] = []

    class _CapturingCursor(_FakeCursor):
        def execute(self, *args: object, **kwargs: object) -> None:
            query = args[0] if args else kwargs.get("query")
            params = args[1] if len(args) > 1 else kwargs.get("params")
            sql = str(query)
            tuple_params: tuple[Any, ...] | None = None
            if isinstance(params, tuple):
                tuple_params = params
            elif isinstance(params, list):
                tuple_params = tuple(params)
            executed.append((sql, tuple_params))

    class _CapturingConnection(_FakeConnection):
        def __init__(self) -> None:
            self._cursor = _CapturingCursor(
                rows=[],
                all_rows=[
                    (
                        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                        None,
                        None,
                        "notion_1",
                        None,
                        None,
                        0.7,
                    )
                ],
            )

    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _CapturingConnection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    store.notion_history(
        "notion_1",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        "15m",
    )

    assert len(executed) == 1
    sql, params = executed[0]
    compact_sql = " ".join(sql.split())
    assert "ILIKE" not in compact_sql
    assert "string_metrics ->> 'notion_confidences'" in compact_sql
    assert "string_metrics ->> 'notion_reinforced'" in compact_sql
    assert "string_metrics ->> 'notion_decayed'" in compact_sql
    assert "string_metrics ->> 'notion_merged'" in compact_sql
    assert params == (
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
    )


def test_metric_and_string_queries_handle_notion_link_and_curation_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_dashboard.sql_store.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(None),
    )
    all_rows_queue: list[list[tuple[Any, ...]]] = [
        [
            (
                datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                2.0,
            )
        ],
        [
            (
                datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                "merge",
            )
        ],
        [
            (
                datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
                "notion_1",
            )
        ],
    ]

    class _SequencedConnection(_FakeConnection):
        def __init__(self) -> None:
            self._cursor = _FakeCursor(rows=[], all_rows=all_rows_queue.pop(0))

    monkeypatch.setattr(
        "ego_dashboard.sql_store.psycopg.connect",
        lambda *_args, **_kwargs: _SequencedConnection(),
    )

    store = SqlTelemetryStore("postgresql://unused", "redis://unused")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)

    metric_rows = store.metric_history("notion_links_created", start, end, "1m")
    action_rows = store.string_timeline("curate_action", start, end)
    notion_rows = store.string_timeline("curate_notion_id", start, end)

    assert metric_rows == [{"ts": "2026-01-01T12:00:00+00:00", "value": 2.0}]
    assert action_rows == [{"ts": "2026-01-01T12:00:00+00:00", "value": "merge"}]
    assert notion_rows == [{"ts": "2026-01-01T12:01:00+00:00", "value": "notion_1"}]
