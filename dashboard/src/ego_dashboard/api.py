from __future__ import annotations

import asyncio
import importlib
import json
import sys
import threading
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ego_dashboard.ingestor import tail_jsonl_file
from ego_dashboard.settings import DashboardSettings, load_settings
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.store import TelemetryStore

_MEMORY_NETWORK_BATCH_SIZE = 512


class StoreProtocol(Protocol):
    def tool_usage(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def metric_history(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def string_timeline(self, key: str, start: datetime, end: datetime) -> list[dict[str, str]]: ...

    def string_heatmap(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def logs(
        self,
        start: datetime,
        end: datetime,
        level: str | None = None,
        *,
        search: str | None = None,
    ) -> list[dict[str, object]]: ...

    def anomaly_alerts(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def current(self) -> dict[str, object]: ...

    def notion_history(
        self, notion_id: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_ego_mcp_importable() -> None:
    ego_src = _repo_root() / "ego-mcp" / "src"
    ego_src_str = str(ego_src)
    if ego_src.exists() and ego_src_str not in sys.path:
        sys.path.insert(0, ego_src_str)


def _load_notion_rows(settings: DashboardSettings) -> list[dict[str, object]]:
    if not settings.ego_mcp_data_dir:
        return []
    notion_path = Path(settings.ego_mcp_data_dir) / "notions.json"
    if not notion_path.exists():
        return []
    try:
        payload = json.loads(notion_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, object]] = []
    for notion_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        source_ids = raw.get("source_memory_ids", [])
        rows.append(
            {
                "id": str(notion_id),
                "label": str(raw.get("label", "")),
                "emotion_tone": str(raw.get("emotion_tone", "neutral")),
                "confidence": float(raw.get("confidence", 0.5)),
                "source_count": len(source_ids) if isinstance(source_ids, list) else 0,
                "source_memory_ids": list(source_ids) if isinstance(source_ids, list) else [],
                "created": str(raw.get("created", "")),
                "last_reinforced": str(raw.get("last_reinforced", "")),
            }
        )
    rows.sort(key=lambda row: str(row.get("created", "")), reverse=True)
    return rows


def _load_memory_network(settings: DashboardSettings) -> dict[str, object]:
    if not settings.ego_mcp_data_dir:
        return {"nodes": [], "edges": []}
    try:
        _ensure_ego_mcp_importable()
        memory_scoring = cast(Any, importlib.import_module("ego_mcp._memory_scoring"))
        memory_serialization = cast(Any, importlib.import_module("ego_mcp._memory_serialization"))
        chromadb_compat = cast(Any, importlib.import_module("ego_mcp.chromadb_compat"))
        calculate_time_decay = cast(Callable[..., float], memory_scoring.calculate_time_decay)
        memory_from_chromadb = cast(
            Callable[[str, str, dict[str, object]], Any],
            memory_serialization.memory_from_chromadb,
        )
        load_chromadb = cast(Callable[[], Any], chromadb_compat.load_chromadb)
    except Exception:
        return {"nodes": [], "edges": []}

    chroma_dir = Path(settings.ego_mcp_data_dir) / "chroma"
    if not chroma_dir.exists():
        return {"nodes": [], "edges": []}
    try:
        chromadb = load_chromadb()
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name="ego_memories")
    except Exception:
        return {"nodes": [], "edges": []}

    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    offset = 0
    while True:
        try:
            rows = collection.get(
                limit=_MEMORY_NETWORK_BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas"],
            )
        except Exception:
            return {"nodes": [], "edges": []}

        ids = rows.get("ids", [])
        documents = rows.get("documents", [])
        metadatas = rows.get("metadatas", [])
        if not isinstance(ids, list) or not ids:
            break

        for memory_id, document, metadata in zip(ids, documents, metadatas):
            if (
                not isinstance(memory_id, str)
                or not isinstance(document, str)
                or not isinstance(metadata, dict)
            ):
                continue
            memory = memory_from_chromadb(memory_id, document, metadata)
            max_confidence = max((link.confidence for link in memory.linked_ids), default=0.0)
            nodes.append(
                {
                    "id": memory.id,
                    "category": memory.category.value,
                    "decay": calculate_time_decay(
                        memory.timestamp,
                        link_confidence_max=max_confidence,
                        access_count=memory.access_count,
                    ),
                    "access_count": memory.access_count,
                    "is_notion": False,
                }
            )
            for link in memory.linked_ids:
                if memory.id <= link.target_id:
                    edge_key = (memory.id, link.target_id, link.link_type.value)
                else:
                    edge_key = (link.target_id, memory.id, link.link_type.value)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append(
                    {
                        "source": memory.id,
                        "target": link.target_id,
                        "link_type": link.link_type.value,
                        "confidence": link.confidence,
                    }
                )

        if len(ids) < _MEMORY_NETWORK_BATCH_SIZE:
            break
        offset += len(ids)

    for notion in _load_notion_rows(settings):
        notion_id = str(notion["id"])
        nodes.append(
            {
                "id": notion_id,
                "label": notion["label"],
                "is_notion": True,
                "confidence": notion["confidence"],
                "access_count": notion["source_count"],
                "decay": notion["confidence"],
                "category": "notion",
            }
        )
        source_memory_ids = notion.get("source_memory_ids", [])
        if not isinstance(source_memory_ids, list):
            continue
        for source_memory_id in source_memory_ids:
            if not isinstance(source_memory_id, str):
                continue
            edges.append(
                {
                    "source": notion_id,
                    "target": source_memory_id,
                    "link_type": "notion_source",
                    "confidence": notion["confidence"],
                }
            )
    return {"nodes": nodes, "edges": edges}


def _default_store() -> StoreProtocol:
    settings = load_settings()
    if settings.use_external_store and settings.database_url and settings.redis_url:
        sql_store = SqlTelemetryStore(settings.database_url, settings.redis_url)
        sql_store.initialize()
        return sql_store
    return TelemetryStore()


def create_app(
    store: StoreProtocol | None = None,
    settings: DashboardSettings | None = None,
) -> FastAPI:
    app_settings = settings or load_settings()
    telemetry = store or _default_store()
    use_local_inmemory_ingestor = (
        store is None
        and not app_settings.use_external_store
        and isinstance(telemetry, TelemetryStore)
    )
    local_ingestor_thread: threading.Thread | None = None
    local_ingestor_stop_event: threading.Event | None = None
    app = FastAPI(title="ego-mcp dashboard api")
    if app_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if use_local_inmemory_ingestor:

        @app.on_event("startup")
        async def _start_local_ingestor() -> None:
            nonlocal local_ingestor_thread, local_ingestor_stop_event
            if local_ingestor_thread is not None and local_ingestor_thread.is_alive():
                return
            local_ingestor_stop_event = threading.Event()
            local_ingestor_thread = threading.Thread(
                target=tail_jsonl_file,
                kwargs={
                    "path": app_settings.log_path,
                    "store": telemetry,
                    "poll_seconds": app_settings.ingest_poll_seconds,
                    "stop_event": local_ingestor_stop_event,
                },
                name="ego-dashboard-local-ingestor",
                daemon=True,
            )
            local_ingestor_thread.start()

        @app.on_event("shutdown")
        async def _stop_local_ingestor() -> None:
            nonlocal local_ingestor_thread, local_ingestor_stop_event
            if local_ingestor_stop_event is not None:
                local_ingestor_stop_event.set()
            if local_ingestor_thread is not None and local_ingestor_thread.is_alive():
                local_ingestor_thread.join(timeout=max(1.0, app_settings.ingest_poll_seconds * 2))
            local_ingestor_thread = None
            local_ingestor_stop_event = None

    @app.get("/api/v1/current")
    def get_current() -> dict[str, object]:
        return telemetry.current()

    @app.get("/api/v1/usage/tools")
    def get_tool_usage(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "1m",
    ) -> dict[str, object]:
        return {"items": telemetry.tool_usage(from_ts, to_ts, bucket)}

    @app.get("/api/v1/metrics/{key}")
    def get_metric(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "1m",
    ) -> dict[str, object]:
        return {"items": telemetry.metric_history(key, from_ts, to_ts, bucket)}

    @app.get("/api/v1/metrics/{key}/string-timeline")
    def get_string_timeline(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return {"items": telemetry.string_timeline(key, from_ts, to_ts)}

    @app.get("/api/v1/metrics/{key}/heatmap")
    def get_string_heatmap(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "5m",
    ) -> dict[str, object]:
        return {"items": telemetry.string_heatmap(key, from_ts, to_ts, bucket)}

    @app.get("/api/v1/logs")
    def get_logs(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        level: str | None = None,
        search: str | None = None,
    ) -> dict[str, object]:
        return {"items": telemetry.logs(from_ts, to_ts, level, search=search)}

    @app.get("/api/v1/alerts/anomalies")
    def get_anomalies(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "5m",
    ) -> dict[str, object]:
        return {"items": telemetry.anomaly_alerts(from_ts, to_ts, bucket)}

    @app.get("/api/v1/memory/network")
    def get_memory_network() -> dict[str, object]:
        return _load_memory_network(app_settings)

    @app.get("/api/v1/notions")
    def get_notions() -> dict[str, object]:
        return {"items": _load_notion_rows(app_settings)}

    @app.get("/api/v1/notions/{notion_id}/history")
    def get_notion_history(
        notion_id: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "15m",
    ) -> dict[str, object]:
        return {"items": telemetry.notion_history(notion_id, from_ts, to_ts, bucket)}

    @app.websocket("/ws/current")
    async def ws_current(websocket: WebSocket) -> None:
        await websocket.accept()
        recent_log_keys: deque[str] = deque(maxlen=512)
        recent_log_key_set: set[str] = set()
        try:
            while True:
                await websocket.send_json(
                    {
                        "type": "current_snapshot",
                        "at": datetime.now(tz=UTC).isoformat(),
                        "data": telemetry.current(),
                    }
                )
                end = datetime.now(tz=UTC)
                start = end - timedelta(minutes=5)
                logs = telemetry.logs(start, end)
                for log in logs:
                    log_key = json.dumps(
                        {
                            "ts": log.get("ts"),
                            "level": log.get("level"),
                            "logger": log.get("logger"),
                            "message": log.get("message"),
                            "fields": log.get("fields", {}),
                        },
                        sort_keys=True,
                        default=str,
                    )
                    if log_key in recent_log_key_set:
                        continue
                    payload = dict(log)
                    fields = payload.get("fields")
                    if isinstance(fields, dict) and "tool_name" in fields:
                        payload.setdefault("tool_name", fields["tool_name"])
                    if "ok" not in payload:
                        level = str(payload.get("level", "")).upper()
                        message = str(payload.get("message", ""))
                        payload["ok"] = not (level == "ERROR" or message == "Tool execution failed")
                    await websocket.send_json({"type": "log_line", "data": payload})
                    if len(recent_log_keys) == recent_log_keys.maxlen:
                        evicted = recent_log_keys[0]
                        recent_log_key_set.discard(evicted)
                    recent_log_keys.append(log_key)
                    recent_log_key_set.add(log_key)
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(2)
        except Exception:
            await websocket.close()

    return app
