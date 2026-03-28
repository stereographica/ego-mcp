from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from ego_dashboard.api import _load_memory_network, create_app
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
    assert client.get(f"/api/v1/desires/keys?{query}").status_code == 200
    assert client.get(f"/api/v1/logs?{query}&level=INFO&search=hello").status_code == 200
    assert client.get(f"/api/v1/alerts/anomalies?{query}&bucket=1m").status_code == 200


def test_logs_endpoint_search_filter_returns_partial_matches() -> None:
    from ego_dashboard.models import LogEvent

    store = TelemetryStore()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest_log(
        LogEvent(
            ts=base,
            level="INFO",
            logger="ego_mcp.server",
            message="hello",
            private=False,
            fields={"tool_name": "remember"},
        )
    )
    store.ingest_log(
        LogEvent(ts=base, level="INFO", logger="other.module", message="world", private=False)
    )

    app = create_app(store)
    client = TestClient(app)

    query = "from=2026-01-01T12:00:00Z&to=2026-01-01T12:02:00Z"

    response = client.get(f"/api/v1/logs?{query}&search=remember")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["logger"] == "ego_mcp.server"

    # No search filter returns all logs
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


def test_memory_network_and_notions_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion_path = tmp_path / "notions.json"
    notion_path.write_text(
        json.dumps(
            {
                "notion_1": {
                    "label": "rain & outing (frustrated)",
                    "emotion_tone": "frustrated",
                    "confidence": 0.7,
                    "source_memory_ids": ["mem_1", "mem_2"],
                    "created": "2026-01-01T12:00:00+00:00",
                    "last_reinforced": "2026-01-02T12:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ego_dashboard.api._load_memory_network",
        lambda _settings: {
            "nodes": [
                {
                    "id": "mem_1",
                    "category": "daily",
                    "decay": 0.8,
                    "access_count": 3,
                    "is_notion": False,
                },
                {
                    "id": "notion_1",
                    "label": "rain & outing (frustrated)",
                    "category": "notion",
                    "decay": 0.7,
                    "access_count": 2,
                    "confidence": 0.7,
                    "is_notion": True,
                },
            ],
            "edges": [
                {
                    "source": "mem_1",
                    "target": "notion_1",
                    "link_type": "notion_source",
                    "confidence": 0.7,
                }
            ],
        },
    )

    app = create_app(
        TelemetryStore(),
        settings=DashboardSettings(ego_mcp_data_dir=str(tmp_path)),
    )
    client = TestClient(app)

    network = client.get("/api/v1/memory/network")
    assert network.status_code == 200
    assert network.json()["nodes"][0]["id"] == "mem_1"
    assert network.json()["nodes"][1]["is_notion"] is True
    assert network.json()["edges"][0]["link_type"] == "notion_source"

    notions = client.get("/api/v1/notions")
    assert notions.status_code == 200
    item = notions.json()["items"][0]
    assert item["label"] == "rain & outing (frustrated)"
    assert item["emotion_tone"] == "frustrated"
    assert item["confidence"] == 0.7
    assert item["source_count"] == 2
    assert item["created"] == "2026-01-01T12:00:00+00:00"
    assert item["last_reinforced"] == "2026-01-02T12:00:00+00:00"


def test_load_memory_network_uses_existing_collection_in_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    collection_calls: list[dict[str, object]] = []

    class _FakeCollection:
        def get(
            self,
            *,
            limit: int,
            offset: int,
            include: list[str],
        ) -> dict[str, object]:
            collection_calls.append({"limit": limit, "offset": offset, "include": tuple(include)})
            if offset == 0:
                return {
                    "ids": ["mem_1"],
                    "documents": ["Memory one with a readable summary"],
                    "metadatas": [
                        {
                            "category": "daily",
                            "timestamp": "2026-01-01T12:00:00+00:00",
                            "access_count": 2,
                            "linked_ids": json.dumps(
                                [
                                    {
                                        "target_id": "mem_2",
                                        "link_type": "related",
                                        "confidence": 0.4,
                                    }
                                ]
                            ),
                        }
                    ],
                }
            if offset == 1:
                return {
                    "ids": ["mem_2"],
                    "documents": ["Private note that should stay hidden"],
                    "metadatas": [
                        {
                            "category": "daily",
                            "timestamp": "2026-01-01T12:00:00+00:00",
                            "access_count": 5,
                            "linked_ids": "[]",
                            "is_private": True,
                        }
                    ],
                }
            return {"ids": [], "documents": [], "metadatas": []}

    class _FakePersistentClient:
        def __init__(self, path: str) -> None:
            self.path = path
            self.collection_requested: str | None = None
            self.collection = _FakeCollection()

        def get_collection(self, name: str) -> _FakeCollection:
            self.collection_requested = name
            return self.collection

    monkeypatch.setattr("ego_dashboard.api.chromadb.PersistentClient", _FakePersistentClient)
    monkeypatch.setattr(
        "ego_dashboard.api._calculate_memory_decay",
        lambda timestamp, *, link_confidence_max, access_count, now=None: (
            access_count + link_confidence_max + 0.12
        ),
    )
    monkeypatch.setattr("ego_dashboard.api._MEMORY_NETWORK_BATCH_SIZE", 1)

    result = _load_memory_network(DashboardSettings(ego_mcp_data_dir=str(tmp_path)))
    nodes = cast(list[dict[str, object]], result["nodes"])
    edges = cast(list[dict[str, object]], result["edges"])

    assert collection_calls == [
        {"limit": 1, "offset": 0, "include": ("documents", "metadatas")},
        {"limit": 1, "offset": 1, "include": ("documents", "metadatas")},
        {"limit": 1, "offset": 2, "include": ("documents", "metadatas")},
    ]
    assert nodes[0]["id"] == "mem_1"
    assert nodes[0]["label"] == "Memory one with a readable summary"
    assert nodes[1]["access_count"] == 5
    assert nodes[1]["label"] == "REDACTED"
    assert nodes[0]["decay"] == pytest.approx(2.52)
    assert edges == [
        {
            "source": "mem_1",
            "target": "mem_2",
            "link_type": "related",
            "confidence": 0.4,
        }
    ]


def test_load_memory_network_keeps_notion_nodes_when_memory_load_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    (tmp_path / "notions.json").write_text(
        json.dumps(
            {
                "notion_1": {
                    "label": "pattern & signal (curious)",
                    "emotion_tone": "curious",
                    "confidence": 0.8,
                    "source_memory_ids": ["mem_1"],
                    "created": "2026-01-01T12:00:00+00:00",
                    "last_reinforced": "2026-01-02T12:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )

    class _ExplodingPersistentClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_collection(self, name: str) -> None:
            raise RuntimeError(f"cannot open {name}")

    monkeypatch.setattr("ego_dashboard.api.chromadb.PersistentClient", _ExplodingPersistentClient)

    result = _load_memory_network(DashboardSettings(ego_mcp_data_dir=str(tmp_path)))

    assert result["nodes"] == [
        {
            "id": "notion_1",
            "label": "pattern & signal (curious)",
            "is_notion": True,
            "confidence": 0.8,
            "access_count": 1,
            "decay": 0.8,
            "category": "notion",
        }
    ]
    assert result["edges"] == [
        {
            "source": "notion_1",
            "target": "mem_1",
            "link_type": "notion_source",
            "confidence": 0.8,
        }
    ]


def test_notion_history_endpoint_returns_bucketed_items() -> None:
    store = TelemetryStore()
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ingest(
        DashboardEvent(
            ts=start,
            event_type="tool_call_completed",
            tool_name="consolidate",
            ok=True,
            duration_ms=10,
            numeric_metrics={"notion_confidence": 0.6},
            string_metrics={
                "notion_created": "notion_1",
                "notion_confidences": json.dumps({"notion_1": 0.6}),
            },
            params={},
            private=False,
        )
    )
    store.ingest(
        DashboardEvent(
            ts=start + timedelta(minutes=5),
            event_type="tool_call_completed",
            tool_name="remember",
            ok=True,
            duration_ms=10,
            numeric_metrics={"notion_confidence": 0.95},
            string_metrics={
                "notion_reinforced": "notion_1,notion_2",
                "notion_confidences": json.dumps({"notion_1": 0.8, "notion_2": 0.95}),
            },
            params={},
            private=False,
        )
    )
    app = create_app(store)
    client = TestClient(app)

    response = client.get(
        "/api/v1/notions/notion_1/history"
        "?from=2026-01-01T12:00:00Z&to=2026-01-01T12:30:00Z&bucket=15m"
    )

    assert response.status_code == 200
    assert response.json()["items"] == [{"ts": "2026-01-01T12:00:00+00:00", "value": 0.7}]
