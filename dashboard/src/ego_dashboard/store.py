from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from ego_dashboard.constants import DESIRE_METRIC_KEYS
from ego_dashboard.models import DashboardEvent, LogEvent

_BUCKETS = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "15m": timedelta(minutes=15)}


class TelemetryStore:
    def __init__(self) -> None:
        self._events: list[DashboardEvent] = []
        self._logs: list[LogEvent] = []

    def ingest(self, event: DashboardEvent) -> None:
        self._events.append(event)
        self._events.sort(key=lambda item: item.ts)

    def ingest_log(self, event: LogEvent) -> None:
        self._logs.append(event)
        self._logs.sort(key=lambda item: item.ts)

    def _bucket_delta(self, bucket: str) -> timedelta:
        return _BUCKETS.get(bucket, timedelta(minutes=1))

    def _filtered(self, start: datetime, end: datetime) -> list[DashboardEvent]:
        return [item for item in self._events if start <= item.ts <= end]

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
        events = self._filtered(start, end)
        rows: list[dict[str, object]] = []
        for at, grouped in self._bucket_events(events, start, end, bucket):
            counts: dict[str, int] = Counter(ev.tool_name for ev in grouped)
            row: dict[str, object] = {"ts": at.isoformat(), **counts}
            rows.append(row)
        return rows

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
        logger: str | None = None,
    ) -> list[dict[str, object]]:
        values = [log for log in self._logs if start <= log.ts <= end]
        if level:
            values = [log for log in values if log.level == level.upper()]
        if logger:
            values = [log for log in values if log.logger == logger]
        rows: list[dict[str, object]] = []
        for item in values[-300:]:
            row = item.model_dump(mode="json")
            if item.private:
                row["message"] = "REDACTED"
            rows.append(row)
        return rows

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

    def current(self) -> dict[str, object]:
        if not self._events:
            return {
                "latest": None,
                "tool_calls_per_min": 0,
                "error_rate": 0.0,
                "window_24h": {"tool_calls": 0, "error_rate": 0.0},
                "latest_desires": {},
            }

        latest = self._events[-1]
        window_start = latest.ts - timedelta(minutes=1)
        window_24h_start = latest.ts - timedelta(hours=24)
        recent = [ev for ev in self._events if ev.ts >= window_start]
        recent_24h = [ev for ev in self._events if ev.ts >= window_24h_start]
        errors = [ev for ev in recent if not ev.ok]
        errors_24h = [ev for ev in recent_24h if not ev.ok]
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
        log_window = [log for log in self._logs if log.ts >= window_start]
        log_window_24h = [log for log in self._logs if log.ts >= window_24h_start]
        invocation_count = sum(
            1
            for log in log_window
            if log.message == "Tool invocation" and "tool_name" in log.fields
        )
        failure_count = sum(1 for log in log_window if log.message == "Tool execution failed")
        invocation_count_24h = sum(
            1
            for log in log_window_24h
            if log.message == "Tool invocation" and "tool_name" in log.fields
        )
        failure_count_24h = sum(
            1 for log in log_window_24h if log.message == "Tool execution failed"
        )
        tool_calls_per_min = invocation_count if invocation_count > 0 else len(recent)
        error_rate = (
            (failure_count / invocation_count)
            if invocation_count > 0
            else (len(errors) / len(recent) if recent else 0.0)
        )
        tool_calls_24h = invocation_count_24h if invocation_count_24h > 0 else len(recent_24h)
        error_rate_24h = (
            (failure_count_24h / invocation_count_24h)
            if invocation_count_24h > 0
            else (len(errors_24h) / len(recent_24h) if recent_24h else 0.0)
        )
        return {
            "latest": latest_payload,
            "tool_calls_per_min": tool_calls_per_min,
            "error_rate": error_rate,
            "window_24h": {"tool_calls": tool_calls_24h, "error_rate": error_rate_24h},
            "latest_desires": self._latest_numeric_metrics(DESIRE_METRIC_KEYS),
        }
