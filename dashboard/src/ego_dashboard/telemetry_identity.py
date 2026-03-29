from __future__ import annotations

import hashlib
import json

from ego_dashboard.models import DashboardEvent, LogEvent


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def dashboard_event_dedupe_key(event: DashboardEvent) -> str:
    payload = {
        "event_type": event.event_type,
        "tool_name": event.tool_name,
        "ok": event.ok,
        "duration_ms": event.duration_ms,
        "emotion_primary": event.emotion_primary,
        "emotion_intensity": event.emotion_intensity,
        "numeric_metrics": event.numeric_metrics,
        "string_metrics": event.string_metrics,
        "params": event.params,
        "private": event.private,
        "message": event.message,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def log_event_dedupe_key(event: LogEvent) -> str:
    payload = {
        "level": event.level.upper(),
        "logger": event.logger,
        "message": event.message,
        "private": event.private,
        "fields": event.fields,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
