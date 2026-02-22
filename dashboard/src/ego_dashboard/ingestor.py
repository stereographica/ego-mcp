from __future__ import annotations

from datetime import UTC, datetime

from ego_dashboard.models import DashboardEvent

ALLOWED_STRING_PARAMS = {"time_phase", "emotion_primary", "mode", "state"}


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
