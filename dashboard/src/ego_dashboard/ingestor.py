from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Protocol

from ego_dashboard.models import DashboardEvent, LogEvent
from ego_dashboard.settings import load_settings
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.store import TelemetryStore

ALLOWED_STRING_PARAMS = {"time_phase", "emotion_primary", "mode", "state"}
LOGGER = logging.getLogger(__name__)


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def normalize_event(raw: dict[str, object]) -> DashboardEvent:
    params = raw.get("params", {})
    safe_params: dict[str, str | int | float | bool] = {}
    numeric_metrics: dict[str, float] = {}
    string_metrics: dict[str, str] = {}

    if isinstance(params, dict):
        for key, value in params.items():
            if isinstance(value, (int, float)):
                numeric_metrics[key] = float(value)
                safe_params[key] = value
            elif isinstance(value, str) and key in ALLOWED_STRING_PARAMS:
                string_metrics[key] = value
                safe_params[key] = value

    raw_intensity = raw.get("emotion_intensity")
    emotion_intensity = float(raw_intensity) if isinstance(raw_intensity, (int, float)) else None
    if emotion_intensity is not None:
        numeric_metrics["intensity"] = emotion_intensity

    private = bool(raw.get("private", False))
    message = raw.get("message")
    raw_ts = raw.get("ts")
    duration = raw.get("duration_ms")
    event = DashboardEvent(
        ts=_parse_ts(raw_ts if isinstance(raw_ts, str) else None),
        event_type=str(raw.get("event_type", "tool_call_completed")),
        tool_name=str(raw.get("tool_name", "unknown")),
        ok=bool(raw.get("ok", True)),
        duration_ms=duration if isinstance(duration, int) else None,
        emotion_primary=(
            str(raw["emotion_primary"]) if isinstance(raw.get("emotion_primary"), str) else None
        ),
        emotion_intensity=emotion_intensity,
        numeric_metrics=numeric_metrics,
        string_metrics=string_metrics,
        params=safe_params,
        private=private,
        message="REDACTED" if private else (str(message) if isinstance(message, str) else None),
    )
    if private:
        event.params = {k: v for k, v in event.params.items() if k in ALLOWED_STRING_PARAMS}
    return event


def normalize_log(raw: dict[str, object]) -> LogEvent:
    private = bool(raw.get("private", False))
    message = str(raw.get("message", ""))
    if private:
        message = "REDACTED"
    return LogEvent(
        ts=_parse_ts(str(raw["ts"]) if isinstance(raw.get("ts"), str) else None),
        level=str(raw.get("level", "INFO")).upper(),
        logger=str(raw.get("logger", "ego_dashboard")),
        message=message,
        private=private,
    )


def parse_jsonl_line(line: str) -> tuple[DashboardEvent | None, LogEvent | None]:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        return None, None
    if payload.get("event_type"):
        return normalize_event(payload), None
    return None, normalize_log(payload)


class IngestStoreProtocol(Protocol):
    def ingest(self, event: DashboardEvent) -> None: ...

    def ingest_log(self, event: LogEvent) -> None: ...


def _default_store() -> IngestStoreProtocol:
    settings = load_settings()
    if settings.use_external_store and settings.database_url and settings.redis_url:
        store = SqlTelemetryStore(settings.database_url, settings.redis_url)
        store.initialize()
        return store
    return TelemetryStore()


def ingest_jsonl_line(line: str, store: IngestStoreProtocol) -> None:
    text = line.strip()
    if not text:
        return
    try:
        event, log = parse_jsonl_line(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        LOGGER.warning("failed to parse jsonl line: %s", exc)
        return
    if event is not None:
        store.ingest(event)
    if log is not None:
        store.ingest_log(log)


def tail_jsonl_file(path: str, store: IngestStoreProtocol, poll_seconds: float = 1.0) -> None:
    current_inode: int | None = None
    position = 0

    while True:
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            if current_inode is not None:
                LOGGER.info("source file disappeared, waiting for recreation: %s", path)
            current_inode = None
            position = 0
            time.sleep(poll_seconds)
            continue

        if current_inode != stat.st_ino or stat.st_size < position:
            current_inode = stat.st_ino
            position = 0
            LOGGER.info("opened source file: %s", path)

        with open(path, encoding="utf-8") as handle:
            handle.seek(position)
            while True:
                line = handle.readline()
                if line == "":
                    break
                ingest_jsonl_line(line, store)
            position = handle.tell()

        time.sleep(poll_seconds)


def run_ingestor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    LOGGER.info(
        "starting ingestor path=%s poll=%.2fs",
        settings.log_path,
        settings.ingest_poll_seconds,
    )
    store = _default_store()
    tail_jsonl_file(settings.log_path, store, poll_seconds=settings.ingest_poll_seconds)


def main() -> None:
    run_ingestor()


if __name__ == "__main__":
    main()
