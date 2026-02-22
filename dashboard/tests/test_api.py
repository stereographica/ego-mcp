from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ego_dashboard.api import create_app
from ego_dashboard.models import DashboardEvent
from ego_dashboard.store import TelemetryStore


def test_history_endpoints() -> None:
    store = TelemetryStore()
    store.ingest(
        DashboardEvent(
            ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            event_type="tool_call_completed",
            tool_name="feel_desires",
            ok=True,
            duration_ms=10,
            emotion_primary="curious",
            emotion_intensity=0.5,
            numeric_metrics={"intensity": 0.5},
            string_metrics={"time_phase": "night"},
            params={"time_phase": "night"},
            private=False,
            message="hello",
        )
    )
    app = create_app(store)
    client = TestClient(app)

    query = "from=2026-01-01T12:00:00Z&to=2026-01-01T12:02:00Z"
    assert client.get(f"/api/v1/usage/tools?{query}&bucket=1m").status_code == 200
    assert client.get(f"/api/v1/metrics/intensity?{query}&bucket=1m").status_code == 200
    assert client.get(f"/api/v1/metrics/time_phase/string-timeline?{query}").status_code == 200
    assert client.get(f"/api/v1/metrics/time_phase/heatmap?{query}&bucket=1m").status_code == 200
    assert client.get(f"/api/v1/alerts/anomalies?{query}&bucket=1m").status_code == 200
