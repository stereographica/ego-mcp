"""Backend tool handlers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from ego_mcp._server_context import _relationship_store
from ego_mcp._server_emotion_formatting import (
    _format_month_emotion_layer,
    _format_recent_emotion_layer,
    _format_week_emotion_layer,
    _relative_time,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import get_workspace_sync
from ego_mcp._server_tools import _FIELD_ALIASES
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore
from ego_mcp.scaffolds import SCAFFOLD_EMOTION_TREND, compose_response
from ego_mcp.self_model import SelfModelStore

logger = logging.getLogger(__name__)
_relative_time_override: Callable[[str, datetime | None], str] | None = None


def configure_overrides(
    *,
    relative_time: Callable[[str, datetime | None], str] | None = None,
) -> None:
    """Configure callables used for test-time override injection."""
    global _relative_time_override
    _relative_time_override = relative_time


def _call_relative_time(timestamp: str, now: datetime | None = None) -> str:
    if _relative_time_override is not None:
        return _relative_time_override(timestamp, now)
    return _relative_time(timestamp, now=now)


def _handle_satisfy_desire(desire: DesireEngine, args: dict[str, Any]) -> str:
    """Satisfy a desire."""
    name = args["name"]
    quality = args.get("quality", 0.7)
    new_level = desire.satisfy(name, quality)
    return f"{name} satisfied (quality: {quality}). New level: {new_level:.2f}"


async def _handle_consolidate(
    memory: MemoryStore, consolidation: ConsolidationEngine
) -> str:
    """Run memory consolidation."""
    stats = await consolidation.run(memory)
    base = (
        f"Consolidation complete. "
        f"Replayed {stats.replay_events} events, "
        f"updated {stats.coactivation_updates} co-activations, "
        f"created {stats.link_updates} links, "
        f"refreshed {stats.refreshed_memories} memories."
    )
    if not stats.merge_candidates:
        return base

    lines = [base, f"Found {len(stats.merge_candidates)} near-duplicate pair(s):"]
    for candidate in stats.merge_candidates:
        similarity = max(0.0, min(1.0, 1.0 - candidate.distance))
        lines.append(
            f"- {candidate.memory_a_id} <-> {candidate.memory_b_id} "
            f"(similarity: {similarity:.2f})"
        )
        lines.append(f"  A: {candidate.snippet_a}")
        lines.append(f"  B: {candidate.snippet_b}")
    lines.append("")
    lines.append("Review each pair with recall. If one is redundant, use forget to remove it.")
    lines.append("If both have value, consider which perspective to keep.")
    return "\n".join(lines)


async def _handle_forget(memory: MemoryStore, args: dict[str, Any]) -> str:
    """Delete a memory by ID and report a short summary for confirmation."""
    memory_id = args["memory_id"]
    deleted = await memory.delete(memory_id)
    if deleted is None:
        data = f"Memory not found: {memory_id}"
        scaffold = "Double-check the ID. Use recall to search for the memory you're looking for."
        return compose_response(data, scaffold)

    sync = get_workspace_sync()
    sync_note = ""
    if sync is not None and not deleted.is_private:
        try:
            removed = sync.remove_memory(memory_id)
            if removed:
                sync_note = "\nWorkspace sync: removed matching entries from memory logs."
        except OSError as exc:
            logger.warning("Workspace memory removal failed: %s", exc)

    age = _call_relative_time(deleted.timestamp)
    snippet = _truncate_for_quote(deleted.content, limit=120)
    data = (
        f"Forgot {deleted.id} [{age}]\n"
        f"{snippet}\n"
        f"emotion: {deleted.emotional_trace.primary.value} | "
        f"importance: {deleted.importance}{sync_note}"
    )
    scaffold = (
        "This memory is gone. Was there anything worth preserving in a new form?\n"
        "If this was part of a merge, save the consolidated version with remember."
    )
    return compose_response(data, scaffold)


async def _handle_link_memories(memory: MemoryStore, args: dict[str, Any]) -> str:
    """Create bidirectional link between memories."""
    source_id = args["source_id"]
    target_id = args["target_id"]
    link_type = args.get("link_type", "related")
    created = await memory.link_memories(source_id, target_id, link_type)
    if created:
        return f"Linked {source_id} ↔ {target_id} (type: {link_type})"
    else:
        return f"Link already exists or memories not found: {source_id} ↔ {target_id}"


def _handle_update_relationship(config: EgoConfig, args: dict[str, Any]) -> str:
    """Update relationship model."""
    person = args["person"]
    original_field = str(args["field"])
    field_name = _FIELD_ALIASES.get(original_field, original_field)
    value = args["value"]
    if original_field == "dominant_tone" and isinstance(value, str):
        value = {value: 1.0}
    relationship_store = _relationship_store(config)
    try:
        relationship_store.update(person, {field_name: value})
    except ValueError as exc:
        return f"Error: {exc}"
    return f"Updated {person}.{field_name}"


def _handle_update_self(config: EgoConfig, args: dict[str, Any]) -> str:
    """Update self model."""
    field_name = args["field"]
    value = args["value"]
    store = SelfModelStore(config.data_dir / "self_model.json")

    if field_name == "resolve_question":
        question_id = str(value)
        if store.resolve_question(question_id):
            return f"Resolved question {question_id}."
        return f"Question {question_id} not found or already resolved."

    if field_name == "question_importance":
        if not isinstance(value, dict):
            return "question_importance expects {id, importance}."
        question_id = str(value.get("id", ""))
        if not question_id:
            return "question_importance expects a non-empty id."
        importance = value.get("importance", 3)
        if store.update_question_importance(question_id, int(importance)):
            return f"Updated question importance for {question_id}."
        return f"Question {question_id} not found."

    store.update({field_name: value})
    return f"Updated self.{field_name}"


async def _handle_emotion_trend(memory: MemoryStore) -> str:
    """Analyze emotional patterns over time with graceful degradation."""
    memories = await memory.list_recent(n=200)
    total = len(memories)
    if total == 0:
        return compose_response("No emotional history yet.", SCAFFOLD_EMOTION_TREND)

    if total < 5:
        unique_emotions = sorted({m.emotional_trace.primary.value for m in memories})
        data = (
            f"Still early - only {total} memories so far.\n"
            f"Emotions felt: {', '.join(unique_emotions)}\n"
            "Too few data points for trends."
        )
        return compose_response(data, SCAFFOLD_EMOTION_TREND)

    now = datetime.now(timezone.utc)
    sections = [_format_recent_emotion_layer(memories, now=now)]
    if total >= 15:
        sections.append(_format_week_emotion_layer(memories, now=now))
    if total >= 30:
        sections.append(_format_month_emotion_layer(memories, now=now))

    return compose_response("\n\n".join(sections), SCAFFOLD_EMOTION_TREND)


async def _handle_get_episode(
    episodes: EpisodeStore,
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    """Get episode details."""
    episode_id = args["episode_id"]
    ep = await episodes.get_by_id(episode_id)
    if ep is None:
        return f"Episode not found: {episode_id}"

    valid_memory_ids: list[str] = []
    missing_count = 0
    for memory_id in ep.memory_ids:
        if await memory.get_by_id(memory_id) is None:
            missing_count += 1
            continue
        valid_memory_ids.append(memory_id)

    lines = [
        f"Episode: {ep.id}",
        f"Summary: {ep.summary}",
        f"Memories: {len(valid_memory_ids)}",
        f"Period: {ep.start_time} → {ep.end_time}",
        f"Importance: {ep.importance}",
    ]
    if missing_count:
        lines.append(f"Note: {missing_count} memory(ies) no longer exist.")
    return "\n".join(lines)


async def _handle_create_episode(episodes: EpisodeStore, args: dict[str, Any]) -> str:
    """Create episode from memories."""
    memory_ids = args["memory_ids"]
    summary = args["summary"]
    ep = await episodes.create(memory_ids=memory_ids, summary=summary)
    return f"Created episode {ep.id} with {len(ep.memory_ids)} memories."
