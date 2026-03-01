from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

DEFAULT_EMOTION_VECTOR = (0.5, 0.0, 0.5)
EMOTION_DEFAULTS: dict[str, tuple[float, float, float]] = {
    # emotion: (intensity, valence, arousal)
    "happy": (0.6, 0.6, 0.5),
    "excited": (0.8, 0.7, 0.8),
    "calm": (0.4, 0.3, 0.2),
    "neutral": (0.3, 0.0, 0.3),
    "curious": (0.6, 0.3, 0.6),
    "contemplative": (0.5, 0.1, 0.3),
    "thoughtful": (0.5, 0.1, 0.4),
    "grateful": (0.6, 0.7, 0.4),
    "vulnerable": (0.6, -0.3, 0.5),
    "content": (0.5, 0.5, 0.2),
    "fulfilled": (0.6, 0.6, 0.2),
    "touched": (0.7, 0.5, 0.4),
    "moved": (0.7, 0.5, 0.5),
    "concerned": (0.5, -0.3, 0.5),
    "hopeful": (0.6, 0.4, 0.5),
    "peaceful": (0.4, 0.4, 0.1),
    "love": (0.8, 0.8, 0.4),
    "warm": (0.5, 0.5, 0.3),
    "sad": (0.5, -0.6, 0.2),
    "anxious": (0.7, -0.6, 0.8),
    "angry": (0.8, -0.7, 0.9),
    "frustrated": (0.7, -0.5, 0.7),
    "lonely": (0.6, -0.6, 0.3),
    "afraid": (0.8, -0.8, 0.9),
    "ashamed": (0.6, -0.7, 0.4),
    "bored": (0.3, -0.3, 0.1),
    "nostalgic": (0.5, 0.1, 0.3),
    "contentment": (0.5, 0.5, 0.2),
    "melancholy": (0.5, -0.4, 0.2),
    "surprised": (0.7, 0.1, 0.9),
}


@dataclass(frozen=True)
class EmotionSnapshot:
    ts: datetime
    emotion_primary: str
    intensity: float
    valence: float
    arousal: float


@dataclass(frozen=True)
class MigrationStats:
    timeline_entries: int
    cleared_completion_rows: int
    updated_invocations: int
    updated_completions: int


def _parse_ts(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _float_or_default(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _normalize_emotion(raw_value: object) -> str:
    if not isinstance(raw_value, str):
        return "neutral"
    normalized = raw_value.strip().lower()
    return normalized or "neutral"


def _to_tool_args(raw_value: object) -> dict[str, object]:
    if isinstance(raw_value, dict):
        return {str(key): value for key, value in raw_value.items()}
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
    return {}


def _emotion_snapshot_from_args(ts: datetime, tool_args: dict[str, object]) -> EmotionSnapshot:
    emotion_primary = _normalize_emotion(tool_args.get("emotion"))
    defaults = EMOTION_DEFAULTS.get(emotion_primary, DEFAULT_EMOTION_VECTOR)
    return EmotionSnapshot(
        ts=ts,
        emotion_primary=emotion_primary,
        intensity=_float_or_default(tool_args.get("intensity"), defaults[0]),
        valence=_float_or_default(tool_args.get("valence"), defaults[1]),
        arousal=_float_or_default(tool_args.get("arousal"), defaults[2]),
    )


def build_emotion_timeline(log_dir: Path) -> list[EmotionSnapshot]:
    timeline: list[EmotionSnapshot] = []
    for log_path in sorted(log_dir.glob("ego-mcp-*.log")):
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("message") != "Tool invocation":
                continue
            if payload.get("tool_name") != "remember":
                continue
            raw_ts = payload.get("timestamp")
            if raw_ts is None:
                raw_ts = payload.get("ts")
            ts = _parse_ts(raw_ts)
            if ts is None:
                continue
            tool_args = _to_tool_args(payload.get("tool_args"))
            timeline.append(_emotion_snapshot_from_args(ts, tool_args))
    timeline.sort(key=lambda snapshot: snapshot.ts)
    return timeline


def find_latest_emotion_at(
    timeline: list[EmotionSnapshot],
    ts: datetime,
) -> EmotionSnapshot | None:
    latest: EmotionSnapshot | None = None
    for snapshot in timeline:
        if snapshot.ts > ts:
            break
        latest = snapshot
    return latest


def _rowcount(cursor: Any) -> int:
    raw = getattr(cursor, "rowcount", 0)
    if isinstance(raw, int) and raw > 0:
        return raw
    return 0


def run_migration(
    *,
    log_dir: Path,
    database_url: str,
    dry_run: bool = False,
) -> MigrationStats:
    timeline = build_emotion_timeline(log_dir)
    if not timeline:
        return MigrationStats(
            timeline_entries=0,
            cleared_completion_rows=0,
            updated_invocations=0,
            updated_completions=0,
        )

    cleared_completion_rows = 0
    updated_invocations = 0
    updated_completions = 0

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if not dry_run:
                cur.execute(
                    """
                    UPDATE tool_events
                    SET emotion_primary = NULL,
                        emotion_intensity = NULL,
                        numeric_metrics = numeric_metrics - 'intensity' - 'valence' - 'arousal'
                    WHERE event_type = 'tool_call_completed'
                      AND emotion_primary = 'neutral'
                      AND emotion_intensity = 0.5
                    """
                )
                cleared_completion_rows = _rowcount(cur)

            cur.execute(
                """
                SELECT ts
                FROM tool_events
                WHERE event_type = 'tool_call_invoked'
                  AND tool_name = 'remember'
                ORDER BY ts ASC
                """
            )
            invocation_rows = cur.fetchall()
            for row in invocation_rows:
                if not row:
                    continue
                ts = row[0]
                if not isinstance(ts, datetime):
                    continue
                snapshot = find_latest_emotion_at(timeline, ts.astimezone(UTC))
                if snapshot is None or dry_run:
                    continue
                cur.execute(
                    """
                    UPDATE tool_events
                    SET emotion_primary = %s,
                        emotion_intensity = %s,
                        numeric_metrics = numeric_metrics || jsonb_build_object(
                            'intensity', %s,
                            'valence', %s,
                            'arousal', %s
                        )
                    WHERE event_type = 'tool_call_invoked'
                      AND tool_name = 'remember'
                      AND ts = %s
                    """,
                    (
                        snapshot.emotion_primary,
                        snapshot.intensity,
                        snapshot.intensity,
                        snapshot.valence,
                        snapshot.arousal,
                        ts,
                    ),
                )
                updated_invocations += _rowcount(cur)

            cur.execute(
                """
                SELECT ts
                FROM tool_events
                WHERE event_type = 'tool_call_completed'
                ORDER BY ts ASC
                """
            )
            completion_rows = cur.fetchall()
            for row in completion_rows:
                if not row:
                    continue
                ts = row[0]
                if not isinstance(ts, datetime):
                    continue
                snapshot = find_latest_emotion_at(timeline, ts.astimezone(UTC))
                if snapshot is None or dry_run:
                    continue
                cur.execute(
                    """
                    UPDATE tool_events
                    SET emotion_primary = %s,
                        emotion_intensity = %s,
                        numeric_metrics = numeric_metrics || jsonb_build_object(
                            'intensity', %s,
                            'valence', %s,
                            'arousal', %s
                        )
                    WHERE event_type = 'tool_call_completed'
                      AND ts = %s
                      AND emotion_primary IS NULL
                    """,
                    (
                        snapshot.emotion_primary,
                        snapshot.intensity,
                        snapshot.intensity,
                        snapshot.valence,
                        snapshot.arousal,
                        ts,
                    ),
                )
                updated_completions += _rowcount(cur)

        if not dry_run:
            conn.commit()

    return MigrationStats(
        timeline_entries=len(timeline),
        cleared_completion_rows=cleared_completion_rows,
        updated_invocations=updated_invocations,
        updated_completions=updated_completions,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate emotion telemetry in dashboard SQL store")
    parser.add_argument("--log-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    database_url = args.database_url or os.getenv("DASHBOARD_DATABASE_URL")
    if not isinstance(database_url, str) or not database_url:
        parser.error("database URL is required via --database-url or DASHBOARD_DATABASE_URL")

    stats = run_migration(
        log_dir=args.log_dir,
        database_url=database_url,
        dry_run=args.dry_run,
    )
    mode = "dry-run" if args.dry_run else "apply"
    print(
        f"mode={mode} timeline_entries={stats.timeline_entries} "
        f"cleared_completion_rows={stats.cleared_completion_rows} "
        f"updated_invocations={stats.updated_invocations} "
        f"updated_completions={stats.updated_completions}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
