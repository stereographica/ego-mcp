from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ego_dashboard.ingestor import tail_jsonl_file
from ego_dashboard.settings import DashboardSettings, load_settings
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.store import TelemetryStore


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
