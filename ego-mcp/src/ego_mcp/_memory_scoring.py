"""Memory scoring utilities."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from ego_mcp.types import Memory

EMOTION_BOOST_MAP: dict[str, float] = {
    "excited": 0.4,
    "surprised": 0.35,
    "moved": 0.3,
    "frustrated": 0.28,
    "sad": 0.25,
    "anxious": 0.22,
    "happy": 0.2,
    "melancholy": 0.18,
    "nostalgic": 0.15,
    "curious": 0.1,
    "contentment": 0.08,
    "neutral": 0.0,
}


def calculate_time_decay(
    timestamp: str,
    now: datetime | None = None,
    half_life_days: float = 30.0,
) -> float:
    """Exponential time decay. Returns 0.0 (forgotten) to 1.0 (fresh)."""
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        memory_time = datetime.fromisoformat(timestamp)
        if memory_time.tzinfo is None:
            memory_time = memory_time.replace(tzinfo=timezone.utc)
    except ValueError:
        return 1.0

    age_seconds = (now - memory_time).total_seconds()
    if age_seconds < 0:
        return 1.0

    age_days = age_seconds / 86400
    decay = math.pow(2, -age_days / half_life_days)
    return max(0.0, min(1.0, decay))


def calculate_emotion_boost(emotion: str) -> float:
    """Emotion-based boost value."""
    return EMOTION_BOOST_MAP.get(emotion, 0.0)


def calculate_importance_boost(importance: int) -> float:
    """Importance-based boost. 1→0.0, 5→0.4."""
    clamped = max(1, min(5, importance))
    return (clamped - 1) / 10


def calculate_final_score(
    semantic_distance: float,
    time_decay: float,
    emotion_boost: float,
    importance_boost: float,
    semantic_weight: float = 1.0,
    decay_weight: float = 0.3,
    emotion_weight: float = 0.2,
    importance_weight: float = 0.2,
) -> float:
    """Combined score. Lower = more relevant."""
    decay_penalty = (1.0 - time_decay) * decay_weight
    total_boost = emotion_boost * emotion_weight + importance_boost * importance_weight
    final = semantic_distance * semantic_weight + decay_penalty - total_boost
    return max(0.0, final)


def count_emotions_weighted(memories: list[Memory]) -> dict[str, float]:
    """Count primary emotions (1.0) and secondary emotions (0.4)."""
    counts: dict[str, float] = {}
    for memory in memories:
        primary = memory.emotional_trace.primary.value
        counts[primary] = counts.get(primary, 0.0) + 1.0
        for secondary in memory.emotional_trace.secondary:
            counts[secondary.value] = counts.get(secondary.value, 0.0) + 0.4
    return counts
