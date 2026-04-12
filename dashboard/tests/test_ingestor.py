from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ego_dashboard.desire_catalog import DesireCatalog, DesireCatalogItem
from ego_dashboard.ingestor import EgoMcpLogProjector, normalize_event


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


def test_projector_creates_event_from_invocation() -> None:
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

    event = projector.project(invocation)

    assert event is not None
    assert event.tool_name == "remember"
    assert event.ok is True
    assert event.emotion_primary == "curious"
    assert event.emotion_intensity == 0.7
    assert event.string_metrics["time_phase"] == "night"


def test_projector_creates_event_from_non_feel_desires_completion() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "remember",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "valence": 0.2,
        "arousal": 0.7,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.event_type == "tool_call_completed"
    assert event.tool_name == "remember"
    assert event.ok is True
    assert event.emotion_primary == "curious"
    assert event.emotion_intensity == 0.65
    assert event.numeric_metrics["valence"] == 0.2
    assert event.numeric_metrics["arousal"] == 0.7


def test_projector_creates_event_from_non_feel_desires_failure() -> None:
    projector = EgoMcpLogProjector()
    failure = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "ERROR",
        "logger": "ego_mcp.server",
        "message": "Tool execution failed",
        "tool_name": "remember",
        "emotion_primary": "concerned",
        "emotion_intensity": 0.4,
        "valence": -0.2,
        "arousal": 0.6,
    }

    event = projector.project(failure)

    assert event is not None
    assert event.event_type == "tool_call_failed"
    assert event.tool_name == "remember"
    assert event.ok is False
    assert event.emotion_primary == "concerned"
    assert event.emotion_intensity == 0.4
    assert event.numeric_metrics["valence"] == -0.2
    assert event.numeric_metrics["arousal"] == 0.6


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
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "valence": 0.2,
        "arousal": 0.7,
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
    assert event.emotion_primary == "curious"
    assert event.emotion_intensity == 0.65
    assert event.string_metrics["time_phase"] == "night"
    assert event.numeric_metrics["valence"] == 0.2
    assert event.numeric_metrics["arousal"] == 0.7
    assert event.numeric_metrics["information_hunger"] == 0.8
    assert event.numeric_metrics["social_thirst"] == 0.4
    assert event.numeric_metrics["cognitive_coherence"] == 0.2
    assert event.numeric_metrics["curiosity"] == 0.7


def test_projector_carries_attune_desire_metrics_from_completion_log() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "attune",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "valence": 0.2,
        "arousal": 0.7,
        "time_phase": "night",
        "desire_levels": {
            "information_hunger": 0.8,
            "curiosity": 0.7,
        },
        "information_hunger": 0.8,
        "curiosity": 0.7,
        "You want to feel safe.": 0.4,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.tool_name == "attune"
    assert event.ok is True
    assert event.string_metrics["time_phase"] == "night"
    assert event.numeric_metrics["information_hunger"] == 0.8
    assert event.numeric_metrics["curiosity"] == 0.7
    assert event.numeric_metrics["You want to feel safe."] == 0.4


def test_projector_skips_attune_invocation_event() -> None:
    """Attune invocation events should be skipped like feel_desires (Finding 7)."""
    projector = EgoMcpLogProjector()
    invocation = {
        "timestamp": "2026-01-01T12:00:00Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool invocation",
        "tool_name": "attune",
        "tool_args": {},
    }
    event = projector.project(invocation)
    assert event is None


def test_projector_parses_attune_desire_levels_from_structured_dict() -> None:
    """Attune should use _parse_feel_desires_levels for structured desire_levels (Finding 8)."""
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "attune",
        "desire_levels": {
            "information_hunger": 0.8,
            "curiosity": 0.7,
        },
    }
    event = projector.project(completion)
    assert event is not None
    assert event.numeric_metrics["information_hunger"] == 0.8
    assert event.numeric_metrics["curiosity"] == 0.7


def test_projector_preserves_forgetting_and_notion_metrics() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "remember",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "fuzzy_recall_count": 2,
        "resurfaced_memory_id": "mem_old",
        "notion_reinforced": "notion_1",
        "notion_confidence": 0.7,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["fuzzy_recall_count"] == 2
    assert event.numeric_metrics["notion_confidence"] == 0.7
    assert event.string_metrics["resurfaced_memory_id"] == "mem_old"
    assert event.string_metrics["notion_reinforced"] == "notion_1"


def test_projector_preserves_notion_link_and_curation_metrics() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "consolidate",
        "notion_links_created": 2,
        "curate_action": "merge",
        "curate_notion_id": "notion_1",
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["notion_links_created"] == 2
    assert event.string_metrics["curate_action"] == "merge"
    assert event.string_metrics["curate_notion_id"] == "notion_1"


def test_projector_parses_top_level_dynamic_desires_and_impulse_metrics() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "feel_desires",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "curiosity": 0.8,
        "You want to feel safe.": 0.55,
        "emergent_desire_created": "You want to feel safe.",
        "impulse_boost_triggered": True,
        "impulse_boosted_desire": "curiosity",
        "impulse_boost_amount": 0.15,
        "tool_output_chars": 387,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["curiosity"] == 0.8
    assert event.numeric_metrics["You want to feel safe."] == 0.55
    assert event.numeric_metrics["impulse_boost_amount"] == 0.15
    assert "tool_output_chars" not in event.numeric_metrics
    assert event.string_metrics["emergent_desire_created"] == "You want to feel safe."
    assert event.string_metrics["impulse_boosted_desire"] == "curiosity"
    assert event.params["impulse_boost_triggered"] is True


def test_projector_prefers_structured_desire_levels_and_ignores_tool_output_chars() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "feel_desires",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "desire_levels": {
            "curiosity": 0.8,
            "You want to feel safe.": 0.55,
        },
        "curiosity": 0.1,
        "You want to feel safe.": 0.2,
        "impulse_boost_amount": 0.15,
        "tool_output_chars": 387,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["curiosity"] == 0.8
    assert event.numeric_metrics["You want to feel safe."] == 0.55
    assert event.numeric_metrics["impulse_boost_amount"] == 0.15
    assert "tool_output_chars" not in event.numeric_metrics


def test_projector_uses_catalog_to_keep_custom_fixed_and_hide_removed_legacy_fixed() -> None:
    projector = EgoMcpLogProjector(
        _catalog(
            ("social_thirst", "Social Thirst"),
            ("custom_focus", "Custom Focus", 2),
        )
    )
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "feel_desires",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "social_thirst": 0.4,
        "custom_focus": 0.9,
        "predictability": 0.6,
        "You want to feel safe.": 0.55,
        "impulse_boost_amount": 0.15,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["social_thirst"] == 0.4
    assert event.numeric_metrics["custom_focus"] == 0.9
    assert event.numeric_metrics["You want to feel safe."] == 0.55
    assert "predictability" not in event.numeric_metrics


def test_projector_parses_feel_desires_levels_from_tool_output_fallback() -> None:
    projector = EgoMcpLogProjector(
        _catalog(
            ("social_thirst", "Social Thirst"),
            ("custom_focus", "Custom Focus", 2),
        )
    )
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "feel_desires",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "tool_output": (
            "social_thirst[0.4/high] custom_focus[0.9/high] "
            "predictability[0.5/high] novel_interest[0.7/high]\n\n"
            "---\nBlend summary"
        ),
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["social_thirst"] == 0.4
    assert event.numeric_metrics["custom_focus"] == 0.9
    assert event.numeric_metrics["novel_interest"] == 0.7
    assert "predictability" not in event.numeric_metrics


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


def test_projector_reads_structured_relationship_metrics() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "consider_them",
        "emotion_primary": "curious",
        "emotion_intensity": 0.65,
        "trust_level": 0.82,
        "total_interactions": 15,
        "shared_episodes_count": 3,
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["trust_level"] == 0.82
    assert event.numeric_metrics["total_interactions"] == 15
    assert event.numeric_metrics["shared_episodes_count"] == 3


def test_projector_parses_relationship_metrics_from_tool_output_fallback() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "consider_them",
        "tool_output": "Master: trust=0.75, interactions=9, shared_episodes=2",
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["trust_level"] == 0.75
    assert event.numeric_metrics["total_interactions"] == 9
    assert event.numeric_metrics["shared_episodes_count"] == 2


def test_projector_prefers_structured_relationship_metrics_over_tool_output() -> None:
    projector = EgoMcpLogProjector()
    completion = {
        "timestamp": "2026-01-01T12:00:02Z",
        "level": "INFO",
        "logger": "ego_mcp.server",
        "message": "Tool execution completed",
        "tool_name": "wake_up",
        "trust_level": 0.82,
        "total_interactions": 15,
        "shared_episodes_count": 3,
        "tool_output": "Master: trust=0.10, interactions=1, shared_episodes=0",
    }

    event = projector.project(completion)

    assert event is not None
    assert event.numeric_metrics["trust_level"] == 0.82
    assert event.numeric_metrics["total_interactions"] == 15
    assert event.numeric_metrics["shared_episodes_count"] == 3


def test_ingest_jsonl_line_only_stores_ego_mcp_server_logs() -> None:
    from ego_dashboard.ingestor import ingest_jsonl_line

    class _CaptureStore:
        def __init__(self) -> None:
            self.events: list[object] = []
            self.logs: list[object] = []

        def ingest(self, event: object) -> None:
            self.events.append(event)

        def ingest_log(self, event: object) -> None:
            self.logs.append(event)

    store = _CaptureStore()
    ingest_jsonl_line(
        '{"timestamp":"2026-01-01T12:00:00Z","level":"INFO","logger":"other.module","message":"x"}',
        store,
    )
    ingest_jsonl_line(
        '{"timestamp":"2026-01-01T12:00:00Z","level":"INFO","logger":"ego_mcp.server","message":"y"}',
        store,
    )

    assert len(store.events) == 0
    assert len(store.logs) == 1


class _CheckpointCaptureStore:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.logs: list[object] = []
        self.checkpoints: dict[str, tuple[int, int]] = {}

    def ingest(self, event: object) -> None:
        self.events.append(event)

    def ingest_log(self, event: object) -> None:
        self.logs.append(event)

    def load_checkpoint(self, path: str) -> tuple[int, int] | None:
        return self.checkpoints.get(path)

    def save_checkpoint(self, path: str, inode: int, offset: int) -> None:
        self.checkpoints[path] = (inode, offset)


def _append_json_line(path: Path, payload: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def _wait_until(predicate: object, timeout: float = 1.0) -> bool:
    if not callable(predicate):
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _run_tail_once(
    path: str,
    store: _CheckpointCaptureStore,
    *,
    wait_for: object | None = None,
) -> None:
    from ego_dashboard.ingestor import tail_jsonl_file

    stop_event = threading.Event()
    thread = threading.Thread(
        target=tail_jsonl_file,
        args=(path, store),
        kwargs={"poll_seconds": 0.01, "stop_event": stop_event},
    )
    thread.start()
    try:
        if wait_for is not None:
            assert _wait_until(wait_for)
        else:
            time.sleep(0.05)
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        assert thread.is_alive() is False


def test_tail_jsonl_file_resumes_from_saved_checkpoint(tmp_path: Path) -> None:
    log_path = tmp_path / "ego-mcp-2026-01-01.log"
    _append_json_line(
        log_path,
        {
            "ts": "2026-01-01T12:00:00Z",
            "event_type": "tool_call_completed",
            "tool_name": "remember",
        },
    )
    store = _CheckpointCaptureStore()

    _run_tail_once(str(log_path), store, wait_for=lambda: len(store.events) == 1)
    first_checkpoint = store.checkpoints[str(log_path)]

    _run_tail_once(str(log_path), store)

    assert len(store.events) == 1
    assert store.checkpoints[str(log_path)] == first_checkpoint
    assert first_checkpoint[1] == log_path.stat().st_size


def test_tail_jsonl_file_tracks_checkpoints_per_globbed_file(tmp_path: Path) -> None:
    first = tmp_path / "ego-mcp-2026-01-01.log"
    second = tmp_path / "ego-mcp-2026-01-02.log"
    _append_json_line(
        first,
        {
            "ts": "2026-01-01T12:00:00Z",
            "event_type": "tool_call_completed",
            "tool_name": "remember",
        },
    )
    _append_json_line(
        second,
        {
            "ts": "2026-01-02T12:00:00Z",
            "event_type": "tool_call_completed",
            "tool_name": "wake_up",
        },
    )
    store = _CheckpointCaptureStore()

    _run_tail_once(str(tmp_path / "ego-mcp-*.log"), store, wait_for=lambda: len(store.events) == 2)
    first_checkpoint = store.checkpoints[str(first)]
    second_checkpoint = store.checkpoints[str(second)]

    _append_json_line(
        first,
        {
            "ts": "2026-01-01T12:05:00Z",
            "event_type": "tool_call_completed",
            "tool_name": "consider_them",
        },
    )
    _run_tail_once(str(tmp_path / "ego-mcp-*.log"), store, wait_for=lambda: len(store.events) == 3)

    assert len(store.events) == 3
    assert store.checkpoints[str(first)][1] > first_checkpoint[1]
    assert store.checkpoints[str(second)] == second_checkpoint
