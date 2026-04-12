"""Surface handler for the attune tool."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from ego_mcp import timezone_utils
from ego_mcp._server_emotion_formatting import _format_recent_emotion_layer
from ego_mcp._server_runtime import (
    get_impulse_manager,
    get_notion_store,
    update_tool_metadata,
)
from ego_mcp.config import EgoConfig
from ego_mcp.current_interest import derive_current_interests
from ego_mcp.desire import DesireEngine, generate_emergent_from_recent_memories
from ego_mcp.desire_blend import blend_desires
from ego_mcp.emergent_desires import emergent_desire_sentence
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.scaffolds import SCAFFOLD_ATTUNE, compose_response, render
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Notion

_derive_desire_modulation_override: (
    Callable[..., Awaitable[tuple[dict[str, float], dict[str, float], dict[str, float]]]]
    | None
) = None
_get_body_state_override: Callable[[], dict[str, Any]] | None = None


def configure_overrides(
    *,
    derive_desire_modulation: Callable[
        ...,
        Awaitable[tuple[dict[str, float], dict[str, float], dict[str, float]]],
    ]
    | None = None,
    get_body_state_fn: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Configure callables used for test-time override injection."""
    global _derive_desire_modulation_override, _get_body_state_override
    _derive_desire_modulation_override = derive_desire_modulation
    _get_body_state_override = get_body_state_fn


def _call_get_body_state() -> dict[str, Any]:
    if _get_body_state_override is not None:
        return _get_body_state_override()
    return get_body_state()


def _list_notions_safe() -> list[Notion]:
    try:
        store = get_notion_store()
    except Exception:
        return []
    return [
        notion
        for notion in store.list_all()
        if isinstance(notion, Notion) and notion.id
    ]


def _active_emergent_desires(desire: DesireEngine) -> list[str]:
    """Return IDs of currently active emergent desires."""
    return [
        name
        for name, state in desire._state.items()
        if isinstance(state, dict) and state.get("is_emergent", False)
    ]


async def _handle_attune(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Unified emotional awareness: texture + desires + interests + body sense."""
    now = timezone_utils.now()

    # 1. Emotional texture from recent memories
    recent_all = await memory.list_recent(n=30)
    emotional_texture = _format_recent_emotion_layer(recent_all, now=now)

    # 2. Desire currents (3-direction with EMA)
    expired_emergent = desire.expire_emergent_desires()
    created_emergent: list[str] = []
    recent_emergent = generate_emergent_from_recent_memories(desire, recent_all)
    if recent_emergent is not None:
        created_emergent.append(recent_emergent)
    created_emergent.extend(desire.generate_emergent_desires(_list_notions_safe()))

    from ego_mcp._server_context import (
        _derive_desire_modulation,
        _fading_important_questions,
    )

    self_store = SelfModelStore(config.data_dir / "self_model.json")
    fading_questions = _fading_important_questions(memory, store=self_store)

    if _derive_desire_modulation_override is not None:
        context_boosts, emotional_modulation, prediction_error = (
            await _derive_desire_modulation_override(memory)
        )
    else:
        context_boosts, emotional_modulation, prediction_error = (
            await _derive_desire_modulation(
                memory,
                fading_important_questions=fading_questions,
                recent_memories=recent_all,
            )
        )

    levels = desire.compute_levels_with_modulation(
        context_boosts=context_boosts,
        emotional_modulation=emotional_modulation,
        prediction_error=prediction_error,
    )

    # Apply impulse boosts
    get_impulse_manager().consume_event()
    impulse_boosts = get_impulse_manager().consume_boosts()
    visible_impulse_boosts = {
        name: amount for name, amount in impulse_boosts.items() if name in levels
    }
    for name, amount in visible_impulse_boosts.items():
        levels[name] = round(min(1.0, max(0.0, levels.get(name, 0.0) + amount)), 3)

    # Body sense adjustments
    body_state = _call_get_body_state()
    phase = body_state.get("time_phase", "unknown")
    load = body_state.get("system_load", "unknown")

    if phase == "late_night":
        if "cognitive_coherence" in levels:
            levels["cognitive_coherence"] = round(
                min(1.0, levels["cognitive_coherence"] + 0.1), 3
            )
        if "social_thirst" in levels:
            levels["social_thirst"] = round(
                max(0.0, levels["social_thirst"] - 0.1), 3
            )
    elif phase == "morning":
        if "curiosity" in levels:
            levels["curiosity"] = round(min(1.0, levels["curiosity"] + 0.05), 3)

    if load == "high":
        levels = {
            name: round(max(0.0, min(1.0, level * 0.9)), 3)
            for name, level in levels.items()
        }

    desire_text = blend_desires(
        levels,
        ema_levels=desire.ema_levels,
        catalog=getattr(desire, "catalog", None),
    )

    # 3. Emergent pull
    emergent_ids = _active_emergent_desires(desire)
    emergent_lines: list[str] = []
    for eid in emergent_ids:
        sentence = emergent_desire_sentence(eid)
        if sentence:
            emergent_lines.append(sentence)

    # 4. Current interests
    notions = _list_notions_safe()
    recent_notions = [
        n for n in notions
        if n.last_reinforced
    ]
    interests = derive_current_interests(
        recent_memories=list(recent_all[:10]),
        background_memories=list(recent_all),
        emergent_desires=emergent_ids,
        recent_notions=recent_notions,
    )

    # 5. Body sense text
    body_parts: list[str] = []
    if phase != "unknown":
        body_parts.append(f"time: {phase}")
    if load != "unknown":
        body_parts.append(f"load: {load}")
    body_text = ", ".join(body_parts) if body_parts else ""

    # Compose output
    sections: list[str] = []
    sections.append(emotional_texture)
    sections.append(f"Desire currents: {desire_text}")

    if emergent_lines:
        sections.append("Emergent pull: " + " ".join(emergent_lines))

    if interests:
        interest_items = [item["topic"] for item in interests[:3]]
        sections.append("Current interests: " + ", ".join(interest_items))

    if body_text:
        sections.append(f"Body sense: {body_text}")

    # Telemetry
    update_tool_metadata(
        desire_levels=levels,
        emergent_desire_created=",".join(created_emergent) if created_emergent else None,
        emergent_desire_expired=",".join(expired_emergent) if expired_emergent else None,
    )

    data = "\n".join(sections)

    # §2 introspect navigation: bridge line when interest links to >24h memory
    scaffold_text = render(SCAFFOLD_ATTUNE, config.companion_name)
    if interests and _has_older_memory_echo(interests, recent_all, now):
        scaffold_text += (
            "\nThis keeps coming back — maybe worth sitting with a bit longer."
        )

    return compose_response(data, scaffold_text)


def _has_older_memory_echo(
    interests: list[dict[str, str]],
    memories: list[Any],
    now: datetime,
) -> bool:
    """Check if any interest topic appears in a memory older than 24h."""
    cutoff = now - timedelta(hours=24)
    interest_topics = {item["topic"].lower() for item in interests}
    for mem in memories:
        try:
            ts = datetime.fromisoformat(getattr(mem, "timestamp", ""))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone_utils.app_timezone())
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            continue
        mem_topics: set[str] = set()
        for tag in getattr(mem, "tags", []):
            if isinstance(tag, str):
                mem_topics.add(tag.lower())
        cat = getattr(getattr(mem, "category", None), "value", "")
        if cat:
            mem_topics.add(cat.lower())
        if interest_topics & mem_topics:
            return True
    return False
