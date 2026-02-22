from __future__ import annotations

import os
from pathlib import Path

from ego_dashboard.ingestor import normalize_event


def test_normalize_private_event_is_redacted() -> None:
    raw = {
        "ts": "2026-01-01T12:00:00Z",
        "event_type": "tool_call_completed",
        "tool_name": "remember",
        "private": True,
        "message": "secret",
        "params": {"time_phase": "night", "note": "sensitive"},
    }

    event = normalize_event(raw)

    assert event.private is True
    assert event.message == "REDACTED"
    assert event.params == {"time_phase": "night"}


def test_normalize_numeric_and_string_metrics() -> None:
    raw = {
        "ts": "2026-01-01T12:00:00Z",
        "tool_name": "feel_desires",
        "emotion_intensity": 0.72,
        "params": {"valence": 0.2, "time_phase": "night"},
    }

    event = normalize_event(raw)

    assert event.numeric_metrics["intensity"] == 0.72
    assert event.numeric_metrics["valence"] == 0.2
    assert event.string_metrics["time_phase"] == "night"


def test_parse_jsonl_for_log_event() -> None:
    from ego_dashboard.ingestor import parse_jsonl_line

    line = (
        '{"ts":"2026-01-01T12:00:00Z","level":"INFO","logger":"app","message":"x","private":true}'
    )
    event, log = parse_jsonl_line(line)
    assert event is None
    assert log is not None
    assert log.message == "REDACTED"


def test_parse_jsonl_for_ego_mcp_log_timestamp_field() -> None:
    from ego_dashboard.ingestor import parse_jsonl_line

    line = (
        '{"timestamp":"2026-01-01T12:34:56Z",'
        '"level":"INFO",'
        '"logger":"ego_mcp.server",'
        '"message":"Tool invocation"}'
    )
    event, log = parse_jsonl_line(line)
    assert event is None
    assert log is not None
    assert log.ts.isoformat() == "2026-01-01T12:34:56+00:00"
    assert log.logger == "ego_mcp.server"


def test_select_source_file_uses_latest_match(tmp_path: Path) -> None:
    from ego_dashboard.ingestor import _select_source_file

    older = tmp_path / "ego-mcp-2026-01-01.log"
    newer = tmp_path / "ego-mcp-2026-01-02.log"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    selected = _select_source_file(str(tmp_path / "ego-mcp-*.log"))

    assert selected == str(newer)
