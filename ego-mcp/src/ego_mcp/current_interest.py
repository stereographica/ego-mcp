"""Derive current interests as a computed view from recent memories, notions, and emergent desires.

This module does not create new stores; it synthesizes existing data.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime

from ego_mcp import timezone_utils
from ego_mcp.emergent_desires import EMERGENT_DESIRE_BY_ID
from ego_mcp.types import Memory, Notion

# Weight constants per source type
_WEIGHT_NOTION_LABEL = 2.0
_WEIGHT_TAG = 1.0
_WEIGHT_CATEGORY = 0.5
_WEIGHT_CATEGORY_GENERIC = 0.15

# Half-life for recency decay (hours)
_HALF_LIFE_HOURS = 12.0


def _recency_weight(timestamp: str, now: datetime | None = None) -> float:
    """Exponential decay with 12h half-life."""
    if now is None:
        now = timezone_utils.now()
    try:
        ts = datetime.fromisoformat(timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone_utils.app_timezone())
    except (ValueError, TypeError):
        return 0.0
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    return math.exp(-age_hours / _HALF_LIFE_HOURS)


def _generic_categories(
    background_memories: list[Memory],
    threshold: float = 0.25,
) -> set[str]:
    """Identify categories that appear in >= threshold fraction of background memories."""
    if not background_memories:
        return set()
    counts = Counter(m.category.value for m in background_memories)
    total = len(background_memories)
    return {cat for cat, n in counts.items() if n / total >= threshold}


def derive_current_interests(
    recent_memories: list[Memory],
    background_memories: list[Memory],
    emergent_desires: list[str],
    recent_notions: list[Notion],
    *,
    max_interests: int = 3,
    generic_threshold: float = 0.25,
) -> list[dict[str, str]]:
    """Derive current interest topics from existing data.

    Returns a list of dicts with keys: topic, source, emotion_color.
    """
    now = timezone_utils.now()
    generics = _generic_categories(background_memories, threshold=generic_threshold)

    # Accumulate weighted scores per topic
    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    emotions: dict[str, Counter[str]] = {}

    def _add(topic: str, weight: float, source: str, emotion: str | None = None) -> None:
        topic = topic.strip()
        if not topic:
            return
        scores[topic] = scores.get(topic, 0.0) + weight
        # Keep the source with the highest weight contribution
        if topic not in sources or weight > scores.get(topic, 0.0) - weight:
            sources[topic] = source
        if emotion:
            emotions.setdefault(topic, Counter())[emotion] += 1

    # 1. Recent memories: tags + category
    for mem in recent_memories:
        recency = _recency_weight(mem.timestamp, now)
        emotion_val = mem.emotional_trace.primary.value

        for tag in mem.tags:
            _add(tag, _WEIGHT_TAG * recency, "memory_tag", emotion_val)

        cat = mem.category.value
        cat_weight = _WEIGHT_CATEGORY_GENERIC if cat in generics else _WEIGHT_CATEGORY
        _add(cat, cat_weight * recency, "memory_category", emotion_val)

    # 2. Recent notions (last_reinforced within 24h)
    for notion in recent_notions:
        recency = _recency_weight(notion.last_reinforced, now)
        emotion_val = notion.emotion_tone.value
        _add(notion.label, _WEIGHT_NOTION_LABEL * recency, "notion", emotion_val)

    # 3. Emergent desires
    for desire_id in emergent_desires:
        definition = EMERGENT_DESIRE_BY_ID.get(desire_id)
        if definition is not None:
            _add(desire_id, 1.0, "emergent_desire", None)

    if not scores:
        return []

    # Sort by score descending, pick top N
    ranked = sorted(scores.items(), key=lambda item: -item[1])[:max_interests]

    results: list[dict[str, str]] = []
    for topic, _score in ranked:
        # Determine dominant emotion color for this topic
        emotion_counter = emotions.get(topic, Counter())
        if emotion_counter:
            emotion_color = emotion_counter.most_common(1)[0][0]
        else:
            emotion_color = "neutral"

        results.append({
            "topic": topic,
            "source": sources.get(topic, "unknown"),
            "emotion_color": emotion_color,
        })

    return results
