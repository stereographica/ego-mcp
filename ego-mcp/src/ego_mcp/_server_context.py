"""Context and relationship analysis helpers for server handlers."""

from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from ego_mcp.config import EgoConfig
from ego_mcp.memory import MemoryStore
from ego_mcp.relationship import RelationshipStore
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Memory

logger = logging.getLogger(__name__)


def _self_model_store_for_memory(memory: MemoryStore) -> SelfModelStore:
    """Create a self-model store using the same configured data directory as memory."""
    return SelfModelStore(memory.data_dir / "self_model.json")


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity for embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _fading_or_dormant_questions(
    memory: MemoryStore, store: SelfModelStore | None = None
) -> list[dict[str, Any]]:
    """Return unresolved questions that are no longer fully active (salience <= 0.3)."""
    model_store = store or _self_model_store_for_memory(memory)
    return [
        q
        for q in model_store.get_unresolved_questions_with_salience()
        if float(q.get("salience", 0.0)) <= 0.3
    ]


def _fading_important_questions(
    memory: MemoryStore, store: SelfModelStore | None = None
) -> list[dict[str, Any]]:
    """Return fading (not dormant) high-importance unresolved questions."""
    model_store = store or _self_model_store_for_memory(memory)
    return [
        q
        for q in model_store.get_unresolved_questions_with_salience()
        if 0.1 < float(q.get("salience", 0.0)) <= 0.3
        and int(q.get("importance", 3)) >= 4
    ]


def _find_related_forgotten_questions(
    memory: MemoryStore,
    content: str,
    *,
    threshold: float = 0.4,
    max_candidates: int = 10,
    candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Find fading/dormant unresolved questions semantically related to new content."""
    source_candidates = candidates if candidates is not None else _fading_or_dormant_questions(memory)
    filtered = [
        q for q in source_candidates if isinstance(q.get("question"), str) and q.get("question")
    ][:max_candidates]
    if not filtered:
        return []

    try:
        content_embedding = memory.embed([content])[0]
        question_texts = [str(q["question"]) for q in filtered]
        question_embeddings = memory.embed(question_texts)
    except Exception as exc:
        logger.warning("Question relevance embedding failed: %s", exc)
        return []

    related: list[dict[str, Any]] = []
    for question, embedding in zip(filtered, question_embeddings):
        similarity = _cosine_similarity(content_embedding, embedding)
        if similarity > threshold:
            salience = float(question.get("salience", 0.0))
            band = "dormant" if salience <= 0.1 else "fading"
            related.append({**question, "trigger_similarity": similarity, "band": band})

    related.sort(key=lambda q: float(q.get("trigger_similarity", 0.0)), reverse=True)
    return related


def _relationship_store(config: EgoConfig) -> RelationshipStore:
    return RelationshipStore(config.data_dir / "relationships" / "models.json")


async def _summarize_conversation_tendency(
    memory: MemoryStore, person: str
) -> tuple[str, str, list[str], list[str]]:
    conversations = await memory.list_recent(n=200, category_filter="conversation")
    person_lc = person.lower()

    filtered = [m for m in conversations if person_lc in m.content.lower()]
    pool = filtered if filtered else conversations
    if not pool:
        return "no recent conversation memories", "unknown tone", [], []

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)

    last_7d = 0
    tones: dict[str, int] = {}
    for mem in pool:
        tone = mem.emotional_trace.primary.value
        tones[tone] = tones.get(tone, 0) + 1
        try:
            ts = datetime.fromisoformat(mem.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= window_start:
                last_7d += 1
        except ValueError:
            continue

    dominant_tone = max(tones.items(), key=lambda x: x[1])[0]
    frequency = (
        f"{last_7d} mentions in last 7d"
        if filtered
        else f"{last_7d} conversations in last 7d"
    )
    preferred_topics, sensitive_topics = _infer_topics_from_memories(pool)
    return frequency, dominant_tone, preferred_topics, sensitive_topics


def _infer_topics_from_memories(memories: list[Memory]) -> tuple[list[str], list[str]]:
    """Infer coarse preferred/sensitive topics from conversation memories."""
    topic_keywords: dict[str, tuple[str, ...]] = {
        "technical": ("code", "config", "test", "bug", "mcp", "deploy", "python"),
        "planning": ("plan", "schedule", "deadline", "priority", "roadmap"),
        "relationship": ("feel", "thanks", "support", "help", "trust"),
        "learning": ("learn", "research", "explore", "curious", "study"),
    }
    counts: Counter[str] = Counter()
    sensitive_counts: Counter[str] = Counter()

    for m in memories:
        content = m.content.lower()
        is_sensitive_mood = (
            m.emotional_trace.primary.value == "sad" or m.emotional_trace.valence < -0.3
        )
        for topic, keywords in topic_keywords.items():
            if any(keyword in content for keyword in keywords):
                counts[topic] += 1
                if is_sensitive_mood:
                    sensitive_counts[topic] += 1

    preferred_topics = [topic for topic, count in counts.most_common(3) if count > 0]
    sensitive_topics = [
        topic for topic, count in sensitive_counts.most_common(2) if count > 0
    ]
    return preferred_topics, sensitive_topics


async def _relationship_snapshot(
    config: EgoConfig, memory: MemoryStore, person: str
) -> str:
    """Build a compact relationship summary line for surface tools."""
    store = _relationship_store(config)
    rel = store.get(person)
    frequency, dominant_tone, _, _ = await _summarize_conversation_tendency(
        memory, person
    )
    parts = [
        f"{person}: trust={rel.trust_level:.2f}",
        f"interactions={rel.total_interactions}",
        f"shared_episodes={len(rel.shared_episode_ids)}",
        f"dominant_tone={dominant_tone}",
    ]
    if rel.last_interaction:
        parts.append(f"last_interaction={rel.last_interaction[:10]}")
    parts.append(f"recent_frequency={frequency}")
    return ", ".join(parts)


async def _derive_desire_modulation(
    memory: MemoryStore,
    *,
    fading_important_questions: list[dict[str, Any]] | None = None,
    recent_memories: list[Memory] | None = None,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Infer transient desire modifiers from recent memory context."""
    recent = recent_memories if recent_memories is not None else await memory.list_recent(n=30)
    context_boosts: dict[str, float] = {}
    fading_important = (
        fading_important_questions
        if fading_important_questions is not None
        else _fading_important_questions(memory)
    )
    if not recent:
        if fading_important:
            context_boosts["cognitive_coherence"] = min(
                0.12, len(fading_important) * 0.04
            )
        return context_boosts, {}, {}

    emotional_modulation: dict[str, float] = {}
    prediction_error: dict[str, float] = {}

    categories = Counter(m.category.value for m in recent)
    if categories.get("technical", 0) >= 3:
        context_boosts["pattern_seeking"] = (
            context_boosts.get("pattern_seeking", 0.0) + 0.08
        )
        context_boosts["predictability"] = (
            context_boosts.get("predictability", 0.0) + 0.06
        )
    if categories.get("introspection", 0) >= 2:
        context_boosts["cognitive_coherence"] = (
            context_boosts.get("cognitive_coherence", 0.0) + 0.07
        )
    if categories.get("conversation", 0) >= 3:
        context_boosts["resonance"] = context_boosts.get("resonance", 0.0) + 0.06
        context_boosts["social_thirst"] = (
            context_boosts.get("social_thirst", 0.0) - 0.04
        )

    valences = [m.emotional_trace.valence for m in recent]
    avg_valence = sum(valences) / len(valences)
    if avg_valence <= -0.2:
        emotional_modulation["social_thirst"] = (
            emotional_modulation.get("social_thirst", 0.0) + 0.10
        )
        emotional_modulation["cognitive_coherence"] = (
            emotional_modulation.get("cognitive_coherence", 0.0) + 0.07
        )
    elif avg_valence >= 0.2:
        emotional_modulation["curiosity"] = (
            emotional_modulation.get("curiosity", 0.0) + 0.06
        )
        emotional_modulation["expression"] = (
            emotional_modulation.get("expression", 0.0) + 0.04
        )

    anxious_count = sum(1 for m in recent if m.emotional_trace.primary.value == "anxious")
    if anxious_count >= 2:
        anxious_boost = min(0.10, anxious_count * 0.03)
        emotional_modulation["cognitive_coherence"] = (
            emotional_modulation.get("cognitive_coherence", 0.0) + anxious_boost
        )
        emotional_modulation["social_thirst"] = (
            emotional_modulation.get("social_thirst", 0.0) + min(0.08, anxious_count * 0.02)
        )

    if fading_important:
        context_boosts["cognitive_coherence"] = (
            context_boosts.get("cognitive_coherence", 0.0)
            + min(0.12, len(fading_important) * 0.04)
        )

    surprise_strength = max(
        (
            m.emotional_trace.intensity
            for m in recent
            if m.emotional_trace.primary.value in {"surprised", "excited", "frustrated"}
        ),
        default=0.0,
    )
    if surprise_strength > 0.0:
        prediction_error["curiosity"] = min(0.20, 0.06 + surprise_strength * 0.14)

    return context_boosts, emotional_modulation, prediction_error
