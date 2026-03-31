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


def _write_desire_catalog(tmp_path: Path) -> None:
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    (settings_dir / "desires.json").write_text(
        json.dumps(
            {
                "version": 1,
                "fixed_desires": {
                    "social_thirst": {
                        "display_name": "Social Thirst",
                        "satisfaction_hours": 24,
                        "maslow_level": 1,
                        "sentence": {
                            "medium": "You want some company.",
                            "high": "You need to talk to someone.",
                        },
                        "implicit_satisfaction": {
                            "consider_them": 0.4,
                        },
                    },
                    "custom_focus": {
                        "display_name": "Custom Focus",
                        "satisfaction_hours": 8,
                        "maslow_level": 2,
                        "sentence": {
                            "medium": "You want to focus.",
                            "high": "You urgently need to focus.",
                        },
                        "implicit_satisfaction": {
                            "recall": 0.2,
                        },
                    },
                },
                "implicit_rules": [],
                "emergent": {
                    "satisfaction_hours": 24,
                },
            }
        ),
        encoding="utf-8",
    )


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


def test_desire_catalog_endpoint_reads_fixed_desires_from_settings(tmp_path: Path) -> None:
    _write_desire_catalog(tmp_path)

    app = create_app(
        TelemetryStore(),
        settings=DashboardSettings(ego_mcp_data_dir=str(tmp_path)),
    )
    client = TestClient(app)

    response = client.get("/api/v1/desires/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert [item["id"] for item in payload["fixed_desires"]] == [
        "social_thirst",
        "custom_focus",
    ]
    assert payload["fixed_desires"][0]["display_name"] == "Social Thirst"


def test_desire_catalog_endpoint_reports_invalid_json(tmp_path: Path) -> None:
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    (settings_dir / "desires.json").write_text("{broken", encoding="utf-8")

    app = create_app(
        TelemetryStore(),
        settings=DashboardSettings(ego_mcp_data_dir=str(tmp_path)),
    )
    client = TestClient(app)

    response = client.get("/api/v1/desires/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid"
    assert payload["fixed_desires"] == []
    assert payload["errors"]


def test_desire_catalog_endpoint_uses_default_catalog_without_data_dir() -> None:
    app = create_app(TelemetryStore(), settings=DashboardSettings())
    client = TestClient(app)

    response = client.get("/api/v1/desires/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unconfigured"
    assert payload["source_path"] is None
    assert payload["fixed_desires"]


def test_api_helpers_handle_edge_cases() -> None:
    from ego_dashboard.api import (
        _calculate_memory_decay,
        _clamp_float,
        _coerce_int,
        _load_link_metadata,
        _memory_label,
        _parse_iso_timestamp,
    )

    assert _clamp_float(True) == 1.0
    assert _clamp_float("2.5") == 1.0
    assert _clamp_float("bad", default=0.25) == 0.25
    assert _coerce_int(True) == 1
    assert _coerce_int(3.9) == 3
    assert _coerce_int("bad", default=7) == 7
    assert _memory_label("alpha beta", {"is_private": True}) == "REDACTED"
    assert _memory_label("alpha beta", {}) == "alpha beta"
    assert _memory_label(123, {}) is None
    assert _memory_label("alpha beta gamma", {}, limit=8) == "alpha..."

    parsed = _parse_iso_timestamp("2026-01-01T12:00:00")
    assert parsed is not None
    assert parsed.tzinfo == UTC
    assert parsed.isoformat() == "2026-01-01T12:00:00+00:00"
    assert _parse_iso_timestamp("") is None
    assert _parse_iso_timestamp("bad") is None

    now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    assert _calculate_memory_decay("bad", now=now) == 1.0
    assert _calculate_memory_decay("2026-01-11T12:00:00Z", now=now) == 1.0
    decay = _calculate_memory_decay(
        "2026-01-01T12:00:00Z",
        link_confidence_max=1.2,
        access_count=20,
        now=now,
    )
    assert 0.0 <= decay <= 1.0

    assert _load_link_metadata("bad-json") == []
    assert _load_link_metadata(
        json.dumps(
            [
                {"target_id": "mem_1", "confidence": "bad"},
                {"target_id": "", "link_type": "related"},
                "skip",
            ]
        )
    ) == [{"target_id": "mem_1", "link_type": "related", "confidence": 0.5}]


def test_load_memory_network_returns_empty_without_data_dir() -> None:
    assert _load_memory_network(DashboardSettings()) == {"nodes": [], "edges": []}


def test_load_notion_rows_handles_missing_invalid_and_valid_files(tmp_path: Path) -> None:
    from ego_dashboard.api import _load_notion_rows

    assert _load_notion_rows(DashboardSettings()) == []
    assert _load_notion_rows(DashboardSettings(ego_mcp_data_dir=str(tmp_path))) == []

    notion_file = tmp_path / "notions.json"
    notion_file.write_text("{broken", encoding="utf-8")
    assert _load_notion_rows(DashboardSettings(ego_mcp_data_dir=str(tmp_path))) == []

    notion_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert _load_notion_rows(DashboardSettings(ego_mcp_data_dir=str(tmp_path))) == []

    notion_file.write_text(
        json.dumps(
            {
                "notion_a": {
                    "label": "A",
                    "emotion_tone": "curious",
                    "confidence": 0.6,
                    "source_memory_ids": ["mem_1"],
                    "related_notion_ids": ["notion_b"],
                    "reinforcement_count": 2,
                    "person_id": "Alice",
                    "created": "2026-01-02T12:00:00+00:00",
                    "last_reinforced": "2026-01-03T12:00:00+00:00",
                },
                "notion_b": {
                    "label": "B",
                    "emotion_tone": "calm",
                    "confidence": 0.9,
                    "source_memory_ids": ["mem_2"],
                    "related_notion_ids": [],
                    "reinforcement_count": 5,
                    "person_id": "Bob",
                    "created": "2026-01-01T12:00:00+00:00",
                    "last_reinforced": "2026-01-02T12:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    rows = _load_notion_rows(DashboardSettings(ego_mcp_data_dir=str(tmp_path)))

    assert [row["id"] for row in rows] == ["notion_a", "notion_b"]
    assert rows[0]["source_count"] == 1
    assert rows[0]["related_count"] == 1
    assert rows[0]["person_id"] == "Alice"
    assert rows[1]["is_conviction"] is True


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
                    "related_notion_ids": ["notion_2"],
                    "reinforcement_count": 5,
                    "person_id": "Master",
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
                },
                {
                    "source": "notion_1",
                    "target": "notion_2",
                    "link_type": "notion_related",
                    "confidence": 0.7,
                },
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
    assert network.json()["edges"][1]["link_type"] == "notion_related"

    notions = client.get("/api/v1/notions")
    assert notions.status_code == 200
    item = notions.json()["items"][0]
    assert item["label"] == "rain & outing (frustrated)"
    assert item["emotion_tone"] == "frustrated"
    assert item["confidence"] == 0.7
    assert item["source_count"] == 2
    assert item["related_notion_ids"] == ["notion_2"]
    assert item["related_count"] == 1
    assert item["reinforcement_count"] == 5
    assert item["person_id"] == "Master"
    assert item["is_conviction"] is True
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
                    "related_notion_ids": ["notion_2"],
                    "reinforcement_count": 6,
                    "person_id": "Master",
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
            "reinforcement_count": 6,
            "person_id": "Master",
            "related_count": 1,
            "is_conviction": True,
        }
    ]
    assert result["edges"] == [
        {
            "source": "notion_1",
            "target": "mem_1",
            "link_type": "notion_source",
            "confidence": 0.8,
        },
        {
            "source": "notion_1",
            "target": "notion_2",
            "link_type": "notion_related",
            "confidence": 0.8,
        },
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


def test_ws_current_stream_sends_snapshot_deduped_logs_and_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _WsStore:
        def tool_usage(
            self, start: datetime, end: datetime, bucket: str
        ) -> list[dict[str, object]]:
            del start, end, bucket
            return []

        def metric_history(
            self, key: str, start: datetime, end: datetime, bucket: str
        ) -> list[dict[str, object]]:
            del key, start, end, bucket
            return []

        def string_timeline(self, key: str, start: datetime, end: datetime) -> list[dict[str, str]]:
            del key, start, end
            return []

        def string_heatmap(
            self, key: str, start: datetime, end: datetime, bucket: str
        ) -> list[dict[str, object]]:
            del key, start, end, bucket
            return []

        def anomaly_alerts(
            self, start: datetime, end: datetime, bucket: str
        ) -> list[dict[str, object]]:
            del start, end, bucket
            return []

        def current(self) -> dict[str, object]:
            return {
                "latest": {"tool_name": "feel_desires"},
                "latest_desires": {"social_thirst": 0.4},
                "latest_emergent_desires": {},
            }

        def logs(
            self,
            start: datetime,
            end: datetime,
            level: str | None = None,
            *,
            search: str | None = None,
        ) -> list[dict[str, object]]:
            del start, end, level, search
            return [
                {
                    "ts": "2026-01-01T12:00:00+00:00",
                    "level": "INFO",
                    "logger": "ego_mcp.server",
                    "message": "Tool invocation",
                    "fields": {"tool_name": "remember"},
                },
                {
                    "ts": "2026-01-01T12:00:00+00:00",
                    "level": "INFO",
                    "logger": "ego_mcp.server",
                    "message": "Tool invocation",
                    "fields": {"tool_name": "remember"},
                },
                {
                    "ts": "2026-01-01T12:00:01+00:00",
                    "level": "ERROR",
                    "logger": "ego_mcp.server",
                    "message": "Tool execution failed",
                    "fields": {},
                },
            ]

        def notion_history(
            self, notion_id: str, start: datetime, end: datetime, bucket: str
        ) -> list[dict[str, object]]:
            del notion_id, start, end, bucket
            return []

        def desire_metric_keys(self, start: datetime, end: datetime) -> list[str]:
            del start, end
            return []

    async def fake_sleep(_seconds: float) -> None:
        raise RuntimeError("stop websocket loop")

    monkeypatch.setattr("ego_dashboard.api.asyncio.sleep", fake_sleep)

    app = create_app(_WsStore())
    client = TestClient(app)

    with client.websocket_connect("/ws/current") as websocket:
        snapshot = websocket.receive_json()
        first_log = websocket.receive_json()
        second_log = websocket.receive_json()
        ping = websocket.receive_json()

        assert snapshot["type"] == "current_snapshot"
        assert snapshot["data"]["latest_desires"] == {"social_thirst": 0.4}

        assert first_log["type"] == "log_line"
        assert first_log["data"]["tool_name"] == "remember"
        assert first_log["data"]["ok"] is True

        assert second_log["type"] == "log_line"
        assert second_log["data"]["message"] == "Tool execution failed"
        assert second_log["data"]["ok"] is False

        assert ping == {"type": "ping"}
