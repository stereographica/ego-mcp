"""Surface handlers for wake/introspection/consider tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ego_mcp._server_context import (
    _derive_desire_modulation,
    _fading_important_questions,
    _find_related_forgotten_questions,
    _relationship_snapshot,
    _relationship_store,
    _summarize_conversation_tendency,
)
from ego_mcp._server_emotion_formatting import _truncate_for_quote
from ego_mcp._server_runtime import get_workspace_sync
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.scaffolds import (
    SCAFFOLD_AM_I_GENUINE,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_FEEL_DESIRES,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render,
    render_with_data,
)
from ego_mcp.self_model import SelfModelStore

_relationship_snapshot_override: (
    Callable[[EgoConfig, MemoryStore, str], Awaitable[str]] | None
) = None
_derive_desire_modulation_override: (
    Callable[..., Awaitable[tuple[dict[str, float], dict[str, float], dict[str, float]]]]
    | None
) = None
_get_body_state_override: Callable[[], dict[str, Any]] | None = None


def configure_overrides(
    *,
    relationship_snapshot: Callable[[EgoConfig, MemoryStore, str], Awaitable[str]] | None = None,
    derive_desire_modulation: Callable[
        ...,
        Awaitable[tuple[dict[str, float], dict[str, float], dict[str, float]]],
    ]
    | None = None,
    get_body_state_fn: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Configure callables used for test-time override injection."""
    global _relationship_snapshot_override, _derive_desire_modulation_override, _get_body_state_override
    _relationship_snapshot_override = relationship_snapshot
    _derive_desire_modulation_override = derive_desire_modulation
    _get_body_state_override = get_body_state_fn


async def _call_relationship_snapshot(
    config: EgoConfig, memory: MemoryStore, person: str
) -> str:
    if _relationship_snapshot_override is not None:
        return await _relationship_snapshot_override(config, memory, person)
    return await _relationship_snapshot(config, memory, person)


async def _call_derive_desire_modulation(
    memory: MemoryStore,
    *,
    fading_important_questions: list[dict[str, Any]] | None = None,
    recent_memories: list[Any] | None = None,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    if _derive_desire_modulation_override is not None:
        return await _derive_desire_modulation_override(memory)
    return await _derive_desire_modulation(
        memory,
        fading_important_questions=fading_important_questions,
        recent_memories=recent_memories,
    )


def _call_get_body_state() -> dict[str, Any]:
    if _get_body_state_override is not None:
        return _get_body_state_override()
    return get_body_state()


async def _handle_wake_up(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Session start: last introspection + desires + relationship summary."""
    sync = get_workspace_sync()
    latest_text: str | None = None
    latest_since: str | None = None
    if sync is not None:
        latest_text, latest_since = sync.read_latest_monologue()

    if latest_text:
        since = latest_since or "workspace-sync"
        intro_line = (
            f'Last introspection ({since}):\n"{_truncate_for_quote(latest_text)}"'
        )
    else:
        recent_introspections = await memory.list_recent(
            n=1, category_filter="introspection"
        )
        if recent_introspections:
            m = recent_introspections[0]
            since = m.timestamp[:16] if len(m.timestamp) >= 16 else m.timestamp
            intro_line = (
                f'Last introspection ({since}):\n"{_truncate_for_quote(m.content)}"'
            )
        else:
            intro_line = "No introspection yet."

    desire_summary = desire.format_summary()
    relationship_line = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )

    parts = [intro_line, f"\nDesires: {desire_summary}", relationship_line]
    data = "\n".join(parts)

    return render_with_data(data, SCAFFOLD_WAKE_UP, config.companion_name)


async def _handle_feel_desires(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Check desire levels with scaffold."""
    self_store = SelfModelStore(config.data_dir / "self_model.json")
    fading_questions = _fading_important_questions(memory, store=self_store)
    (
        context_boosts,
        emotional_modulation,
        prediction_error,
    ) = await _call_derive_desire_modulation(
        memory, fading_important_questions=fading_questions
    )
    levels = desire.compute_levels_with_modulation(
        context_boosts=context_boosts,
        emotional_modulation=emotional_modulation,
        prediction_error=prediction_error,
    )
    body_state = _call_get_body_state()
    phase = body_state.get("time_phase", "unknown")
    load = body_state.get("system_load", "unknown")

    if phase == "late_night":
        levels["cognitive_coherence"] = min(
            1.0, levels.get("cognitive_coherence", 0.0) + 0.1
        )
        levels["social_thirst"] = max(0.0, levels.get("social_thirst", 0.0) - 0.1)
    elif phase == "morning":
        levels["curiosity"] = min(1.0, levels.get("curiosity", 0.0) + 0.05)

    if load == "high":
        levels = {
            name: round(max(0.0, min(1.0, level * 0.9)), 3)
            for name, level in levels.items()
        }

    sorted_desires = sorted(levels.items(), key=lambda x: -x[1])

    def tag(level: float) -> str:
        if level >= 0.7:
            return "high"
        elif level >= 0.4:
            return "mid"
        else:
            return "low"

    lines = [f"{name}[{level:.1f}/{tag(level)}]" for name, level in sorted_desires]
    data = " ".join(lines)

    scaffold = render(SCAFFOLD_FEEL_DESIRES, config.companion_name)
    if levels.get("cognitive_coherence", 0.0) >= 0.6 and fading_questions:
        scaffold += (
            "\nSomething feels unresolved. You can't quite name it, but there's a nagging feeling.\n"
            "Consider running introspect to see if anything surfaces."
        )
    return compose_response(data, scaffold)


async def _handle_introspect(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Introspection materials: memories + desires + self/relationship cues."""
    recent_all = await memory.list_recent(n=30)
    recent = recent_all[:3]
    if recent:
        mem_lines = ["Recent memories:"]
        for m in recent:
            emotion = m.emotional_trace.primary.value
            ts = m.timestamp[:10] if len(m.timestamp) >= 10 else m.timestamp
            content = m.content[:80] + "..." if len(m.content) > 80 else m.content
            mem_lines.append(f"- [{ts}] {content} (emotion: {emotion})")
        memory_section = "\n".join(mem_lines)
    else:
        memory_section = "No memories yet."

    desire_summary = desire.format_summary()
    self_store = SelfModelStore(config.data_dir / "self_model.json")
    fading_questions = _fading_important_questions(memory, store=self_store)
    (
        introspect_context_boosts,
        introspect_emotional_modulation,
        introspect_prediction_error,
    ) = await _call_derive_desire_modulation(
        memory,
        fading_important_questions=fading_questions,
        recent_memories=recent_all,
    )
    introspect_levels = desire.compute_levels_with_modulation(
        context_boosts=introspect_context_boosts,
        emotional_modulation=introspect_emotional_modulation,
        prediction_error=introspect_prediction_error,
    )
    coherence_level = float(introspect_levels.get("cognitive_coherence", 0.0))
    self_model = self_store.get()
    goals = (
        ", ".join(self_model.current_goals[:2]) if self_model.current_goals else "none"
    )
    self_summary = (
        f"Self model: confidence={self_model.confidence_calibration:.2f}, goals={goals}"
    )
    if self_model.last_updated:
        self_summary += f", last_updated={self_model.last_updated[:10]}"

    active_questions, resurfacing_questions = self_store.get_visible_questions()
    question_lines: list[str] = []
    if active_questions:
        question_lines.append("Unresolved questions:")
        for item in active_questions:
            question_lines.append(
                f"- [{item['id']}] {item['question']} (importance: {item['importance']})"
            )
    else:
        question_lines.append("No unresolved questions yet.")

    resurfacing_triggered_by_recent = False
    if recent and resurfacing_questions:
        resurfacing_triggered_by_recent = bool(
            _find_related_forgotten_questions(
                memory,
                recent[0].content,
                candidates=resurfacing_questions,
            )
        )
    show_resurfacing = bool(resurfacing_questions) and (
        coherence_level >= 0.6 or resurfacing_triggered_by_recent
    )

    if show_resurfacing:
        question_lines.append("")
        question_lines.append("Resurfacing (you'd almost forgotten):")
        for item in resurfacing_questions:
            dormant_days = max(0, int(round(float(item.get("age_days", 0.0)))))
            question_lines.append(
                "- "
                f"[{item['id']}] {item['question']} "
                f"(importance: {item['importance']}, dormant {dormant_days} days)"
            )

    if active_questions or resurfacing_questions:
        question_lines.append("")
        question_lines.append(
            'To resolve a question: update_self(field="resolve_question", value="<question_id>")'
        )

    open_questions = "\n".join(question_lines)

    if recent_all:
        category_counts: dict[str, int] = {}
        emotion_counts: dict[str, int] = {}
        for m in recent_all:
            category_counts[m.category.value] = (
                category_counts.get(m.category.value, 0) + 1
            )
            emotion = m.emotional_trace.primary.value
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        top_category = max(category_counts.items(), key=lambda x: x[1])[0]
        top_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0]
        trend = f"Recent tendency: leaning toward {top_category} topics, tone={top_emotion}."
    else:
        trend = "Recent tendency: not enough data."

    relationship_summary = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )

    parts = [
        memory_section,
        f"\nDesires: {desire_summary}",
        self_summary,
        relationship_summary,
        open_questions,
        trend,
    ]
    data = "\n".join(parts)

    return render_with_data(data, SCAFFOLD_INTROSPECT, config.companion_name)


async def _handle_consider_them(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """ToM: relationship summary + scaffold."""
    person = args.get("person", config.companion_name)
    store = _relationship_store(config)
    (
        frequency,
        dominant_tone,
        preferred_topics,
        sensitive_topics,
    ) = await _summarize_conversation_tendency(memory, person)

    now_iso = datetime.now(timezone.utc).isoformat()
    if dominant_tone != "unknown tone":
        store.add_interaction(person, now_iso, dominant_tone)
    rel = store.apply_tom_feedback(
        person_id=person,
        dominant_tone=dominant_tone,
        preferred_topics=preferred_topics,
        sensitive_topics=sensitive_topics,
    )

    relationship_summary = (
        f"{person}: trust={rel.trust_level:.2f}, "
        f"interactions={rel.total_interactions}, "
        f"shared_episodes={len(rel.shared_episode_ids)}"
    )
    if rel.preferred_topics:
        relationship_summary += (
            f", preferred_topics={','.join(rel.preferred_topics[:2])}"
        )
    if rel.sensitive_topics:
        relationship_summary += (
            f", sensitive_topics={','.join(rel.sensitive_topics[:2])}"
        )
    if rel.last_interaction:
        relationship_summary += f", last_interaction={rel.last_interaction[:10]}"
    if rel.emotional_baseline:
        baseline_tone = max(
            rel.emotional_baseline.items(),
            key=lambda item: item[1],
        )[0]
        relationship_summary += f", baseline_tone={baseline_tone}"

    tendency = f"Recent dialog tendency: {frequency}, observed_tone={dominant_tone}"
    recent_moods = rel.recent_mood_trajectory[-3:]
    if recent_moods:
        mood_tail = " > ".join(
            str(item.get("mood", "unknown"))
            for item in recent_moods
            if isinstance(item, dict)
        )
        data = (
            f"{relationship_summary}\n{tendency}\nRecent mood trajectory: {mood_tail}"
        )
    else:
        data = f"{relationship_summary}\n{tendency}"
    return render_with_data(data, SCAFFOLD_CONSIDER_THEM, config.companion_name)


def _handle_am_i_genuine() -> str:
    """Authenticity check with consistent data+scaffold format."""
    data = "Self-check triggered."
    return compose_response(data, SCAFFOLD_AM_I_GENUINE)
