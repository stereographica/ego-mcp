from __future__ import annotations

import os
from pathlib import Path

from ego_dashboard.ingestor import EgoMcpLogProjector, normalize_event


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
    assert log.fields == {}


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
    assert log.fields == {}


def test_parse_jsonl_preserves_extra_log_fields() -> None:
    from ego_dashboard.ingestor import parse_jsonl_line

    line = (
        '{"timestamp":"2026-01-01T12:34:56Z",'
        '"level":"INFO",'
        '"logger":"ego_mcp.server",'
        '"message":"Tool invocation",'
        '"tool_name":"remember",'
        '"tool_args":{"emotion":"curious"}}'
    )
    event, log = parse_jsonl_line(line)
    assert event is None
    assert log is not None
    assert log.fields["tool_name"] == "remember"


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


def test_resolve_source_files_returns_all_matches(tmp_path: Path) -> None:
    from ego_dashboard.ingestor import _resolve_source_files

    first = tmp_path / "ego-mcp-2026-01-01.log"
    second = tmp_path / "ego-mcp-2026-01-02.log"
    first.write_text("{}\n", encoding="utf-8")
    second.write_text("{}\n", encoding="utf-8")

    resolved = _resolve_source_files(str(tmp_path / "ego-mcp-*.log"))

    assert resolved == [str(first), str(second)]


def test_projector_creates_event_from_invocation_and_ignores_non_feel_desires_completion() -> None:
    projector = EgoMcpLogProjector()

    invocation = {
        "timestamp": "2026-01-01T12:00:00Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool invocation",
        "tool_name": "remember",
        "tool_args": {
            "emotion": "curious",
            "intensity": 0.7,
            "private": False,
            "body_state": {"time_phase": "night"},
        },
    }
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "remember",
    }

    event = projector.project(invocation)

    assert event is not None
    assert event.tool_name == "remember"
    assert event.ok is True
    assert event.emotion_primary == "curious"
    assert event.emotion_intensity == 0.7
    assert event.string_metrics["time_phase"] == "night"
    assert projector.project(completion) is None


def test_projector_parses_feel_desires_completion_metrics() -> None:
    projector = EgoMcpLogProjector()
    invocation = {
        "timestamp": "2026-01-01T12:00:00Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool invocation",
        "tool_name": "feel_desires",
        "tool_args": {},
        "time_phase": "night",
    }
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "feel_desires",
        "time_phase": "night",
        "tool_output": (
            "information_hunger[0.8/high] social_thirst[0.4/mid] "
            "cognitive_coherence[0.2/low] curiosity[0.7/high]\n\n"
            "---\nAfter acting on a desire, use satisfy_desire."
        ),
    }

    assert projector.project(invocation) is None

    event = projector.project(completion)

    assert event is not None
    assert event.tool_name == "feel_desires"
    assert event.ok is True
    assert event.string_metrics["time_phase"] == "night"
    assert event.numeric_metrics["information_hunger"] == 0.8
    assert event.numeric_metrics["social_thirst"] == 0.4
    assert event.numeric_metrics["cognitive_coherence"] == 0.2
    assert event.numeric_metrics["curiosity"] == 0.7


def test_projector_reads_top_level_time_phase_from_ego_mcp_logs() -> None:
    projector = EgoMcpLogProjector()
    invocation = {
        "timestamp": "2026-01-01T12:00:00Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool invocation",
        "tool_name": "wake_up",
        "tool_args": {},
        "time_phase": "afternoon",
    }

    event = projector.project(invocation)

    assert event is not None
    assert event.tool_name == "wake_up"
    assert event.string_metrics["time_phase"] == "afternoon"
