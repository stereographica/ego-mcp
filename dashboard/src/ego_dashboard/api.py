from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, TypedDict

import chromadb
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ego_dashboard.ingestor import tail_jsonl_file
from ego_dashboard.settings import DashboardSettings, load_settings
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.store import TelemetryStore

_MEMORY_NETWORK_BATCH_SIZE = 512
logger = logging.getLogger(__name__)


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

    def desire_metric_keys(self, start: datetime, end: datetime) -> list[str]: ...


class _MemoryLinkPayload(TypedDict):
    target_id: str
    link_type: str
    confidence: float


def _clamp_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        parsed = float(int(value))
    elif isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            parsed = default
    else:
        parsed = default
    return max(0.0, min(1.0, parsed))


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _memory_label(document: object, metadata: object, *, limit: int = 72) -> str | None:
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    private_raw = metadata_dict.get("is_private") if isinstance(metadata_dict, dict) else False
    if private_raw in (True, 1, "1", "true", "True"):
        return "REDACTED"
    if not isinstance(document, str):
        return None
    compact = " ".join(document.split()).strip()
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _calculate_memory_decay(
    timestamp: object,
    *,
    link_confidence_max: float = 0.0,
    access_count: int = 0,
    now: datetime | None = None,
) -> float:
    memory_time = _parse_iso_timestamp(timestamp)
    if memory_time is None:
        return 1.0

    current = now or datetime.now(tz=UTC)
    age_seconds = (current - memory_time).total_seconds()
    if age_seconds < 0:
        return 1.0

    age_days = age_seconds / 86400
    access_bonus = min(max(access_count, 0) * 5, 60)
    effective_half_life = (30.0 + access_bonus) * (1.0 + _clamp_float(link_confidence_max) * 0.5)
    return max(0.0, min(1.0, 2 ** (-age_days / max(effective_half_life, 1e-6))))


def _load_link_metadata(value: object) -> list[_MemoryLinkPayload]:
    if not isinstance(value, str) or not value:
        return []
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    links: list[_MemoryLinkPayload] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            continue
        link_type = item.get("link_type")
        links.append(
            {
                "target_id": target_id,
                "link_type": link_type if isinstance(link_type, str) and link_type else "related",
                "confidence": _clamp_float(item.get("confidence"), 0.5),
            }
        )
    return links


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
    notion_rows = _load_notion_rows(settings)
    if not settings.ego_mcp_data_dir:
        return {"nodes": [], "edges": []}

    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    chroma_dir = Path(settings.ego_mcp_data_dir) / "chroma"
    if not chroma_dir.exists():
        logger.warning(
            "Memory network skipped because Chroma directory does not exist: %s", chroma_dir
        )
    else:
        try:
            client = chromadb.PersistentClient(path=str(chroma_dir))
            collection = client.get_collection(name="ego_memories")
            offset = 0
            while True:
                rows = collection.get(
                    limit=_MEMORY_NETWORK_BATCH_SIZE,
                    offset=offset,
                    include=["documents", "metadatas"],
                )

                ids = rows.get("ids", [])
                documents = rows.get("documents", [])
                metadatas = rows.get("metadatas", [])
                if not isinstance(ids, list) or not ids:
                    break
                document_rows = documents if isinstance(documents, list) else []
                metadata_rows = metadatas if isinstance(metadatas, list) else []

                for index, memory_id in enumerate(ids):
                    if not isinstance(memory_id, str):
                        continue
                    document = document_rows[index] if index < len(document_rows) else None
                    metadata = metadata_rows[index] if index < len(metadata_rows) else {}
                    if not isinstance(metadata, dict):
                        continue
                    linked_ids = _load_link_metadata(metadata.get("linked_ids"))
                    max_confidence = max(
                        (link["confidence"] for link in linked_ids),
                        default=0.0,
                    )
                    access_count = _coerce_int(metadata.get("access_count"), 0)
                    category = metadata.get("category")
                    nodes.append(
                        {
                            "id": memory_id,
                            "label": _memory_label(document, metadata),
                            "category": (
                                str(category) if isinstance(category, str) and category else "daily"
                            ),
                            "decay": _calculate_memory_decay(
                                metadata.get("timestamp"),
                                link_confidence_max=max_confidence,
                                access_count=access_count,
                            ),
                            "access_count": access_count,
                            "is_notion": False,
                        }
                    )
                    for link in linked_ids:
                        target_id = str(link["target_id"])
                        link_type = str(link["link_type"])
                        if memory_id <= target_id:
                            edge_key = (memory_id, target_id, link_type)
                        else:
                            edge_key = (target_id, memory_id, link_type)
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)
                        edges.append(
                            {
                                "source": memory_id,
                                "target": target_id,
                                "link_type": link_type,
                                "confidence": link["confidence"],
                            }
                        )

                if len(ids) < _MEMORY_NETWORK_BATCH_SIZE:
                    break
                offset += len(ids)
        except Exception:
            logger.exception("Failed to load memory nodes for Memory Network from %s", chroma_dir)

    for notion in notion_rows:
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

    @app.get("/api/v1/desires/keys")
    def get_desire_metric_keys(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return {"items": telemetry.desire_metric_keys(from_ts, to_ts)}

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
