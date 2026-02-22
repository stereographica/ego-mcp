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
