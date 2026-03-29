from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.models import DashboardEvent, LogEvent
from ego_dashboard.telemetry_identity import dashboard_event_dedupe_key, log_event_dedupe_key

_BUCKETS = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "15m": timedelta(minutes=15)}


class TelemetryStore:
    def __init__(self) -> None:
        self._events: list[DashboardEvent] = []
        self._logs: list[LogEvent] = []
        self._event_keys: set[tuple[datetime, str]] = set()
        self._log_keys: set[tuple[datetime, str]] = set()
        self._checkpoints: dict[str, tuple[int, int]] = {}

    def ingest(self, event: DashboardEvent) -> None:
        key = (event.ts, dashboard_event_dedupe_key(event))
        if key in self._event_keys:
            return
        self._event_keys.add(key)
        self._events.append(event)
        self._events.sort(key=lambda item: item.ts)

    def ingest_log(self, event: LogEvent) -> None:
        key = (event.ts, log_event_dedupe_key(event))
        if key in self._log_keys:
            return
        self._log_keys.add(key)
        self._logs.append(event)
        self._logs.sort(key=lambda item: item.ts)

    def load_checkpoint(self, path: str) -> tuple[int, int] | None:
        return self._checkpoints.get(path)

    def save_checkpoint(self, path: str, inode: int, offset: int) -> None:
        self._checkpoints[path] = (inode, offset)

    def _bucket_delta(self, bucket: str) -> timedelta:
        return _BUCKETS.get(bucket, timedelta(minutes=1))

    def _filtered(self, start: datetime, end: datetime) -> list[DashboardEvent]:
        return [item for item in self._events if start <= item.ts <= end]

    def _terminal_events(self, start: datetime, end: datetime) -> list[DashboardEvent]:
        return [
            item
            for item in self._events
            if start <= item.ts <= end
            and item.event_type in {"tool_call_completed", "tool_call_failed"}
        ]

    @staticmethod
    def _invocation_tool_name(log: LogEvent) -> str | None:
        raw = log.fields.get("tool_name")
        return raw if isinstance(raw, str) and raw else None

    def _latest_numeric_metrics(self, keys: tuple[str, ...]) -> dict[str, float]:
        if not self._events:
            return {}
        wanted = set(keys)
        latest: dict[str, float] = {}
        for event in reversed(self._events):
            for key, value in event.numeric_metrics.items():
                if key not in wanted or key in latest:
                    continue
                latest[key] = float(value)
            if len(latest) == len(wanted):
                break
        return latest

    def _latest_desire_metrics(self) -> dict[str, float]:
        excluded = {
            "intensity",
            "valence",
            "arousal",
            "impulse_boost_amount",
        }
        source = next(
            (event for event in reversed(self._events) if event.tool_name == "feel_desires"),
            None,
        )
        if source is None:
            return {}
        desire_metrics: dict[str, float] = {}
        for key, value in source.numeric_metrics.items():
            if key in excluded:
                continue
            if key in DESIRE_METRIC_KEYS or "want" in key.lower():
                desire_metrics[key] = float(value)
        return desire_metrics

    def _bucket_events(
        self, events: list[DashboardEvent], start: datetime, end: datetime, bucket: str
    ) -> list[tuple[datetime, list[DashboardEvent]]]:
        delta = self._bucket_delta(bucket)
        rows: list[tuple[datetime, list[DashboardEvent]]] = []
        cursor = start
        while cursor < end:
            bucket_end = cursor + delta
            grouped = [ev for ev in events if cursor <= ev.ts < bucket_end]
            rows.append((cursor, grouped))
            cursor = bucket_end
        return rows

    def tool_usage(self, start: datetime, end: datetime, bucket: str) -> list[dict[str, object]]:
        invocations = [
            log
            for log in self._logs
            if start <= log.ts <= end
            and log.message == "Tool invocation"
            and self._invocation_tool_name(log) is not None
        ]
        if invocations:
            tool_names = sorted(
                {
                    tool_name
                    for log in invocations
                    if (tool_name := self._invocation_tool_name(log)) is not None
                }
            )
            log_usage_rows: list[dict[str, object]] = []
            delta = self._bucket_delta(bucket)
            cursor = start
            while cursor < end:
                bucket_end = cursor + delta
                log_counts: Counter[str] = Counter(
                    tool_name
                    for log in invocations
                    if cursor <= log.ts < bucket_end
                    if (tool_name := self._invocation_tool_name(log)) is not None
                )
                row: dict[str, object] = {"ts": cursor.isoformat()}
                for tool_name in tool_names:
                    row[tool_name] = int(log_counts.get(tool_name, 0))
                log_usage_rows.append(row)
                cursor = bucket_end
            return log_usage_rows

        events = self._terminal_events(start, end)
        tool_names = sorted({ev.tool_name for ev in events})
        event_usage_rows: list[dict[str, object]] = []
        for at, grouped in self._bucket_events(events, start, end, bucket):
            event_counts: dict[str, int] = Counter(ev.tool_name for ev in grouped)
            row = {"ts": at.isoformat()}
            for tool_name in tool_names:
                row[tool_name] = int(event_counts.get(tool_name, 0))
            event_usage_rows.append(row)
        return event_usage_rows

    def metric_history(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        events = self._filtered(start, end)
        rows: list[dict[str, object]] = []
        for at, grouped in self._bucket_events(events, start, end, bucket):
            values = [ev.numeric_metrics[key] for ev in grouped if key in ev.numeric_metrics]
            if values:
                rows.append({"ts": at.isoformat(), "value": sum(values) / len(values)})
        return rows

    def string_timeline(self, key: str, start: datetime, end: datetime) -> list[dict[str, str]]:
        events = self._filtered(start, end)
        points = [
            {"ts": ev.ts.isoformat(), "value": ev.string_metrics[key]}
            for ev in events
            if key in ev.string_metrics
        ]
        return points

    def string_heatmap(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        events = self._filtered(start, end)
        rows: list[dict[str, object]] = []
        for at, grouped in self._bucket_events(events, start, end, bucket):
            counter: Counter[str] = Counter(
                ev.string_metrics[key] for ev in grouped if key in ev.string_metrics
            )
            rows.append({"ts": at.isoformat(), "counts": dict(counter)})
        return rows

    def logs(
        self,
        start: datetime,
        end: datetime,
        level: str | None = None,
        *,
        search: str | None = None,
    ) -> list[dict[str, object]]:
        values = [log for log in self._logs if start <= log.ts <= end]
        if level:
            values = [log for log in values if log.level == level.upper()]
        if search:
            needle = search.lower()
            values = [
                log
                for log in values
                if needle in log.message.lower()
                or any(needle in value.lower() for value in self._field_values(log.fields))
            ]
        rows: list[dict[str, object]] = []
        for item in values[-300:]:
            row = item.model_dump(mode="json")
            if item.private:
                row["message"] = "REDACTED"
            rows.append(row)
        return rows

    @classmethod
    def _field_values(cls, value: object) -> Iterable[str]:
        if isinstance(value, str):
            yield value
            return
        if isinstance(value, dict):
            for nested in value.values():
                yield from cls._field_values(nested)
            return
        if isinstance(value, list):
            for nested in value:
                yield from cls._field_values(nested)
            return
        if value is not None:
            yield str(value)

    def anomaly_alerts(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        usage = self.tool_usage(start, end, bucket)
        intensity = self.metric_history("intensity", start, end, bucket)

        alerts: list[dict[str, object]] = []
        prev_total: int | None = None
        for row in usage:
            total = sum(
                value for key, value in row.items() if key != "ts" and isinstance(value, int)
            )
            if prev_total is not None and prev_total > 0 and total >= prev_total * 2:
                alerts.append({"kind": "usage_spike", "ts": row["ts"], "value": total})
            prev_total = total

        prev_intensity: float | None = None
        for row in intensity:
            raw_value = row.get("value")
            if not isinstance(raw_value, (int, float)):
                continue
            value = float(raw_value)
            if prev_intensity is not None and value - prev_intensity >= 0.4:
                alerts.append({"kind": "intensity_spike", "ts": row["ts"], "value": value})
            prev_intensity = value

        return alerts

    def desire_metric_keys(self, start: datetime, end: datetime) -> list[str]:
        keys: set[str] = set()
        for event in self._filtered(start, end):
            if event.tool_name != "feel_desires":
                continue
            for key in event.numeric_metrics:
                if key in DESIRE_METRIC_KEYS or "want" in key.lower():
                    keys.add(key)
        return sorted(keys)

    def current(self) -> dict[str, object]:
        if not self._events:
            return {
                "latest": None,
                "latest_emotion": None,
                "latest_relationship": None,
                "tool_calls_per_min": 0,
                "error_rate": 0.0,
                "window_24h": {"tool_calls": 0, "error_rate": 0.0},
                "latest_desires": {},
                "latest_emergent_desires": {},
            }

        latest = self._events[-1]
        window_start = latest.ts - timedelta(minutes=1)
        window_24h_start = latest.ts - timedelta(hours=24)
        recent = [ev for ev in self._events if ev.ts >= window_start]
        recent_24h = [ev for ev in self._events if ev.ts >= window_24h_start]
        terminal_recent = [
            ev for ev in recent if ev.event_type in {"tool_call_completed", "tool_call_failed"}
        ]
        terminal_recent_24h = [
            ev for ev in recent_24h if ev.event_type in {"tool_call_completed", "tool_call_failed"}
        ]
        latest_payload = latest.model_dump(mode="json")
        if latest.private:
            latest_payload["message"] = "REDACTED"
        emotion_source = next(
            (
                ev
                for ev in reversed(self._events)
                if ev.emotion_primary is not None or ev.emotion_intensity is not None
            ),
            None,
        )
        if emotion_source is not None:
            if (
                latest_payload.get("emotion_primary") is None
                and emotion_source.emotion_primary is not None
            ):
                latest_payload["emotion_primary"] = emotion_source.emotion_primary
            if (
                latest_payload.get("emotion_intensity") is None
                and emotion_source.emotion_intensity is not None
            ):
                latest_payload["emotion_intensity"] = emotion_source.emotion_intensity
        latest_emotion = None
        if emotion_source is not None:
            valence_raw = emotion_source.numeric_metrics.get("valence")
            arousal_raw = emotion_source.numeric_metrics.get("arousal")
            latest_emotion = {
                "ts": emotion_source.ts.isoformat(),
                "emotion_primary": emotion_source.emotion_primary,
                "emotion_intensity": emotion_source.emotion_intensity,
                "valence": (float(valence_raw) if isinstance(valence_raw, (int, float)) else None),
                "arousal": (float(arousal_raw) if isinstance(arousal_raw, (int, float)) else None),
            }
        relationship_source = next(
            (ev for ev in reversed(self._events) if "trust_level" in ev.numeric_metrics),
            None,
        )
        latest_relationship = None
        if relationship_source is not None:
            metrics = relationship_source.numeric_metrics
            latest_relationship = {
                "trust_level": metrics.get("trust_level"),
                "total_interactions": metrics.get("total_interactions"),
                "shared_episodes_count": metrics.get("shared_episodes_count"),
            }
        log_window = [log for log in self._logs if log.ts >= window_start]
        log_window_24h = [log for log in self._logs if log.ts >= window_24h_start]
        invocation_count = sum(
            1
            for log in log_window
            if log.message == "Tool invocation" and self._invocation_tool_name(log) is not None
        )
        failure_count = sum(1 for log in log_window if log.message == "Tool execution failed")
        invocation_count_24h = sum(
            1
            for log in log_window_24h
            if log.message == "Tool invocation" and self._invocation_tool_name(log) is not None
        )
        failure_count_24h = sum(
            1 for log in log_window_24h if log.message == "Tool execution failed"
        )
        tool_calls_per_min = invocation_count if invocation_count > 0 else len(terminal_recent)
        error_rate = (
            (failure_count / invocation_count)
            if invocation_count > 0
            else (
                sum(1 for ev in terminal_recent if not ev.ok) / len(terminal_recent)
                if terminal_recent
                else 0.0
            )
        )
        tool_calls_24h = (
            invocation_count_24h if invocation_count_24h > 0 else len(terminal_recent_24h)
        )
        error_rate_24h = (
            (failure_count_24h / invocation_count_24h)
            if invocation_count_24h > 0
            else (
                sum(1 for ev in terminal_recent_24h if not ev.ok) / len(terminal_recent_24h)
                if terminal_recent_24h
                else 0.0
            )
        )
        desire_metrics = self._latest_desire_metrics()
        latest_fixed_desires = {
            key: value for key, value in desire_metrics.items() if key in DESIRE_METRIC_KEYS
        }
        latest_emergent_desires = {
            key: value for key, value in desire_metrics.items() if key not in DESIRE_METRIC_KEYS
        }
        return {
            "latest": latest_payload,
            "latest_emotion": latest_emotion,
            "latest_relationship": latest_relationship,
            "tool_calls_per_min": tool_calls_per_min,
            "error_rate": error_rate,
            "window_24h": {"tool_calls": tool_calls_24h, "error_rate": error_rate_24h},
            "latest_desires": latest_fixed_desires,
            "latest_emergent_desires": latest_emergent_desires,
        }

    def notion_history(
        self, notion_id: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]:
        events = []
        for event in self._filtered(start, end):
            confidence = self._notion_confidence_for_event(event, notion_id)
            if confidence is None:
                continue
            cloned = event.model_copy(deep=True)
            cloned.numeric_metrics["notion_confidence"] = confidence
            events.append(cloned)
        rows: list[dict[str, object]] = []
        for at, grouped in self._bucket_events(events, start, end, bucket):
            values = [
                ev.numeric_metrics["notion_confidence"]
                for ev in grouped
                if "notion_confidence" in ev.numeric_metrics
            ]
            if values:
                rows.append({"ts": at.isoformat(), "value": sum(values) / len(values)})
        return rows

    @staticmethod
    def _parse_notion_confidences(value: object) -> dict[str, float]:
        if not isinstance(value, str) or not value:
            return {}
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        parsed: dict[str, float] = {}
        for notion_id, confidence in payload.items():
            if not isinstance(notion_id, str) or not isinstance(confidence, (int, float)):
                continue
            parsed[notion_id] = float(confidence)
        return parsed

    @classmethod
    def _notion_confidence_for_event(
        cls,
        event: DashboardEvent,
        notion_id: str,
    ) -> float | None:
        confidence_map = cls._parse_notion_confidences(
            event.string_metrics.get("notion_confidences")
        )
        if notion_id in confidence_map:
            return confidence_map[notion_id]

        related_ids = {
            candidate
            for key in (
                "notion_created",
                "notion_reinforced",
                "notion_weakened",
                "notion_dormant",
                "notion_decayed",
                "notion_pruned",
                "notion_merged",
            )
            for candidate in event.string_metrics.get(key, "").split(",")
            if candidate
        }
        if (
            notion_id in related_ids
            and len(related_ids) == 1
            and "notion_confidence" in event.numeric_metrics
        ):
            return float(event.numeric_metrics["notion_confidence"])
        return None
