"""Surface handlers for wake/introspection/consider tools."""

from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Any, Awaitable, Callable

from ego_mcp import timezone_utils
from ego_mcp._server_context import (
    _derive_desire_modulation,
    _derived_reader,
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
    _tail_quote_for_introspection,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import (
    get_episodes,
    get_impulse_manager,
    get_notion_store,
    get_workspace_sync,
    update_tool_metadata,
)
from ego_mcp._server_surface_person import (
    _format_active_persons,
    _get_active_person_ids,
)
from ego_mcp.absence import absence_band, approx_duration_words
from ego_mcp.anticipation import (
    format_approaching_anticipation,
    format_arrived_anticipation,
    pick_anticipation,
    pick_arrived_anticipation,
)
from ego_mcp.config import EgoConfig
from ego_mcp.derived import stagnation as stagnation_lens
from ego_mcp.derived.affect import (
    DIRECTION_BRIGHTER,
    DIRECTION_DARKER,
    DIRECTION_LIVELIER,
    DIRECTION_QUIETER,
)
from ego_mcp.derived.affect import LENS_NAME as AFFECT_LENS
from ego_mcp.derived.chapters import LENS_NAME as CHAPTERS_LENS
from ego_mcp.derived.dream import DREAM_PRESENT_PROBABILITY
from ego_mcp.derived.dream import LENS_NAME as DREAM_LENS
from ego_mcp.derived.drift import LENS_NAME as DRIFT_LENS
from ego_mcp.derived.holes import HOLES_KIND_ORDER
from ego_mcp.derived.holes import LENS_NAME as HOLES_LENS
from ego_mcp.derived.recurrence import LENS_NAME as RECURRENCE_LENS
from ego_mcp.derived.recurrence import RECURRENCE_PRESENT_PROBABILITY
from ego_mcp.derived.words import count_words, span_words
from ego_mcp.desire import DesireEngine
from ego_mcp.desire_blend import blend_desires
from ego_mcp.embers import generate_embers
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import (
    analyze_notion_network,
    format_network_analysis,
    is_conviction,
)
from ego_mcp.proust import find_proust_memory
from ego_mcp.relationship_wording import episode_words, history_words, trust_words
from ego_mcp.ripening import (
    build_ripened_question_block,
    format_shared_question_line,
    person_display_name,
    pick_ripened_question,
    shared_open_questions_for_person,
)
from ego_mcp.scaffolds import (
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_INTROSPECT_NETWORK,
    SCAFFOLD_PAUSE,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render_with_data,
)
from ego_mcp.self_model import QUESTION_ACTIVE_MIN_SALIENCE, SelfModelStore
from ego_mcp.types import Memory, Notion

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


def _last_interaction_words(timestamp: str, now: datetime) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return ""
    parsed = timezone_utils.localize(parsed)
    elapsed_days = max(0.0, (now - parsed).total_seconds() / 86400.0)
    return f"{approx_duration_words(elapsed_days)} ago"


def _parse_reunion_noted_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def _pending_reunion_note(store: Any) -> tuple[str, dict[str, Any]] | None:
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    raw_data = getattr(store, "_data", {})
    if not isinstance(raw_data, dict):
        return None
    for person_id, raw in raw_data.items():
        if not isinstance(person_id, str) or not isinstance(raw, dict):
            continue
        note = raw.get("reunion_note")
        if not isinstance(note, dict) or note.get("wake_up_shown") is True:
            continue
        noted_at = _parse_reunion_noted_at(note.get("noted_at"))
        if noted_at is None:
            continue
        candidates.append((noted_at, person_id, note))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, person_id, note = candidates[0]
    return person_id, note


def _reunion_gap_days(note: dict[str, Any]) -> float:
    try:
        return max(0.0, float(note.get("gap_days", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


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


_logger = logging.getLogger(__name__)

_CONFIDENCE_DROP_THRESHOLD = 0.1


def _detect_weakened_notions(
    current_notions: list[Notion],
    snapshot_path: Path,
) -> list[Notion]:
    """Return notions whose confidence dropped >= threshold since last snapshot.

    Saves the current confidence values for next comparison.
    """
    previous: dict[str, float] = {}
    if snapshot_path.exists():
        try:
            previous = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if not isinstance(previous, dict):
        previous = {}

    weakened: list[Notion] = []
    for n in current_notions:
        prev_conf = previous.get(n.id)
        if prev_conf is not None and prev_conf - n.confidence >= _CONFIDENCE_DROP_THRESHOLD:
            weakened.append(n)

    current_snapshot = {n.id: n.confidence for n in current_notions}
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(current_snapshot), encoding="utf-8"
        )
    except OSError:
        _logger.debug("Failed to save notion confidence snapshot", exc_info=True)

    return weakened


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


def _format_question_line(
    item: dict[str, Any],
    relationship_store: Any | None,
) -> str:
    person_id = item.get("person_id")
    if isinstance(person_id, str) and person_id and relationship_store is not None:
        name = person_display_name(relationship_store, person_id)
        return (
            f"- [{item['id']}] {item['question']} "
            f"(importance: {item['importance']}, with {name})"
        )
    return f"- [{item['id']}] {item['question']} (importance: {item['importance']})"


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


async def _list_anticipations_safe(memory: MemoryStore) -> list[Memory]:
    method = getattr(memory, "list_anticipations", None)
    if not callable(method):
        return []
    try:
        result = method()
        if isawaitable(result):
            result = await result
    except Exception:
        _logger.debug("Skipped anticipation scan", exc_info=True)
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
        _logger.debug("Skipped anticipation surfaced update", exc_info=True)


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


# --- derived layer presentation (D0 S8 calling convention) -------------------
#
# Every helper below owns its own ``try/except Exception``: a missing, stale or
# malformed derived file must leave the response exactly as it was.

#: D4 edge cases: with a daily batch the key changes daily, so the same notion
#: is not re-asked about for this many days after a replacement.
DRIFT_PRESENT_COOLDOWN_DAYS = 7.0
#: D4 S2: at most this many landscape lines are replaced per introspect call.
DRIFT_MAX_REPLACEMENTS = 2
#: D3 D2: the "Unconnected density" section is at most this many lines.
HOLES_MAX_LINES = 4
#: D6 D3 / S3: appended to the introspect scaffold while 6b is enabled.
STAGNATION_BRIDGE_LINE = (
    "Some of this might be worth bringing to {companion_name} "
    "rather than turning over alone."
)

_SECONDS_PER_DAY = 86400.0


async def _memory_by_id(memory: MemoryStore, memory_id: Any) -> Memory | None:
    """Fetch a memory referenced by a derived item, or ``None`` if it is gone."""
    if not isinstance(memory_id, str) or not memory_id:
        return None
    return await memory.get_by_id(memory_id)


def _elapsed_days(marked: datetime, now: datetime) -> float:
    """Days between two moments, both pulled into the app timezone."""
    return (
        timezone_utils.localize(now) - timezone_utils.localize(marked)
    ).total_seconds() / _SECONDS_PER_DAY


async def _recurrence_surface_line(
    config: EgoConfig,
    memory: MemoryStore,
    now: datetime,
    rng: Any,
) -> str | None:
    """D1 S2: one calendar echo per day, right after the anticipation line."""
    try:
        reader = _derived_reader(config)
        today = now.date().isoformat()
        items = [
            item
            for item in reader.items(RECURRENCE_LENS, now=now)
            if item.get("on_date") == today
        ]
        if not items:
            return None
        # At most one per day: a second wake_up on the same day stays quiet even
        # when another candidate is still unsurfaced.
        if reader.has_surfaced_with_prefix(
            f"{RECURRENCE_LENS}:", suffix=f":{today}"
        ):
            return None
        if rng.random() >= RECURRENCE_PRESENT_PROBABILITY:
            return None
        item = items[0]
        recalled = await _memory_by_id(memory, item.get("memory_id"))
        # The mark goes down either way: a deleted target ends the day quietly
        # rather than falling through to the next candidate.
        reader.mark_surfaced(str(item["key"]), now=now)
        if recalled is None:
            return None
        span = span_words(str(item.get("period", "year")), int(item.get("span", 1)))
        update_tool_metadata(
            derived_presented=item["key"],
            recurrence_presented=recalled.id,
            recurrence_period=item.get("period"),
        )
        return (
            f"Around this time {span}: "
            f'"{_truncate_for_quote(recalled.content, 120)}"'
        )
    except Exception:
        _logger.debug("Skipped recurrence line", exc_info=True)
        return None


async def _dream_surface_block(
    config: EgoConfig,
    memory: MemoryStore,
    now: datetime,
    rng: Any,
) -> str | None:
    """D2 S2: two distant memories held side by side, no thread named."""
    try:
        reader = _derived_reader(config)
        items = reader.items(DREAM_LENS, now=now)
        # Candidates first, dice second — the same order proust.py uses.
        if not items or rng.random() >= DREAM_PRESENT_PROBABILITY:
            return None
        item = items[0]
        memory_ids = item.get("memory_ids")
        if not isinstance(memory_ids, list) or len(memory_ids) < 2:
            return None
        first = await _memory_by_id(memory, memory_ids[0])
        second = await _memory_by_id(memory, memory_ids[1])
        # Marked even when one side is gone: the dream is spent either way.
        reader.mark_surfaced(str(item["key"]), now=now)
        if first is None or second is None:
            return None
        threads = item.get("threads")
        update_tool_metadata(
            derived_presented=item["key"],
            dream_presented=item["key"],
            dream_thread=(
                ",".join(str(thread) for thread in threads)
                if isinstance(threads, list)
                else ""
            ),
        )
        return (
            "A strange dream:\n"
            f'  "{_truncate_for_quote(first.content, 80)}"\n'
            f'  "{_truncate_for_quote(second.content, 80)}"\n'
            "They were side by side. Nothing says why."
        )
    except Exception:
        _logger.debug("Skipped dream block", exc_info=True)
        return None


async def _holes_line(
    config: EgoConfig,
    memory: MemoryStore,
    notion_store: Any,
    kind: str,
    item: dict[str, Any],
) -> str | None:
    """D3 D2: one line for one hole, or ``None`` when its target is gone."""
    if kind == "person_unlinked":
        person_id = item.get("person_id")
        if not isinstance(person_id, str) or not person_id:
            return None
        name = person_display_name(_relationship_store(config), person_id)
        return (
            f"  {name} appears in many memories that never connected to anything."
        )
    if kind == "worn_isolated":
        worn = await _memory_by_id(memory, item.get("memory_id"))
        if worn is None:
            return None
        return (
            f'  "{_truncate_for_quote(worn.content, 60)}"'
            " — returned to often, linked to nothing."
        )
    if kind == "tag_without_notion":
        tag = item.get("tag")
        if not isinstance(tag, str) or not tag:
            return None
        return f'  "{tag}" runs through many memories but no notion holds it.'
    if kind == "straddling":
        straddler = await _memory_by_id(memory, item.get("memory_id"))
        if straddler is None:
            return None
        notion_ids = item.get("notion_ids")
        if not isinstance(notion_ids, list) or len(notion_ids) < 2:
            return None
        left = notion_store.get_by_id(str(notion_ids[0]))
        right = notion_store.get_by_id(str(notion_ids[1]))
        if left is None or right is None:
            return None
        return (
            f'  "{_truncate_for_quote(straddler.content, 60)}"'
            f' stands between "{left.label}" and "{right.label}".'
        )
    return None


async def _format_holes_section(
    config: EgoConfig,
    memory: MemoryStore,
    notion_store: Any,
    now: datetime,
) -> str:
    """D3 S2: the "Unconnected density" section, one line per kind."""
    try:
        items = _derived_reader(config).items(
            HOLES_LENS, now=now, exclude_surfaced=False
        )
        if not items:
            return ""
        lines: list[str] = []
        shown_kinds: list[str] = []
        for kind in HOLES_KIND_ORDER:
            if len(lines) >= HOLES_MAX_LINES:
                break
            item = next(
                (candidate for candidate in items if candidate.get("kind") == kind),
                None,
            )
            if item is None:
                continue
            # A deleted target skips the kind; it never falls through to the
            # second item of the same kind (D3 edge cases).
            line = await _holes_line(config, memory, notion_store, kind, item)
            if line is None:
                continue
            lines.append(line)
            shown_kinds.append(kind)
        if not lines:
            return ""
        update_tool_metadata(holes_presented=json.dumps(shown_kinds))
        return "\nUnconnected density:\n" + "\n".join(lines)
    except Exception:
        _logger.debug("Skipped unconnected density section", exc_info=True)
        return ""


def _drift_replacement_lines(
    config: EgoConfig,
    notions: list[Notion],
    now: datetime,
) -> dict[str, str]:
    """D4 S2: notion id -> the question line that replaces its landscape line."""
    try:
        reader = _derived_reader(config)
        by_notion: dict[str, dict[str, Any]] = {}
        for item in reader.items(DRIFT_LENS, now=now):
            notion_id = item.get("notion_id")
            if isinstance(notion_id, str) and notion_id and notion_id not in by_notion:
                by_notion[notion_id] = item
        if not by_notion:
            return {}

        chosen: list[tuple[Notion, dict[str, Any]]] = []
        # drift first, then stale_conviction; landscape order inside each kind.
        for kind in ("drift", "stale_conviction"):
            for notion in notions:
                if len(chosen) >= DRIFT_MAX_REPLACEMENTS:
                    break
                drift_item = by_notion.get(notion.id)
                if drift_item is None or drift_item.get("kind") != kind:
                    continue
                last = reader.last_surfaced_at(f"{DRIFT_LENS}:{notion.id}:")
                if (
                    last is not None
                    and _elapsed_days(last, now) < DRIFT_PRESENT_COOLDOWN_DAYS
                ):
                    continue
                chosen.append((notion, drift_item))
            if len(chosen) >= DRIFT_MAX_REPLACEMENTS:
                break
        if not chosen:
            return {}

        lines: dict[str, str] = {}
        for notion, item in chosen:
            tail = (
                "is this still true? Its recent ground has shifted."
                if item.get("kind") == "drift"
                else "unrevisited for a while. Still true?"
            )
            lines[notion.id] = (
                f'- "{notion.label}" confidence: {notion.confidence:.1f} — {tail}'
            )
            reader.mark_surfaced(str(item["key"]), now=now)
        update_tool_metadata(
            drift_presented=json.dumps([notion.id for notion, _ in chosen]),
            drift_kinds=json.dumps([str(item.get("kind")) for _, item in chosen]),
        )
        return lines
    except Exception:
        _logger.debug("Skipped drift replacements", exc_info=True)
        return {}


def _boundary_age_days(boundary_week: Any, now: datetime) -> float | None:
    """Days since a chapter boundary week, or ``None`` if it cannot be read."""
    if not isinstance(boundary_week, str) or not boundary_week:
        return None
    try:
        week_start = date.fromisoformat(boundary_week)
    except ValueError:
        return None
    return max(0.0, float((now.date() - week_start).days))


async def _chapter_lines(
    config: EgoConfig,
    memory: MemoryStore,
    now: datetime,
) -> list[str]:
    """D5 S2: a fresh boundary once, otherwise the one-line count."""
    try:
        reader = _derived_reader(config)
        all_items = reader.items(CHAPTERS_LENS, now=now, exclude_surfaced=False)
        if not all_items:
            return []
        fresh = [
            item for item in all_items if not reader.is_surfaced(str(item["key"]))
        ]
        if fresh:
            # Items come newest first, so the head is the newest unsurfaced one.
            item = fresh[0]
            before = await _memory_by_id(memory, item.get("before_memory_id"))
            after = await _memory_by_id(memory, item.get("after_memory_id"))
            reader.mark_surfaced(str(item["key"]), now=now)
            if before is None or after is None:
                return []
            age_days = _boundary_age_days(item.get("boundary_week"), now)
            if age_days is None:
                return []
            update_tool_metadata(
                derived_presented=item["key"],
                chapter_presented=item["key"],
                chapter_count=len(all_items),
            )
            return [
                "Chapters (unnamed):",
                f"  A turn around {approx_duration_words(age_days)} ago — "
                f'from "{_truncate_for_quote(before.content, 60)}"'
                f' toward "{_truncate_for_quote(after.content, 60)}".',
                "  If it has a name, that's yours to give.",
            ]
        latest_age = _boundary_age_days(all_items[0].get("boundary_week"), now)
        if latest_age is None:
            return []
        update_tool_metadata(chapter_count=len(all_items))
        return [
            f"Chapters (unnamed): {count_words(len(all_items))} turns so far, "
            f"the last one {approx_duration_words(latest_age)} ago."
        ]
    except Exception:
        _logger.debug("Skipped chapter lines", exc_info=True)
        return []


def _affect_trajectory_line(
    config: EgoConfig,
    person_id: str,
    now: datetime,
) -> str | None:
    """P2 S2: one line for how the shared moments have moved, if they moved."""
    try:
        items = _derived_reader(config).items(
            AFFECT_LENS, now=now, exclude_surfaced=False
        )
        item = next(
            (
                candidate
                for candidate in items
                if candidate.get("person_id") == person_id
            ),
            None,
        )
        if item is None:
            return None
        valence = item.get("valence_direction")
        arousal = item.get("arousal_direction")
        if valence in (DIRECTION_BRIGHTER, DIRECTION_DARKER):
            line = (
                "The shared moments of the last while lean "
                f"{valence} than the ones before."
            )
        elif arousal in (DIRECTION_LIVELIER, DIRECTION_QUIETER):
            line = (
                f"The shared moments of the last while run {arousal} than before."
            )
        else:
            # Both steady: saying "unchanged" every time is the script (P2 D2).
            return None
        update_tool_metadata(
            affect_valence_direction=valence,
            affect_arousal_direction=arousal,
            affect_dv=item.get("dv"),
            affect_da=item.get("da"),
        )
        return line
    except Exception:
        _logger.debug("Skipped affect trajectory line", exc_info=True)
        return None


def _stagnation_bridge_line(config: EgoConfig, now: datetime) -> str | None:
    """D6 S3: point the introspect scaffold back at dialogue while 6b is on."""
    # Read through the module so flipping the flag in derived/stagnation.py is
    # the single line change D6 D3 describes.
    if not stagnation_lens.STAGNATION_MODULATION_ENABLED:
        return None
    try:
        items = _derived_reader(config).items(
            stagnation_lens.LENS_NAME, now=now, exclude_surfaced=False
        )
        if not items:
            return None
        if items[0].get("band") not in (
            stagnation_lens.STAGNATION_BAND_CIRCLING,
            stagnation_lens.STAGNATION_BAND_STUCK,
        ):
            return None
        update_tool_metadata(stagnation_bridge_shown=True)
        return STAGNATION_BRIDGE_LINE
    except Exception:
        _logger.debug("Skipped stagnation bridge line", exc_info=True)
        return None


async def _handle_wake_up(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Session start: emotional texture + embers + Proust + introspection + desires + relationship."""
    from ego_mcp import timezone_utils

    now = timezone_utils.now()
    recent_all = await memory.list_recent(n=30)
    parts: list[str] = []
    desire.expire_emergent_desires()

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
    all_notions = _list_notions_safe()
    snapshot_path = config.data_dir / "notion_confidence_snapshot.json"
    weakened_notions = _detect_weakened_notions(all_notions, snapshot_path)
    ember_texts = generate_embers(
        recent_all[:5], active_emergent, weakened_notions
    )
    if ember_texts:
        parts.append("Embers:\n" + "\n".join(f"  {e}" for e in ember_texts))
    if weakened_notions:
        notion_lines = []
        for wn in weakened_notions[:5]:
            meta_parts = ", ".join(
                f"{k}:{v['type']}" for k, v in wn.meta_fields.items()
            )
            meta_str = f" meta=[{meta_parts}]" if meta_parts else ""
            notion_lines.append(
                f'  "{wn.label}" conf={wn.confidence:.2f}{meta_str}'
            )
        parts.append("Weakened notions:\n" + "\n".join(notion_lines))

    # 3. Involuntary recall — Proust
    proust_mem: Memory | None = None
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

    # 3b. The dream — never alongside Proust (two involuntary recalls is too
    # many for one wake_up; D2 D2).
    if proust_mem is None:
        dream_block = await _dream_surface_block(config, memory, now, random)
        if dream_block:
            parts.append(dream_block)

    # 4. Last introspection (shortened)
    sync = get_workspace_sync()
    latest_text: str | None = None
    latest_since: str | None = None
    if sync is not None:
        latest_text, latest_since = sync.read_latest_monologue()

    if latest_text:
        since = latest_since or "workspace-sync"
        parts.append(
            f'Last introspection ({since}):\n"{_tail_quote_for_introspection(latest_text)}"'
        )
    else:
        recent_introspections = await memory.list_recent(
            n=1, category_filter="introspection"
        )
        if recent_introspections:
            m = recent_introspections[0]
            since = m.timestamp[:16] if len(m.timestamp) >= 16 else m.timestamp
            parts.append(
                f'Last introspection ({since}):\n"{_tail_quote_for_introspection(m.content)}"'
            )
        else:
            parts.append("No introspection yet.")

    self_store = SelfModelStore(config.data_dir / "self_model.json")
    entries = self_store.get_unresolved_questions_with_salience()
    ripened_block = ""
    ripened = pick_ripened_question(entries)
    if ripened is not None:
        try:
            ripened_block = await build_ripened_question_block(
                self_store,
                memory,
                ripened,
                relationship_store=_relationship_store(config),
                notion_store=get_notion_store(),
                now=now,
            ) or ""
        except Exception:
            ripened_block = ""
    if ripened_block:
        parts.append(f"Open edges:\n{ripened_block}")
    else:
        active = [
            e
            for e in self_store.get_unresolved_questions_with_salience()
            if float(e.get("salience", 0.0)) > QUESTION_ACTIVE_MIN_SALIENCE
        ]
        if active:
            top = max(active, key=lambda e: float(e.get("salience", 0.0)))
            parts.append(
                f"Open edges:\n  [{top['id']}] {top['question']} "
                f"(importance: {top['importance']})"
            )

    anticipation_line = await _anticipation_surface_line(memory, now)
    if anticipation_line:
        parts.append(anticipation_line)

    # The time channel: the future line and the calendar echo side by side.
    recurrence_line = await _recurrence_surface_line(config, memory, now, random)
    if recurrence_line:
        parts.append(recurrence_line)

    # 5. Desire currents (3-direction)
    levels = desire.compute_levels_with_modulation()
    desire_summary = blend_desires(
        levels,
        ema_levels=desire.ema_levels,
        catalog=getattr(desire, "catalog", None),
        emergent_directions=desire.emergent_directions(),
    )
    parts.append(f"Desire currents: {desire_summary}")

    # 6. Relationship note
    relationship_line = await _call_relationship_snapshot(
        config, memory, config.companion_name
    )
    parts.append(relationship_line)
    try:
        reunion_store = _relationship_store(config)
        pending_reunion = _pending_reunion_note(reunion_store)
        if pending_reunion is not None:
            person_id, note = pending_reunion
            rel = reunion_store.get(person_id)
            name = rel.name if rel and rel.name else person_id
            gap_words = approx_duration_words(_reunion_gap_days(note))
            parts.append(
                f"Reunited with {name} recently — "
                f"the first shared moment in about {gap_words}."
            )
            shared_question_line = format_shared_question_line(self_store, person_id)
            if shared_question_line:
                parts.append(shared_question_line)
            reunion_store.mark_reunion_wake_up_shown(person_id)
    except Exception:
        pass

    # 7. Active persons
    _active_person_ids: list[str] = []
    try:
        _ws = _relationship_store(config)
        active_persons = _format_active_persons(_ws, max_persons=2)
        if active_persons:
            parts.append(active_persons)
        _active_person_ids = _get_active_person_ids(_ws, max_persons=2)
    except Exception:
        pass

    data = "\n\n".join(parts)
    if _active_person_ids:
        update_tool_metadata(
            active_person_ids=json.dumps(_active_person_ids),
        )
    return render_with_data(data, SCAFFOLD_WAKE_UP, config.companion_name)


async def _handle_introspect_network(
    config: EgoConfig, memory: MemoryStore
) -> str:
    """Notion graph topology summary, plus where the memory graph has no form."""
    notion_store = get_notion_store()
    analysis = analyze_notion_network(notion_store)
    data = format_network_analysis(analysis, notion_store)
    holes = await _format_holes_section(
        config, memory, notion_store, timezone_utils.now()
    )
    if holes:
        data += "\n" + holes
    return compose_response(data, SCAFFOLD_INTROSPECT_NETWORK)


async def _handle_introspect(
    config: EgoConfig,
    memory: MemoryStore,
    desire: DesireEngine,
    args: dict[str, Any] | None = None,
) -> str:
    """Introspection materials: week/month layers + notions + questions + episodes + desire trend."""
    focus = (args or {}).get("focus", "default")
    if focus == "network":
        return await _handle_introspect_network(config, memory)
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
            drift_lines = _drift_replacement_lines(config, top_notions, now)
            for notion in top_notions:
                # A notion whose ground moved is asked about instead of
                # asserted; the associated/meta suffixes are dropped to keep
                # the question line short (D4 S2).
                replacement = drift_lines.get(notion.id)
                if replacement is not None:
                    framework_lines.append(replacement)
                    continue
                meta_parts = ", ".join(
                    f"{k}:{v['type']}" for k, v in notion.meta_fields.items()
                )
                meta_str = f" meta=[{meta_parts}]" if meta_parts else ""
                framework_lines.append(
                    f'- "{notion.label}" confidence: {notion.confidence:.1f}'
                    f"{_format_associated_from_map(notion, notion_map, limit=2)}"
                    f"{meta_str}"
                )

    # §10.1 unresolved questions
    active_questions, resurfacing_questions = self_store.get_visible_questions()
    try:
        question_relationship_store = _relationship_store(config)
    except Exception:
        question_relationship_store = None
    question_lines: list[str] = []
    if active_questions:
        question_lines.append("Unresolved questions:")
        for item in active_questions:
            question_lines.append(_format_question_line(item, question_relationship_store))
    else:
        question_lines.append("No unresolved questions yet.")

    ripened_block = ""
    ripened = pick_ripened_question(
        self_store.get_unresolved_questions_with_salience()
    )
    if ripened is not None:
        try:
            ripened_block = await build_ripened_question_block(
                self_store,
                memory,
                ripened,
                relationship_store=question_relationship_store,
                notion_store=get_notion_store(),
                now=now,
            ) or ""
        except Exception:
            ripened_block = ""

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

    if ripened_block:
        question_lines.append("")
        question_lines.append(ripened_block)
    elif show_resurfacing:
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
    question_lines.append(
        'To hold a new question: update_self(field="new_question", value={"question": ..., "importance": 1-5})'
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

    # §D5 chapter boundaries — between the episodes and the self model
    chapter_lines = await _chapter_lines(config, memory, now)

    parts = [
        emotion_section,
        "\n".join(framework_lines) if framework_lines else "",
        open_questions,
        "\n".join(episode_lines) if episode_lines else "",
        "\n".join(chapter_lines) if chapter_lines else "",
        self_summary,
        "\n".join(desire_trend_lines) if desire_trend_lines else "",
        f"\nDesire currents: {desire_summary}",
        relationship_summary,
    ]
    data = "\n".join(part for part in parts if part)

    # Active persons
    _introspect_active_ids: list[str] = []
    try:
        _ws = _relationship_store(config)
        active_persons = _format_active_persons(_ws, max_persons=2)
        if active_persons:
            data += "\n" + active_persons
        _introspect_active_ids = _get_active_person_ids(_ws, max_persons=2)
    except Exception:
        pass

    if _introspect_active_ids:
        update_tool_metadata(
            active_person_ids=json.dumps(_introspect_active_ids),
        )
    scaffold = _filter_desire_scaffold(SCAFFOLD_INTROSPECT, desire)
    bridge_line = _stagnation_bridge_line(config, now)
    if bridge_line:
        scaffold = f"{scaffold}\n{bridge_line}"
    return render_with_data(data, scaffold, config.companion_name)


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
    resolved = store.resolve_person(person)
    if resolved is not None:
        person = resolved
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

    now = timezone_utils.now()
    relationship_summary = (
        f"{person}: {trust_words(rel.trust_level)}; "
        f"{history_words(rel.first_interaction, rel.total_interactions, now)}"
    )
    if rel.shared_episode_ids:
        relationship_summary += f", {episode_words(len(rel.shared_episode_ids))}"
    if preferred_topics:
        relationship_summary += (
            f", preferred_topics={','.join(preferred_topics[:2])}"
        )
    if sensitive_topics:
        relationship_summary += (
            f", sensitive_topics={','.join(sensitive_topics[:2])}"
        )
    if rel.last_interaction:
        last_interaction = _last_interaction_words(rel.last_interaction, now)
        if last_interaction:
            relationship_summary += f", last shared moment {last_interaction}"
    if rel.emotional_baseline:
        baseline_tone = max(
            rel.emotional_baseline.items(),
            key=lambda item: item[1],
        )[0]
        relationship_summary += f", baseline_tone={baseline_tone}"

    tendency = f"Recent dialog tendency: {frequency}, observed_tone={dominant_tone}"
    band, elapsed_days = absence_band(store.raw(person), now)
    absence_frame = ""
    if band in ("quiet", "long"):
        name = rel.name if rel and rel.name else person
        elapsed_words = approx_duration_words(elapsed_days)
        absence_frame = (
            f"It's been about {elapsed_words} since you last shared something with {name}.\n"
            "They may have changed in that time. What would you want to ask first?"
        )
    recent_moods = rel.recent_mood_trajectory[-3:]
    data_lines = [relationship_summary, tendency]
    if recent_moods:
        mood_tail = " > ".join(
            str(item.get("mood", "unknown"))
            for item in recent_moods
            if isinstance(item, dict)
        )
        data_lines.append(f"Recent mood trajectory: {mood_tail}")
    if absence_frame:
        data_lines.append(absence_frame)
    affect_line = _affect_trajectory_line(config, person, now)
    if affect_line:
        data_lines.append(affect_line)
    held_questions = shared_open_questions_for_person(
        SelfModelStore(config.data_dir / "self_model.json"),
        person,
        limit=2,
    )
    if held_questions:
        name = rel.name if rel and rel.name else person
        data_lines.append(f"Held together with {name}:")
        for question in held_questions:
            data_lines.append(f"- [{question['id']}] {question['question']}")
    data = "\n".join(data_lines)
    person_notions = sorted(
        (
            notion for notion in _list_notions_safe() if notion.person_id == person
        ),
        key=lambda notion: (-notion.confidence, -notion.reinforcement_count, notion.label),
    )
    if person_notions:
        impression_lines = [f"Impressions of {person}:"]
        for notion in person_notions[:3]:
            meta_parts = ", ".join(
                f"{k}:{v['type']}" for k, v in notion.meta_fields.items()
            )
            meta_str = f" meta=[{meta_parts}]" if meta_parts else ""
            impression_lines.append(
                f'  - "{notion.label}" confidence: {notion.confidence:.1f}{meta_str}'
            )
        data = f"{data}\n" + "\n".join(impression_lines)
    update_tool_metadata(
        person_id=person,
        trust_level=rel.trust_level,
        total_interactions=rel.total_interactions,
        shared_episodes_count=len(rel.shared_episode_ids),
    )
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
            meta_parts = ", ".join(
                f"{k}:{v['type']}" for k, v in notion.meta_fields.items()
            )
            meta_str = f" meta=[{meta_parts}]" if meta_parts else ""
            lines.append(f'- "{notion.label}"{meta_str}')
        data = "\n".join(lines)
    return compose_response(data, SCAFFOLD_PAUSE)
