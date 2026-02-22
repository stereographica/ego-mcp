from __future__ import annotations

import glob
import json
import logging
import os
import time
from collections.abc import Mapping
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
    if not isinstance(raw_ts, str):
        raw_ts = raw.get("timestamp")
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
    raw_ts = raw.get("ts")
    if not isinstance(raw_ts, str):
        raw_ts = raw.get("timestamp")
    reserved = {"ts", "timestamp", "level", "logger", "message", "private"}
    fields = {key: value for key, value in raw.items() if key not in reserved}
    return LogEvent(
        ts=_parse_ts(raw_ts if isinstance(raw_ts, str) else None),
        level=str(raw.get("level", "INFO")).upper(),
        logger=str(raw.get("logger", "ego_dashboard")),
        message=message,
        private=private,
        fields=fields,
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


class EgoMcpLogProjector:
    """Project ego-mcp structured logs into dashboard telemetry events."""

    def project(self, raw: Mapping[str, object]) -> DashboardEvent | None:
        message = raw.get("message")
        tool_name = raw.get("tool_name")
        if not isinstance(message, str) or not isinstance(tool_name, str):
            return None

        if message == "Tool invocation":
            tool_args = raw.get("tool_args")
            safe_tool_args = tool_args if isinstance(tool_args, dict) else {}
            event_raw = self._build_event_raw(
                raw,
                tool_name,
                safe_tool_args,
                True,
                "tool_call_invoked",
            )
            return normalize_event(event_raw)

        if message not in {"Tool execution completed", "Tool execution failed"}:
            return None
        return None

    def _build_event_raw(
        self,
        raw: Mapping[str, object],
        tool_name: str,
        tool_args: dict[str, object],
        ok: bool,
        event_type: str,
    ) -> dict[str, object]:
        params: dict[str, object] = {}

        if isinstance(tool_args.get("emotion"), str):
            params["emotion_primary"] = tool_args["emotion"]
        for key in ("intensity", "valence", "arousal"):
            value = tool_args.get(key)
            if isinstance(value, (int, float)):
                params[key] = value

        body_state = tool_args.get("body_state")
        if isinstance(body_state, dict):
            time_phase = body_state.get("time_phase")
            if isinstance(time_phase, str):
                params["time_phase"] = time_phase
            mode = body_state.get("mode")
            if isinstance(mode, str):
                params["mode"] = mode
            state = body_state.get("state")
            if isinstance(state, str):
                params["state"] = state

        raw_ts = raw.get("ts")
        if not isinstance(raw_ts, str):
            raw_ts = raw.get("timestamp")

        event_raw: dict[str, object] = {
            "ts": raw_ts,
            "event_type": event_type,
            "tool_name": tool_name,
            "ok": ok,
            "params": params,
            "private": bool(tool_args.get("private", False)),
            "message": str(raw.get("message", "")),
        }
        if isinstance(tool_args.get("emotion"), str):
            event_raw["emotion_primary"] = tool_args["emotion"]
        if isinstance(tool_args.get("intensity"), (int, float)):
            event_raw["emotion_intensity"] = tool_args["intensity"]
        return event_raw


def _default_store() -> IngestStoreProtocol:
    settings = load_settings()
    if settings.use_external_store and settings.database_url and settings.redis_url:
        store = SqlTelemetryStore(settings.database_url, settings.redis_url)
        store.initialize()
        return store
    return TelemetryStore()


def ingest_jsonl_line(
    line: str,
    store: IngestStoreProtocol,
    projector: EgoMcpLogProjector | None = None,
) -> None:
    text = line.strip()
    if not text:
        return
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        LOGGER.warning("failed to parse jsonl line: %s", exc)
        return
    if not isinstance(payload, dict):
        return

    try:
        if payload.get("event_type"):
            event: DashboardEvent | None = normalize_event(payload)
            log = None
        else:
            log = normalize_log(payload)
            event = projector.project(payload) if projector is not None else None
    except (TypeError, ValueError) as exc:
        LOGGER.warning("failed to normalize jsonl line: %s", exc)
        return

    if event is not None:
        store.ingest(event)
    if log is not None:
        store.ingest_log(log)


def _select_source_file(path_or_glob: str) -> str | None:
    resolved = _resolve_source_files(path_or_glob)
    if not resolved:
        return None
    return max(resolved, key=lambda path: (os.path.getmtime(path), path))


def _resolve_source_files(path_or_glob: str) -> list[str]:
    if glob.has_magic(path_or_glob):
        return sorted(path for path in glob.glob(path_or_glob) if os.path.isfile(path))
    return [path_or_glob] if os.path.isfile(path_or_glob) else []


def tail_jsonl_file(path: str, store: IngestStoreProtocol, poll_seconds: float = 1.0) -> None:
    """Tail a file path or all files matching a glob pattern."""
    inodes: dict[str, int] = {}
    positions: dict[str, int] = {}
    projectors: dict[str, EgoMcpLogProjector] = {}

    while True:
        selected_paths = _resolve_source_files(path)
        if not selected_paths:
            if inodes:
                LOGGER.info("source file(s) disappeared, waiting for recreation: %s", path)
            inodes.clear()
            positions.clear()
            projectors.clear()
            time.sleep(poll_seconds)
            continue

        active_set = set(selected_paths)
        for stale_path in list(positions):
            if stale_path not in active_set:
                positions.pop(stale_path, None)
                inodes.pop(stale_path, None)
                projectors.pop(stale_path, None)

        for selected_path in selected_paths:
            stat = os.stat(selected_path)
            current_inode = inodes.get(selected_path)
            position = positions.get(selected_path, 0)
            projector = projectors.setdefault(selected_path, EgoMcpLogProjector())

            if current_inode != stat.st_ino or stat.st_size < position:
                inodes[selected_path] = stat.st_ino
                position = 0
                positions[selected_path] = 0
                projectors[selected_path] = EgoMcpLogProjector()
                projector = projectors[selected_path]
                LOGGER.info("opened source file: %s", selected_path)

            with open(selected_path, encoding="utf-8") as handle:
                handle.seek(position)
                while True:
                    line = handle.readline()
                    if line == "":
                        break
                    ingest_jsonl_line(line, store, projector=projector)
                positions[selected_path] = handle.tell()
                inodes[selected_path] = stat.st_ino

        time.sleep(poll_seconds)


def run_ingestor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    LOGGER.info(
        "starting ingestor source=%s poll=%.2fs",
        settings.log_path,
        settings.ingest_poll_seconds,
    )
    store = _default_store()
    tail_jsonl_file(settings.log_path, store, poll_seconds=settings.ingest_poll_seconds)


def main() -> None:
    run_ingestor()


if __name__ == "__main__":
    main()
