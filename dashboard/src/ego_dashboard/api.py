from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

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
        self, start: datetime, end: datetime, level: str | None = None, logger: str | None = None
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
    app = FastAPI(title="ego-mcp dashboard api")
    if app_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
        logger: str | None = None,
    ) -> dict[str, object]:
        return {"items": telemetry.logs(from_ts, to_ts, level, logger)}

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
                logs = telemetry.logs(start, end, None, None)
                if logs:
                    await websocket.send_json({"type": "log_line", "data": logs[-1]})
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(2)
        except Exception:
            await websocket.close()

    return app
