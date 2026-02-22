from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardSettings:
    database_url: str | None = None
    redis_url: str | None = None
    log_path: str = "/tmp/ego-mcp/telemetry.jsonl"
    ingest_poll_seconds: float = 1.0

    @property
    def use_external_store(self) -> bool:
        return bool(self.database_url and self.redis_url)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


def load_settings() -> DashboardSettings:
    return DashboardSettings(
        database_url=os.getenv("DASHBOARD_DATABASE_URL"),
        redis_url=os.getenv("DASHBOARD_REDIS_URL"),
        log_path=os.getenv("DASHBOARD_LOG_PATH", "/tmp/ego-mcp/telemetry.jsonl"),
        ingest_poll_seconds=_env_float("DASHBOARD_INGEST_POLL_SECONDS", 1.0),
    )
