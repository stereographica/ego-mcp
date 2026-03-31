"""Surface handlers for wake/introspection/consider tools."""

from __future__ import annotations

from collections import Counter
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
from ego_mcp._server_runtime import (
    get_impulse_manager,
    get_notion_store,
    get_workspace_sync,
    update_tool_metadata,
)
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.desire_blend import blend_desires
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import is_conviction
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
from ego_mcp.types import Notion

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


def _merge_topic_hints(*topic_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for topic_group in topic_groups:
        for topic in topic_group:
            if topic in seen:
                continue
            seen.add(topic)
            merged.append(topic)
    return merged


def _notion_map() -> dict[str, Notion]:
    try:
        store = get_notion_store()
    except Exception:
        return {}
    return {
        notion.id: notion
        for notion in store.list_all()
        if isinstance(notion, Notion) and notion.id
    }


def _list_notions_safe() -> list[Notion]:
    return list(_notion_map().values())


def _format_associated_from_map(
    notion: Notion,
    notion_map: dict[str, Notion],
    *,
    limit: int,
) -> str:
    associated = [
        notion_map[related_id]
        for related_id in notion.related_notion_ids
        if related_id in notion_map
    ]
    associated.sort(key=lambda item: (-item.confidence, item.label, item.id))
    if not associated:
        return ""
    return " → " + ", ".join(f'"{item.label}"' for item in associated[:limit])


def _catalog_fixed_ids(desire: DesireEngine | None) -> set[str] | None:
    if desire is None:
        return None
    try:
        return set(desire.catalog.fixed_desires)
    except Exception:
        return None


def _adjust_existing_level(
    levels: dict[str, float],
    name: str,
    fn: Callable[[float], float],
) -> None:
    if name not in levels:
        return
    levels[name] = round(min(1.0, max(0.0, fn(float(levels[name])))), 3)


def _sanitize_impulse_event(
    event: dict[str, object],
    *,
    visible_boosts: dict[str, float],
) -> dict[str, object]:
    if not event or not visible_boosts:
        return {"impulse_boost_triggered": False}

    filtered = dict(event)
    filtered_desires = [
        desire_name
        for desire_name in str(event.get("impulse_boosted_desires", "")).split(",")
        if desire_name and desire_name in visible_boosts
    ]
    if filtered_desires:
        filtered["impulse_boosted_desires"] = ",".join(filtered_desires)
        filtered["impulse_event_count"] = len(filtered_desires)
        filtered["impulse_boost_amounts"] = ",".join(
            f"{visible_boosts[desire_name]:.2f}" for desire_name in filtered_desires
        )

    boosted_desire = event.get("impulse_boosted_desire")
    if isinstance(boosted_desire, str) and boosted_desire in visible_boosts:
        filtered["impulse_boosted_desire"] = boosted_desire
        filtered["impulse_boost_amount"] = visible_boosts[boosted_desire]
        return filtered

    if filtered_desires:
        first_visible = filtered_desires[0]
        filtered["impulse_boosted_desire"] = first_visible
        filtered["impulse_boost_amount"] = visible_boosts[first_visible]
        return filtered

    return {"impulse_boost_triggered": False}


def _filter_desire_scaffold(scaffold: str, desire: DesireEngine | None) -> str:
    fixed_ids = _catalog_fixed_ids(desire)
    if fixed_ids is None or "predictability" in fixed_ids:
        return scaffold

    lines = scaffold.splitlines()
    filtered_lines = [
        line
        for line in lines
        if "consider satisfying predictability" not in line
        and "sense of predictability is being confirmed" not in line
    ]
    return "\n".join(filtered_lines)


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

    desire_summary = blend_desires(
        desire.compute_levels_with_modulation(),
        catalog=getattr(desire, "catalog", None),
    )
    relationship_line = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )

    notion_counts = Counter(
        notion.emotion_tone.value
        for notion in _list_notions_safe()
        if notion.confidence >= 0.5
    )
    notion_baseline = ""
    if notion_counts:
        rendered = ", ".join(
            f"{emotion}({count})"
            for emotion, count in sorted(
                notion_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:3]
        )
        notion_baseline = f"Notion baseline: {rendered}"

    parts = [intro_line]
    if notion_baseline:
        parts.append(notion_baseline)
    parts.extend([f"\nDesires: {desire_summary}", relationship_line])
    data = "\n".join(parts)

    return render_with_data(data, SCAFFOLD_WAKE_UP, config.companion_name)


async def _handle_feel_desires(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Check desire levels with scaffold."""
    created_emergent = desire.generate_emergent_desires(_list_notions_safe())
    expired_emergent = desire.expire_emergent_desires()
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
    impulse_event = get_impulse_manager().consume_event()
    impulse_boosts = get_impulse_manager().consume_boosts()
    visible_impulse_boosts = {
        name: amount for name, amount in impulse_boosts.items() if name in levels
    }
    for name, amount in visible_impulse_boosts.items():
        levels[name] = round(min(1.0, max(0.0, levels.get(name, 0.0) + amount)), 3)
    body_state = _call_get_body_state()
    phase = body_state.get("time_phase", "unknown")
    load = body_state.get("system_load", "unknown")

    if phase == "late_night":
        _adjust_existing_level(
            levels,
            "cognitive_coherence",
            lambda value: value + 0.1,
        )
        _adjust_existing_level(levels, "social_thirst", lambda value: value - 0.1)
    elif phase == "morning":
        _adjust_existing_level(levels, "curiosity", lambda value: value + 0.05)

    if load == "high":
        levels = {
            name: round(max(0.0, min(1.0, level * 0.9)), 3)
            for name, level in levels.items()
        }

    data = blend_desires(levels, catalog=getattr(desire, "catalog", None))
    update_tool_metadata(
        desire_levels=levels,
        emergent_desire_created=",".join(created_emergent) if created_emergent else None,
        emergent_desire_expired=",".join(expired_emergent) if expired_emergent else None,
        **_sanitize_impulse_event(
            impulse_event,
            visible_boosts=visible_impulse_boosts,
        ),
    )

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
    desire_summary = blend_desires(
        introspect_levels,
        catalog=getattr(desire, "catalog", None),
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

    notion_map = _notion_map()
    framework_lines: list[str] = []
    if notion_map:
        top_notions = sorted(
            (
                notion
                for notion in notion_map.values()
                if notion.confidence >= 0.7
            ),
            key=lambda notion: (-notion.confidence, -notion.reinforcement_count, notion.label),
        )[:5]
        if top_notions:
            framework_lines.append("Conceptual framework:")
            for notion in top_notions:
                framework_lines.append(
                    f'- "{notion.label}" confidence: {notion.confidence:.1f}'
                    f"{_format_associated_from_map(notion, notion_map, limit=2)}"
                )

    parts = [
        memory_section,
        f"\nDesires: {desire_summary}",
        self_summary,
        relationship_summary,
        "\n".join(framework_lines) if framework_lines else "",
        open_questions,
        trend,
    ]
    data = "\n".join(part for part in parts if part)

    return render_with_data(
        data,
        _filter_desire_scaffold(SCAFFOLD_INTROSPECT, desire),
        config.companion_name,
    )


async def _handle_consider_them(
    config: EgoConfig,
    memory: MemoryStore,
    args: dict[str, Any],
    desire: DesireEngine | None = None,
) -> str:
    """ToM: relationship summary + scaffold."""
    person = args.get("person", config.companion_name)
    store = _relationship_store(config)
    rel = store.get(person)
    (
        frequency,
        dominant_tone,
        inferred_preferred_topics,
        inferred_sensitive_topics,
    ) = await _summarize_conversation_tendency(memory, person)
    preferred_topics = _merge_topic_hints(
        rel.preferred_topics,
        inferred_preferred_topics,
    )
    sensitive_topics = _merge_topic_hints(
        rel.sensitive_topics,
        inferred_sensitive_topics,
    )

    relationship_summary = (
        f"{person}: trust={rel.trust_level:.2f}, "
        f"interactions={rel.total_interactions}, "
        f"shared_episodes={len(rel.shared_episode_ids)}"
    )
    if preferred_topics:
        relationship_summary += (
            f", preferred_topics={','.join(preferred_topics[:2])}"
        )
    if sensitive_topics:
        relationship_summary += (
            f", sensitive_topics={','.join(sensitive_topics[:2])}"
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
    person_notions = sorted(
        (
            notion for notion in _list_notions_safe() if notion.person_id == person
        ),
        key=lambda notion: (-notion.confidence, -notion.reinforcement_count, notion.label),
    )
    if person_notions:
        impression_lines = [f"Impressions of {person}:"]
        for notion in person_notions[:3]:
            impression_lines.append(
                f'  - "{notion.label}" confidence: {notion.confidence:.1f}'
            )
        data = f"{data}\n" + "\n".join(impression_lines)
    return render_with_data(
        data,
        _filter_desire_scaffold(SCAFFOLD_CONSIDER_THEM, desire),
        config.companion_name,
    )


def _handle_am_i_genuine() -> str:
    """Authenticity check with consistent data+scaffold format."""
    data = "Self-check triggered."
    convictions = sorted(
        (
            notion for notion in _list_notions_safe() if is_conviction(notion)
        ),
        key=lambda notion: (-notion.confidence, -notion.reinforcement_count, notion.label),
    )
    if convictions:
        lines = [data, "Your convictions:"]
        for notion in convictions[:5]:
            lines.append(f'- "{notion.label}"')
        data = "\n".join(lines)
    return compose_response(data, SCAFFOLD_AM_I_GENUINE)
