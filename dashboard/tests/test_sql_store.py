from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

import pytest

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.sql_store import SqlTelemetryStore


class _FakeRedis:
    def __init__(self, payload: str | None) -> None:
        self._payload = payload

    def get(self, key: str) -> str | None:
        del key
        return self._payload


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...] | None]) -> None:
        self._rows = rows
        self._index = 0

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def fetchone(self) -> tuple[Any, ...] | None:
        value = self._rows[self._index]
        self._index += 1
        return value

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False


class _FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...] | None]) -> None:
        self._cursor = _FakeCursor(rows)

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
    return SqlTelemetryStore("postgresql://unused", "redis://unused")


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
            (emotion_ts, "curious", 0.7, "0.2", "0.8"),  # latest emotion row
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
    assert params == (latest_ts,)
