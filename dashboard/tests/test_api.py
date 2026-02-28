from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ego_dashboard.api import create_app
from ego_dashboard.models import DashboardEvent
from ego_dashboard.settings import DashboardSettings
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
    assert client.get(f"/api/v1/logs?{query}&level=INFO&logger=app").status_code == 200
    assert client.get(f"/api/v1/alerts/anomalies?{query}&bucket=1m").status_code == 200


def test_logs_endpoint_logger_filter_returns_partial_matches() -> None:
    from ego_dashboard.models import LogEvent

    store = TelemetryStore()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest_log(LogEvent(ts=base, level="INFO", logger="ego_mcp.server", message="hello", private=False))
    store.ingest_log(LogEvent(ts=base, level="INFO", logger="other.module", message="world", private=False))

    app = create_app(store)
    client = TestClient(app)

    query = "from=2026-01-01T12:00:00Z&to=2026-01-01T12:02:00Z"

    # Partial logger name matches only ego_mcp.server
    response = client.get(f"/api/v1/logs?{query}&logger=ego_mcp")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["logger"] == "ego_mcp.server"

    # No logger filter returns all logs
    response = client.get(f"/api/v1/logs?{query}")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_cors_preflight_allows_configured_origin() -> None:
    app = create_app(
        TelemetryStore(),
        settings=DashboardSettings(cors_allowed_origins=("http://localhost:4173",)),
    )
    client = TestClient(app)

    response = client.options(
        "/api/v1/current",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"


def test_create_app_starts_local_inmemory_ingestor_when_store_is_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    stopped = threading.Event()
    calls: list[dict[str, object]] = []

    def fake_tail_jsonl_file(
        path: str,
        store: object,
        poll_seconds: float = 1.0,
        stop_event: threading.Event | None = None,
    ) -> None:
        calls.append(
            {
                "path": path,
                "store_type": type(store).__name__,
                "poll_seconds": poll_seconds,
                "has_stop_event": stop_event is not None,
            }
        )
        started.set()
        if stop_event is not None:
            stop_event.wait(0.5)
        stopped.set()

    monkeypatch.setattr("ego_dashboard.api.tail_jsonl_file", fake_tail_jsonl_file)

    app = create_app(
        settings=DashboardSettings(
            log_path="/tmp/test-ego-mcp-*.log",
            ingest_poll_seconds=0.01,
        )
    )

    with TestClient(app):
        assert started.wait(1.0) is True

    assert stopped.wait(1.0) is True
    assert len(calls) == 1
    assert calls[0]["path"] == "/tmp/test-ego-mcp-*.log"
    assert calls[0]["store_type"] == "TelemetryStore"
    assert calls[0]["poll_seconds"] == 0.01
    assert calls[0]["has_stop_event"] is True
