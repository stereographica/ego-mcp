from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pytest

from ego_dashboard.migrate_emotion_telemetry import (
    EmotionSnapshot,
    build_emotion_timeline,
    find_latest_emotion_at,
    run_migration,
)


def _write_log(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "\n".join(json.dumps(row) for row in rows)
    path.write_text(f"{payload}\n", encoding="utf-8")


def test_build_emotion_timeline_uses_defaults_and_overrides(tmp_path: Path) -> None:
    log_file = tmp_path / "ego-mcp-2026-03-01.log"
    _write_log(
        log_file,
        [
            {
                "timestamp": "2026-03-01T00:00:00Z",
                "message": "Tool invocation",
                "tool_name": "remember",
                "tool_args": {"emotion": "contentment"},
            },
            {
                "timestamp": "2026-03-01T00:00:10Z",
                "message": "Tool invocation",
                "tool_name": "remember",
                "tool_args": {
                    "emotion": "melancholy",
                    "intensity": 0.9,
                    "valence": -0.2,
                    "arousal": 0.4,
                },
            },
            {
                "timestamp": "2026-03-01T00:00:20Z",
                "message": "Tool invocation",
                "tool_name": "wake_up",
                "tool_args": {},
            },
        ],
    )

    timeline = build_emotion_timeline(tmp_path)

    assert len(timeline) == 2
    assert timeline[0].emotion_primary == "contentment"
    assert timeline[0].intensity == pytest.approx(0.5)
    assert timeline[0].valence == pytest.approx(0.5)
    assert timeline[0].arousal == pytest.approx(0.2)
    assert timeline[1].emotion_primary == "melancholy"
    assert timeline[1].intensity == pytest.approx(0.9)
    assert timeline[1].valence == pytest.approx(-0.2)
    assert timeline[1].arousal == pytest.approx(0.4)


def test_find_latest_emotion_at_returns_most_recent_snapshot() -> None:
    base = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    timeline = [
        EmotionSnapshot(
            ts=base,
            emotion_primary="neutral",
            intensity=0.3,
            valence=0.0,
            arousal=0.3,
        ),
        EmotionSnapshot(
            ts=base + timedelta(seconds=30),
            emotion_primary="curious",
            intensity=0.6,
            valence=0.3,
            arousal=0.6,
        ),
    ]

    assert find_latest_emotion_at(timeline, base - timedelta(seconds=1)) is None
    latest = find_latest_emotion_at(timeline, base + timedelta(seconds=45))
    assert latest is not None
    assert latest.emotion_primary == "curious"
    assert latest.intensity == pytest.approx(0.6)


def test_dry_run_produces_no_sql_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "ego-mcp-2026-03-01.log"
    _write_log(
        log_file,
        [
            {
                "timestamp": "2026-03-01T00:00:00Z",
                "message": "Tool invocation",
                "tool_name": "remember",
                "tool_args": {"emotion": "curious"},
            }
        ],
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.executed_sql: list[str] = []

        def execute(self, query: object, _params: object | None = None) -> None:
            self.executed_sql.append(str(query))

        def fetchall(self) -> list[tuple[Any, ...]]:
            sql = self.executed_sql[-1]
            if "event_type = 'tool_call_invoked'" in sql:
                return []
            if "event_type = 'tool_call_completed'" in sql:
                return []
            return []

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()
            self.commit_called = False

        def cursor(self) -> FakeCursor:
            return self.cursor_obj

        def commit(self) -> None:
            self.commit_called = True

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    fake_connection = FakeConnection()
    monkeypatch.setattr(
        "ego_dashboard.migrate_emotion_telemetry.psycopg.connect",
        lambda *_args, **_kwargs: fake_connection,
    )

    stats = run_migration(
        log_dir=tmp_path,
        database_url="postgresql://unused",
        dry_run=True,
    )

    assert stats.timeline_entries == 1
    assert stats.cleared_completion_rows == 0
    assert stats.updated_invocations == 0
    assert stats.updated_completions == 0
    assert all(
        not statement.lstrip().upper().startswith("UPDATE")
        for statement in fake_connection.cursor_obj.executed_sql
    )
    assert fake_connection.commit_called is False
