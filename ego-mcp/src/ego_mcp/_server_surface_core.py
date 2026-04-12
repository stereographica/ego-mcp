"""Surface handlers for wake/introspection/consider tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from ego_mcp import timezone_utils
from ego_mcp._server_context import (
    _derive_desire_modulation,
    _fading_important_questions,
    _find_related_forgotten_questions,
    _relationship_snapshot,
    _relationship_store,
    _summarize_conversation_tendency,
)
from ego_mcp._server_emotion_formatting import (
    _format_month_emotion_layer,
    _format_recent_emotion_layer,
    _format_week_emotion_layer,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import (
    get_episodes,
    get_impulse_manager,
    get_notion_store,
    get_workspace_sync,
)
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.desire_blend import blend_desires
from ego_mcp.embers import generate_embers
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import is_conviction
from ego_mcp.proust import find_proust_memory
from ego_mcp.scaffolds import (
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_PAUSE,
    SCAFFOLD_WAKE_UP,
    compose_response,
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
    """Session start: emotional texture + embers + Proust + introspection + desires + relationship."""
    from ego_mcp import timezone_utils
    from ego_mcp._server_context import _fading_important_questions
    from ego_mcp.emergent_desires import emergent_desire_sentence

    now = timezone_utils.now()
    recent_all = await memory.list_recent(n=30)
    parts: list[str] = []
    expire_emergent = getattr(desire, "expire_emergent_desires", None)
    if callable(expire_emergent):
        expire_emergent()

    # 1. Emotional texture of last session
    if recent_all:
        emotion_layer = _format_recent_emotion_layer(recent_all, now)
        parts.append(emotion_layer)

    # 2. Embers
    active_emergent = [
        name
        for name, state in desire._state.items()
        if isinstance(state, dict) and state.get("is_emergent", False)
    ]
    weakened_notions = [
        n for n in _list_notions_safe() if n.confidence < 0.4
    ]
    try:
        unresolved_qs = _fading_important_questions(memory)
    except Exception:
        unresolved_qs = []
    ember_texts = generate_embers(
        recent_all[:5], unresolved_qs, active_emergent, weakened_notions
    )
    if ember_texts:
        parts.append("Embers:\n" + "\n".join(f"  {e}" for e in ember_texts))

    # 3. Involuntary recall — Proust
    if recent_all:
        seed = recent_all[0].content
        proust_mem = await find_proust_memory(seed, memory)
        if proust_mem is not None:
            try:
                get_impulse_manager().register_proust_event(proust_mem)
            except Exception:
                pass
            parts.append(
                f'Involuntary recall:\n  "{_truncate_for_quote(proust_mem.content, 120)}"'
            )

    # 4. Last introspection (shortened)
    sync = get_workspace_sync()
    latest_text: str | None = None
    latest_since: str | None = None
    if sync is not None:
        latest_text, latest_since = sync.read_latest_monologue()

    if latest_text:
        since = latest_since or "workspace-sync"
        parts.append(
            f'Last introspection ({since}):\n"{_truncate_for_quote(latest_text)}"'
        )
    else:
        recent_introspections = await memory.list_recent(
            n=1, category_filter="introspection"
        )
        if recent_introspections:
            m = recent_introspections[0]
            since = m.timestamp[:16] if len(m.timestamp) >= 16 else m.timestamp
            parts.append(
                f'Last introspection ({since}):\n"{_truncate_for_quote(m.content)}"'
            )
        else:
            parts.append("No introspection yet.")

    # 5. Desire currents (3-direction)
    levels = desire.compute_levels_with_modulation()
    desire_summary = blend_desires(
        levels,
        ema_levels=desire.ema_levels,
        catalog=getattr(desire, "catalog", None),
    )
    parts.append(f"Desire currents: {desire_summary}")

    # 6. Emergent pull
    for desire_id in active_emergent:
        sentence = emergent_desire_sentence(desire_id)
        if sentence:
            parts.append(f"Emergent pull: {sentence}")
            break

    # 7. Relationship note
    relationship_line = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )
    parts.append(relationship_line)

    data = "\n\n".join(parts)
    return render_with_data(data, SCAFFOLD_WAKE_UP, config.companion_name)


async def _handle_introspect(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Introspection materials: week/month layers + notions + questions + episodes + desire trend."""
    recent_all = await memory.list_recent(n=30)
    now = timezone_utils.now()

    # §10.1 emotional layers — week + month only (3-day is in attune)
    week_layer = _format_week_emotion_layer(recent_all, now)
    month_layer = _format_month_emotion_layer(recent_all, now)
    emotion_section = f"{week_layer}\n{month_layer}"

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
        ema_levels=desire.ema_levels,
        catalog=getattr(desire, "catalog", None),
    )
    coherence_level = float(introspect_levels.get("cognitive_coherence", 0.0))

    # §10.1 notion landscape
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
            framework_lines.append("Notion landscape:")
            for notion in top_notions:
                framework_lines.append(
                    f'- "{notion.label}" confidence: {notion.confidence:.1f}'
                    f"{_format_associated_from_map(notion, notion_map, limit=2)}"
                )

    # §10.1 unresolved questions
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

    recent = recent_all[:3]
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

    # §10.1 recent episodes (past 2 weeks)
    episode_lines: list[str] = []
    try:
        episode_store = get_episodes()
        all_episodes = await episode_store.list_episodes(limit=10)
        from datetime import timedelta

        cutoff = now - timedelta(days=14)
        recent_episodes = [
            ep for ep in all_episodes
            if _parse_episode_time(ep.start_time) is not None
            and _parse_episode_time(ep.start_time) >= cutoff  # type: ignore[operator]
        ]
        if recent_episodes:
            episode_lines.append("Recent episodes:")
            for ep in recent_episodes[:3]:
                episode_lines.append(
                    f"- [{ep.id}] {ep.summary[:80]}"
                    f" ({len(ep.memory_ids)} memories)"
                )
    except Exception:
        pass

    # §10.1 self model delta
    self_model = self_store.get()
    goals = (
        ", ".join(self_model.current_goals[:2]) if self_model.current_goals else "none"
    )
    self_summary = (
        f"Self model: confidence={self_model.confidence_calibration:.2f}, goals={goals}"
    )
    if self_model.last_updated:
        self_summary += f", last_updated={self_model.last_updated[:10]}"

    # §10.1 desire trend — EMA-based change for 1-2 desires
    desire_trend_lines: list[str] = []
    ema = desire.ema_levels
    if ema and introspect_levels:
        deltas = [
            (name, float(introspect_levels.get(name, 0.0)) - ema_val)
            for name, ema_val in ema.items()
        ]
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        notable = [(name, d) for name, d in deltas[:2] if abs(d) > 0.1]
        if notable:
            desire_trend_lines.append("Desire trend:")
            for name, delta in notable:
                direction = "rising" if delta > 0 else "settling"
                desire_trend_lines.append(
                    f"- {name}: {direction} ({delta:+.2f} from baseline)"
                )

    relationship_summary = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )

    parts = [
        emotion_section,
        "\n".join(framework_lines) if framework_lines else "",
        open_questions,
        "\n".join(episode_lines) if episode_lines else "",
        self_summary,
        "\n".join(desire_trend_lines) if desire_trend_lines else "",
        f"\nDesire currents: {desire_summary}",
        relationship_summary,
    ]
    data = "\n".join(part for part in parts if part)

    return render_with_data(
        data,
        _filter_desire_scaffold(SCAFFOLD_INTROSPECT, desire),
        config.companion_name,
    )


def _parse_episode_time(timestamp: str) -> datetime | None:
    """Parse episode timestamp string to datetime."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone_utils.app_timezone())
    return parsed


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


def _handle_pause() -> str:
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
    return compose_response(data, SCAFFOLD_PAUSE)
