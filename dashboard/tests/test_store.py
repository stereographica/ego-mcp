from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from ego_dashboard.models import DashboardEvent
from ego_dashboard.store import TelemetryStore


def _event(minutes: int, tool: str, intensity: float, time_phase: str) -> DashboardEvent:
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)
    return DashboardEvent(
        ts=ts,
        event_type="tool_call_completed",
        tool_name=tool,
        ok=True,
        duration_ms=50,
        emotion_primary="curious",
        emotion_intensity=intensity,
        numeric_metrics={"intensity": intensity},
        string_metrics={"time_phase": time_phase},
        params={"time_phase": time_phase},
        private=False,
        message="ok",
    )


def test_tool_usage_and_metric_history() -> None:
    store = TelemetryStore()
    store.ingest(_event(0, "feel_desires", 0.3, "morning"))
    store.ingest(_event(1, "feel_desires", 0.6, "morning"))
    store.ingest(_event(1, "remember", 0.8, "night"))

    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 3, tzinfo=UTC)

    usage = store.tool_usage(start, end, bucket="1m")
    intensity = store.metric_history("intensity", start, end, bucket="1m")

    assert usage[0]["feel_desires"] == 1
    assert usage[1]["feel_desires"] == 1
    assert usage[1]["remember"] == 1
    assert intensity[0]["value"] == 0.3
    assert intensity[1]["value"] == 0.7


def test_string_visualization_and_anomaly_detection() -> None:
    store = TelemetryStore()
    for minute in range(5):
        store.ingest(_event(minute, "feel_desires", 0.2, "day"))
    for minute in range(5, 10):
        store.ingest(_event(minute, "feel_desires", 0.9, "night"))

    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 11, tzinfo=UTC)

    timeline = store.string_timeline("time_phase", start, end)
    heatmap = store.string_heatmap("time_phase", start, end, bucket="5m")
    alerts = store.anomaly_alerts(start, end, bucket="5m")

    assert timeline[0]["value"] == "day"
    assert timeline[-1]["value"] == "night"
    first_counts = cast(dict[str, Any], heatmap[0]["counts"])
    second_counts = cast(dict[str, Any], heatmap[1]["counts"])
    assert first_counts["day"] == 5
    assert second_counts["night"] == 5
    assert any(alert["kind"] == "intensity_spike" for alert in alerts)


def test_logs_filtering() -> None:
    from ego_dashboard.models import LogEvent

    store = TelemetryStore()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest_log(
        LogEvent(
            ts=base,
            level="INFO",
            logger="a",
            message="ok",
            private=False,
            fields={"tool_name": "remember"},
        )
    )
    store.ingest_log(LogEvent(ts=base, level="ERROR", logger="a", message="ng", private=False))
    logs = store.logs(base, base + timedelta(minutes=1), "ERROR", "a")
    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"

    info_logs = store.logs(base, base + timedelta(minutes=1), "INFO", "a")
    assert info_logs[0]["fields"] == {"tool_name": "remember"}


def test_current_backfills_latest_emotion_from_recent_telemetry() -> None:
    store = TelemetryStore()
    store.ingest(_event(0, "remember", 0.8, "night"))
    store.ingest(
        _event(1, "wake_up", 0.0, "morning").model_copy(
            update={"emotion_primary": None, "emotion_intensity": None}
        )
    )

    current = store.current()
    latest = cast(dict[str, Any], current["latest"])

    assert latest["emotion_primary"] == "curious"
    assert latest["emotion_intensity"] == 0.8


def test_current_prefers_log_derived_counts_and_error_rate() -> None:
    from ego_dashboard.models import LogEvent

    store = TelemetryStore()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest(_event(0, "remember", 0.8, "night"))
    store.ingest_log(
        LogEvent(
            ts=base,
            level="INFO",
            logger="ego_mcp.server",
            message="Tool invocation",
            private=False,
            fields={"tool_name": "remember"},
        )
    )
    store.ingest_log(
        LogEvent(
            ts=base + timedelta(seconds=2),
            level="ERROR",
            logger="ego_mcp.server",
            message="Tool execution failed",
            private=False,
        )
    )

    current = store.current()

    assert current["tool_calls_per_min"] == 1
    assert current["error_rate"] == 1.0


def test_current_exposes_24h_window_and_latest_desires() -> None:
    from ego_dashboard.models import LogEvent

    store = TelemetryStore()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest(
        DashboardEvent(
            ts=base - timedelta(hours=2),
            event_type="tool_call_completed",
            tool_name="feel_desires",
            ok=True,
            duration_ms=10,
            numeric_metrics={
                "information_hunger": 0.8,
                "social_thirst": 0.3,
                "cognitive_coherence": 0.6,
            },
            private=False,
        )
    )
    store.ingest(_event(0, "remember", 0.4, "day"))
    store.ingest_log(
        LogEvent(
            ts=base - timedelta(hours=1),
            level="INFO",
            logger="ego_mcp.server",
            message="Tool invocation",
            private=False,
            fields={"tool_name": "feel_desires"},
        )
    )
    store.ingest_log(
        LogEvent(
            ts=base - timedelta(minutes=30),
            level="INFO",
            logger="ego_mcp.server",
            message="Tool invocation",
            private=False,
            fields={"tool_name": "remember"},
        )
    )
    store.ingest_log(
        LogEvent(
            ts=base - timedelta(minutes=29),
            level="ERROR",
            logger="ego_mcp.server",
            message="Tool execution failed",
            private=False,
        )
    )

    current = store.current()

    window_24h = cast(dict[str, Any], current["window_24h"])
    latest_desires = cast(dict[str, Any], current["latest_desires"])

    assert window_24h["tool_calls"] == 2
    assert window_24h["error_rate"] == 0.5
    assert latest_desires["information_hunger"] == 0.8
    assert latest_desires["social_thirst"] == 0.3
    assert latest_desires["cognitive_coherence"] == 0.6
