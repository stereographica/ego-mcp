"""Formatting helpers for decay-aware memory rendering."""

from __future__ import annotations

import re
from datetime import datetime

from ego_mcp import timezone_utils
from ego_mcp.types import Memory

_LATIN_KEYWORD_RE = re.compile(r"[A-Za-z]{4,}")
_CJK_KEYWORD_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]{2,}")


def _approx_time(timestamp: str, now: datetime | None = None) -> str:
    if now is None:
        now = timezone_utils.now()
    try:
        then = datetime.fromisoformat(timestamp)
    except ValueError:
        return "~some time ago"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone_utils.app_timezone())

    age_days = max(0.0, (now - then).total_seconds() / 86400)
    if age_days < 1:
        return "~today"
    if age_days < 14:
        return f"~{max(1, round(age_days))} day{'s' if age_days >= 1.5 else ''} ago"
    if age_days < 60:
        weeks = max(1, round(age_days / 7))
        return f"~{weeks} week{'s' if weeks != 1 else ''} ago"
    if age_days < 730:
        months = max(1, round(age_days / 30))
        return f"~{months} month{'s' if months != 1 else ''} ago"
    years = max(1, round(age_days / 365))
    return f"~{years} year{'s' if years != 1 else ''} ago"


def _extract_keywords(content: str, max_keywords: int = 5) -> str:
    keywords: set[str] = set()
    keywords.update(match.group(0).lower() for match in _LATIN_KEYWORD_RE.finditer(content))
    keywords.update(match.group(0) for match in _CJK_KEYWORD_RE.finditer(content))
    unique = sorted(keywords, key=lambda word: (-len(word), word))
    return ", ".join(unique[:max_keywords]) or "fragments"


def format_memory_by_decay(
    memory: Memory,
    decay: float,
    now: datetime | None = None,
) -> str:
    """Render a memory with progressively degraded detail."""
    if decay >= 0.5:
        emotion_label = memory.emotional_trace.primary.value
        if memory.emotional_trace.intensity >= 0.7:
            emotion_label = f"{emotion_label}({memory.emotional_trace.intensity:.1f})"
        details = [
            f"emotion: {emotion_label}",
            f"category: {memory.category.value}",
            f"importance: {memory.importance}",
        ]
        if memory.emotional_trace.secondary:
            details.insert(1, f"undercurrent: {memory.emotional_trace.secondary[0].value}")
        if memory.tags:
            details.append(f"tags: {', '.join(memory.tags)}")
        if memory.is_private:
            details.append("private")
        return f"{memory.content}\n   {' | '.join(details)}"

    emotion = memory.emotional_trace.primary.value
    approx_time = _approx_time(memory.timestamp, now=now)
    if decay >= 0.2:
        keywords = _extract_keywords(memory.content)
        return (
            f"{emotion} {memory.category.value} — {keywords} "
            f"({approx_time}) decay: {decay:.2f}"
        )
    return f"{emotion}, {approx_time} decay: {decay:.2f}"
