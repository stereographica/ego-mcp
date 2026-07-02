"""Surface handler for the attune tool."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from inspect import isawaitable
from typing import Any, Awaitable, Callable

from ego_mcp import timezone_utils
from ego_mcp._server_emotion_formatting import (
    _format_recent_emotion_layer,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import (
    get_impulse_manager,
    get_notion_store,
    update_tool_metadata,
)
from ego_mcp._server_surface_person import (
    _format_active_persons,
    _get_active_person_ids,
)
from ego_mcp.anticipation import (
    format_approaching_anticipation,
    format_arrived_anticipation,
    pick_anticipation,
    pick_arrived_anticipation,
)
from ego_mcp.config import EgoConfig
from ego_mcp.current_interest import derive_current_interests
from ego_mcp.desire import (
    CURIOSITY_TONUS_BOOST,
    DesireEngine,
    detect_curious_tonus,
    generate_emergent_from_recent_memories,
)
from ego_mcp.desire_blend import blend_desires
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.scaffolds import SCAFFOLD_ATTUNE, compose_response, render
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Memory, Notion

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


async def _list_anticipations_safe(memory: MemoryStore) -> list[Memory]:
    method = getattr(memory, "list_anticipations", None)
    if not callable(method):
        return []
    try:
        result = method()
        if isawaitable(result):
            result = await result
    except Exception:
        return []
    return result if isinstance(result, list) else []


async def _mark_anticipation_surfaced_safe(
    memory: MemoryStore,
    memory_id: str,
) -> None:
    method = getattr(memory, "mark_anticipation_surfaced", None)
    if not callable(method):
        return
    try:
        result = method(memory_id)
        if isawaitable(result):
            await result
    except Exception:
        return


async def _anticipation_surface_line(
    memory: MemoryStore,
    now: datetime,
) -> str:
    anticipations = await _list_anticipations_safe(memory)
    if not anticipations:
        return ""

    arrived = pick_arrived_anticipation(anticipations, now)
    if arrived is not None:
        await _mark_anticipation_surfaced_safe(memory, arrived.id)
        if not arrived.is_private:
            update_tool_metadata(anticipation_arrived=arrived.id)
        return format_arrived_anticipation(arrived, _truncate_for_quote)

    approaching = pick_anticipation(anticipations, now, random)
    if approaching is None:
        return ""
    if not approaching.is_private:
        update_tool_metadata(anticipation_presented=approaching.id)
    return format_approaching_anticipation(approaching, now, _truncate_for_quote)


async def _handle_attune(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any], desire: DesireEngine
) -> str:
    """Unified emotional awareness: texture + desires + interests + body sense."""
    now = timezone_utils.now()

    # Resolve target person for this attune call
    from ego_mcp._server_context import _relationship_store
    _ws = _relationship_store(config)
    person = args.get("person", config.companion_name)
    resolved = _ws.resolve_person(person)
    if resolved is not None:
        person = resolved

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

    curiosity_tonus_applied = False
    if detect_curious_tonus(recent_all) and "curiosity" in levels:
        levels["curiosity"] = round(
            min(1.0, levels["curiosity"] + CURIOSITY_TONUS_BOOST), 3
        )
        curiosity_tonus_applied = True

    desire_text = blend_desires(
        levels,
        ema_levels=desire.ema_levels,
        catalog=getattr(desire, "catalog", None),
        emergent_directions=desire.emergent_directions(),
    )

    # 3. Current interests
    notions = _list_notions_safe()
    recent_notions = [
        n for n in notions
        if n.last_reinforced
    ]
    interests = derive_current_interests(
        recent_memories=list(recent_all[:10]),
        background_memories=list(recent_all),
        recent_notions=recent_notions,
    )

    # 4. Body sense text
    body_text = f"time: {phase}" if phase != "unknown" else ""

    # Compose output
    sections: list[str] = []
    sections.append(emotional_texture)
    anticipation_line = await _anticipation_surface_line(memory, now)
    if anticipation_line:
        sections.append(anticipation_line)
    sections.append(f"Desire currents: {desire_text}")

    if interests:
        interest_items = [item["topic"] for item in interests[:3]]
        sections.append("Current interests: " + ", ".join(interest_items))

    if body_text:
        sections.append(f"Body sense: {body_text}")

    # Active persons
    _active_person_ids: list[str] = []
    try:
        _ws = _relationship_store(config)
        active_persons = _format_active_persons(_ws, max_persons=2)
        if active_persons:
            sections.append(active_persons)
        _active_person_ids = _get_active_person_ids(_ws, max_persons=2)
    except Exception:
        pass

    # Insert targeted person snapshot if different from companion
    if person != config.companion_name:
        try:
            rel = _ws.get(person)
            if rel and rel.name:
                sections.insert(
                    len(sections) - 1 if active_persons else len(sections),
                    f"Regarding {rel.name}: trust {rel.trust_level:.1f}, "
                    f"{rel.total_interactions} interactions.",
                )
        except Exception:
            pass

    # Telemetry
    update_tool_metadata(
        desire_levels=levels,
        emergent_desire_created=",".join(created_emergent) if created_emergent else None,
        emergent_desire_expired=",".join(expired_emergent) if expired_emergent else None,
        curiosity_tonus_boost=(
            f"{CURIOSITY_TONUS_BOOST:.2f}" if curiosity_tonus_applied else None
        ),
        attune_person=person,
        active_person_ids=json.dumps(_active_person_ids) if _active_person_ids else None,
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
