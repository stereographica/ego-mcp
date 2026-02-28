"""Formatting helpers for recall and emotional trend outputs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable

from ego_mcp.memory import calculate_time_decay, count_emotions_weighted
from ego_mcp.types import Memory, MemorySearchResult

_relative_time_override: Callable[[str, datetime | None], str] | None = None
_calculate_time_decay_override: Callable[..., float] | None = None


def configure_overrides(
    *,
    relative_time: Callable[[str, datetime | None], str] | None = None,
    calculate_time_decay_fn: Callable[..., float] | None = None,
) -> None:
    """Configure callables used for test-time override injection."""
    global _relative_time_override, _calculate_time_decay_override
    _relative_time_override = relative_time
    _calculate_time_decay_override = calculate_time_decay_fn


def _call_relative_time(timestamp: str, now: datetime | None = None) -> str:
    if _relative_time_override is not None:
        return _relative_time_override(timestamp, now)
    return _relative_time(timestamp, now)


def _call_calculate_time_decay(
    timestamp: str, now: datetime | None = None, half_life_days: float = 30.0
) -> float:
    if _calculate_time_decay_override is not None:
        return _calculate_time_decay_override(
            timestamp, now=now, half_life_days=half_life_days
        )
    return calculate_time_decay(timestamp, now=now, half_life_days=half_life_days)


def _truncate_for_quote(text: str, limit: int = 220) -> str:
    """Trim long text snippets for concise tool responses."""
    compact = " ".join(text.split()).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _truncate_for_log(text: str, limit: int = 1200) -> tuple[str, bool]:
    """Trim long tool outputs for logs while keeping metadata."""
    compact = text.strip()
    if len(compact) <= limit:
        return compact, False
    return compact[: limit - 3].rstrip() + "...", True


def _relative_time(timestamp: str, now: datetime | None = None) -> str:
    """Format an ISO8601 timestamp as compact relative time (e.g. 2d ago)."""
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return "unknown time"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{max(1, seconds // 3600)}h ago"

    days = max(1, seconds // 86400)
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{max(1, days // 7)}w ago"
    if days < 365:
        return f"{max(1, days // 30)}mo ago"
    return f"{max(1, days // 365)}y ago"


def _format_recall_entry(
    index: int,
    result: MemorySearchResult,
    now: datetime | None = None,
) -> str:
    """Render a single recall result in the compact two-line format."""
    if now is None:
        now = datetime.now(timezone.utc)
    memory = result.memory
    age = _call_relative_time(memory.timestamp, now=now)
    content = _truncate_for_quote(memory.content, limit=70)

    emotion_label = memory.emotional_trace.primary.value
    if memory.emotional_trace.intensity >= 0.7:
        emotion_label = f"{emotion_label}({memory.emotional_trace.intensity:.1f})"

    details = [f"emotion: {emotion_label}"]
    if memory.emotional_trace.secondary:
        details.append(f"undercurrent: {memory.emotional_trace.secondary[0].value}")
    details.append(f"importance: {memory.importance}")
    details.append(f"score: {result.score:.2f}")
    if memory.is_private:
        details.append("private")

    return f"{index}. [{age}] {content}\n   {' | '.join(details)}"


def _recall_scaffold(n_shown: int, total_count: int, filters_used: list[str]) -> str:
    """Build a recall scaffold that adapts to visible results and used filters."""
    parts = ["How do these memories connect to the current moment?"]
    if n_shown < total_count:
        parts.append(f"Showing {n_shown} of ~{total_count}. Increase n_results for more.")

    all_filters = {
        "emotion_filter",
        "category_filter",
        "date_from",
        "date_to",
        "valence_range",
        "arousal_range",
    }
    if not filters_used:
        parts.append(
            "Narrow by: emotion_filter, category_filter, date_from/date_to, "
            "valence_range, arousal_range."
        )
    else:
        remaining = sorted(all_filters - set(filters_used))
        if remaining:
            parts.append(f"Also available: {', '.join(remaining)}.")

    parts.append("Need narrative detail? Use get_episode.")
    parts.append("If you found a new relation, use link_memories.")
    return "\n".join(parts)


def _parse_iso_datetime(timestamp: str) -> datetime | None:
    """Parse ISO8601 timestamp as timezone-aware datetime."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _memories_within_days(
    memories: list[Memory], days: float, now: datetime | None = None
) -> list[Memory]:
    """Return memories whose timestamps fall within the last `days` days."""
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    selected: list[Memory] = []
    for memory in memories:
        parsed = _parse_iso_datetime(getattr(memory, "timestamp", ""))
        if parsed is None:
            continue
        if parsed >= window_start:
            selected.append(memory)
    selected.sort(key=lambda m: str(getattr(m, "timestamp", "")), reverse=True)
    return selected


def _secondary_weighted_counts(memories: list[Memory]) -> dict[str, float]:
    """Count secondary emotions only, using the same 0.4 undercurrent weight."""
    counts: dict[str, float] = {}
    for memory in memories:
        for emotion in memory.emotional_trace.secondary:
            counts[emotion.value] = counts.get(emotion.value, 0.0) + 0.4
    return counts


def _valence_arousal_to_impression(avg_valence: float, avg_arousal: float) -> str:
    """Convert monthly average valence/arousal into a coarse impression phrase."""
    if avg_valence > 0.3 and avg_arousal > 0.5:
        return "an energetic, fulfilling month"
    if avg_valence > 0.3 and avg_arousal <= 0.5:
        return "a quietly content month"
    if avg_valence < -0.3 and avg_arousal > 0.5:
        return "a turbulent, unsettled month"
    if avg_valence < -0.3 and avg_arousal <= 0.5:
        return "a heavy, draining month"
    if abs(avg_valence) <= 0.3 and avg_arousal <= 0.3:
        return "a numb, uneventful month"
    return "a month of mixed feelings"


def _format_recent_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format vivid recent emotional events (~3 days)."""
    recent = _memories_within_days(memories, 3, now=now)
    lines = ["Recent (past 3 days):"]
    if not recent:
        lines.append("  - No recent emotional events in this window.")
        return "\n".join(lines)

    selected = list(recent[:3])
    peak = max(recent, key=lambda m: float(m.emotional_trace.intensity))
    if all(peak.id != item.id for item in selected):
        selected = selected[:2] + [peak]

    selected_ids = {item.id for item in selected}
    ordered_selected = [m for m in recent if m.id in selected_ids][:3]
    peak_id = peak.id
    for memory in ordered_selected:
        age = _call_relative_time(memory.timestamp, now=now)
        emotion = memory.emotional_trace.primary.value
        parts = [f"{emotion}"]
        if memory.id == peak_id:
            parts.append(f"peak intensity {memory.emotional_trace.intensity:.1f}")
        if memory.emotional_trace.secondary:
            parts.append(f"undercurrent: {memory.emotional_trace.secondary[0].value}")
        lines.append(
            f"  - [{age}] {_truncate_for_quote(memory.content, 70)} ({', '.join(parts)})"
        )
    return "\n".join(lines)


def _format_week_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format moderate-resolution weekly emotional trends (~7 days)."""
    week = _memories_within_days(memories, 7, now=now)
    lines = ["This week:"]
    if not week:
        lines.append("  Dominant: not enough recent data")
        return "\n".join(lines)

    weighted = count_emotions_weighted(week)
    dominant = sorted(weighted.items(), key=lambda item: item[1], reverse=True)[:2]
    if dominant:
        lines.append(
            "  Dominant: " + ", ".join(f"{name}({score:.1f})" for name, score in dominant)
        )

    secondary_counts = _secondary_weighted_counts(week)
    if secondary_counts:
        under_name, under_score = max(secondary_counts.items(), key=lambda item: item[1])
        lines.append(f"  Undercurrent: {under_name}({under_score:.1f})")

    chronological = sorted(week, key=lambda m: str(m.timestamp))
    if chronological:
        first_emotion = chronological[0].emotional_trace.primary.value
        last_emotion = chronological[-1].emotional_trace.primary.value
        lines.append(f"  Shift: {first_emotion} -> {last_emotion}")

    run_emotion = ""
    run_length = 0
    cluster_emotion: str | None = None
    for memory in chronological:
        current = memory.emotional_trace.primary.value
        if current == run_emotion:
            run_length += 1
        else:
            run_emotion = current
            run_length = 1
        if run_length >= 3:
            cluster_emotion = current
            break
    if cluster_emotion:
        lines.append(f"  ! Cluster detected: {cluster_emotion} repeated 3+ times")

    return "\n".join(lines)


def _format_month_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format impressionistic monthly emotional summary (~30 days)."""
    month = _memories_within_days(memories, 30, now=now)
    lines = ["This month (impressionistic):"]
    if not month:
        lines.append("  Tone: not enough monthly data")
        return "\n".join(lines)

    avg_valence = sum(m.emotional_trace.valence for m in month) / len(month)
    avg_arousal = sum(m.emotional_trace.arousal for m in month) / len(month)
    lines.append(f"  Tone: {_valence_arousal_to_impression(avg_valence, avg_arousal)}.")

    peak = max(month, key=lambda m: float(m.emotional_trace.intensity))
    end = month[0]
    lines.append(f"  Peak: {_truncate_for_quote(peak.content, 70)}")
    lines.append(f"  End: {_truncate_for_quote(end.content, 70)}")

    week_primarys = {
        m.emotional_trace.primary.value for m in _memories_within_days(memories, 7, now=now)
    }
    month_counts = Counter(m.emotional_trace.primary.value for m in month)
    fading_emotion = next(
        (
            emotion
            for emotion, _count in month_counts.most_common()
            if emotion not in week_primarys
        ),
        None,
    )
    candidate_decay = 1.0
    if fading_emotion:
        candidate_memories = [
            m for m in month if m.emotional_trace.primary.value == fading_emotion
        ]
        if candidate_memories:
            candidate_decay = sum(
                _call_calculate_time_decay(m.timestamp, now=now)
                for m in candidate_memories
            ) / len(candidate_memories)
    if fading_emotion and candidate_decay <= 0.5:
        lines.append(
            f"  [fading] {fading_emotion} appears mostly in older memories and is fading."
        )

    return "\n".join(lines)
