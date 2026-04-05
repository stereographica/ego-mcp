"""Backend tool handlers."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ego_mcp import timezone_utils
from ego_mcp._server_context import _relationship_store
from ego_mcp._server_emotion_formatting import (
    _format_month_emotion_layer,
    _format_recent_emotion_layer,
    _format_week_emotion_layer,
    _relative_time,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import (
    get_notion_store,
    get_workspace_sync,
    update_tool_metadata,
)
from ego_mcp._server_tools import _FIELD_ALIASES
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import (
    NotionStore,
    generate_notion_from_cluster,
    infer_person_id,
    is_ephemeral_cluster,
)
from ego_mcp.scaffolds import (
    SCAFFOLD_CURATE_NOTIONS,
    SCAFFOLD_EMOTION_TREND,
    compose_response,
)
from ego_mcp.self_model import SelfModelStore

logger = logging.getLogger(__name__)
_relative_time_override: Callable[[str, datetime | None], str] | None = None
_last_tool_context: dict[str, dict[str, object]] = {}


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


def _set_tool_context(name: str, context: dict[str, object]) -> None:
    _last_tool_context[name] = dict(context)


def pop_tool_context(name: str) -> dict[str, object]:
    return _last_tool_context.pop(name, {})


def _handle_satisfy_desire(desire: DesireEngine, args: dict[str, Any]) -> str:
    """Satisfy a desire."""
    name = args["name"]
    quality = args.get("quality", 0.7)
    new_level = desire.satisfy(name, quality)
    return f"{name} satisfied (quality: {quality}). New level: {new_level:.2f}"


def _load_person_memory_ids(memory: MemoryStore) -> dict[str, set[str]]:
    person_memory_ids: dict[str, set[str]] = {}
    if not hasattr(memory, "data_dir") or not hasattr(memory, "get_client"):
        return person_memory_ids
    relationships_path = Path(memory.data_dir) / "relationships" / "models.json"
    try:
        raw_payload = json.loads(relationships_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_payload = {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    try:
        collection = memory.get_client().get_or_create_collection(name="ego_episodes")
    except Exception:
        collection = None

    for person, raw in raw_payload.items():
        if not isinstance(person, str) or not isinstance(raw, dict):
            continue
        episode_ids = raw.get("shared_episode_ids", [])
        if not isinstance(episode_ids, list) or not episode_ids:
            continue
        if collection is None:
            continue
        try:
            rows = collection.get(ids=episode_ids, include=["metadatas"])
        except Exception:
            continue
        metadatas = rows.get("metadatas", [])
        if not isinstance(metadatas, list):
            continue
        for metadata in metadatas:
            if not isinstance(metadata, dict):
                continue
            raw_memory_ids = metadata.get("memory_ids", [])
            if isinstance(raw_memory_ids, str):
                try:
                    memory_ids = json.loads(raw_memory_ids)
                except json.JSONDecodeError:
                    memory_ids = []
            else:
                memory_ids = raw_memory_ids
            if not isinstance(memory_ids, list):
                continue
            person_memory_ids.setdefault(person, set()).update(
                memory_id
                for memory_id in memory_ids
                if isinstance(memory_id, str) and memory_id
            )
    return person_memory_ids


async def _handle_consolidate(
    memory: MemoryStore, consolidation: ConsolidationEngine
) -> str:
    """Run memory consolidation."""
    stats = await consolidation.run(memory)
    created_notion_ids: list[str] = []
    created_notion_confidences: dict[str, float] = {}
    decayed_notion_ids: list[str] = []
    pruned_notion_ids: list[str] = []
    merged_notion_ids: list[str] = []
    notion_links_created = 0
    try:
        notion_store = get_notion_store()
    except Exception:
        notion_store = None
    if notion_store is not None:
        person_memory_ids = _load_person_memory_ids(memory)
        existing_clusters = {
            tuple(sorted(notion.source_memory_ids)) for notion in notion_store.list_all()
        }
        for cluster in stats.detected_clusters:
            normalized_cluster = tuple(sorted(cluster))
            if normalized_cluster in existing_clusters:
                continue
            cluster_memories = [
                loaded
                for memory_id in normalized_cluster
                for loaded in [await memory.get_by_id(memory_id)]
                if loaded is not None
            ]
            if len(cluster_memories) < 3:
                continue
            if is_ephemeral_cluster(cluster_memories):
                continue
            notion = generate_notion_from_cluster(cluster_memories)
            notion.person_id = infer_person_id(notion.source_memory_ids, person_memory_ids)
            notion_store.save(notion)
            created_notion_ids.append(notion.id)
            created_notion_confidences[notion.id] = notion.confidence
            existing_clusters.add(normalized_cluster)
        for notion_id, outcome in notion_store.apply_time_decay():
            if outcome == "decayed":
                decayed_notion_ids.append(notion_id)
                loaded_notion = notion_store.get_by_id(notion_id)
                if loaded_notion is not None:
                    created_notion_confidences[loaded_notion.id] = loaded_notion.confidence
            elif outcome == "pruned":
                pruned_notion_ids.append(notion_id)
        for component in notion_store.find_duplicate_components():
            notions = [
                notion
                for notion_id in component
                for notion in [notion_store.get_by_id(notion_id)]
                if notion is not None
            ]
            if len(notions) < 2:
                continue
            ordered = sorted(
                notions,
                key=lambda notion: (
                    -notion.confidence,
                    -notion.reinforcement_count,
                    notion.created,
                    notion.id,
                ),
            )
            keep = ordered[0]
            for absorb in ordered[1:]:
                merged = notion_store.merge_notions(keep.id, absorb.id)
                if merged is not None:
                    keep = merged
                    merged_notion_ids.append(absorb.id)
                    created_notion_confidences[keep.id] = keep.confidence
        notion_links_created = notion_store.auto_link_notions()
    update_tool_metadata(
        consolidation_replay_events=stats.replay_events,
        consolidation_new_links=stats.link_updates,
        consolidation_coactivation_updates=stats.coactivation_updates,
        consolidation_pruned_links=stats.pruned_links,
        consolidation_link_types=json.dumps(
            {
                "replay": max(
                    0,
                    stats.link_updates
                    - stats.emotion_links
                    - stats.theme_links
                    - stats.cross_category_links,
                ),
                "emotion": stats.emotion_links,
                "theme": stats.theme_links,
                "cross_category": stats.cross_category_links,
            },
            sort_keys=True,
        ),
        notion_created=",".join(created_notion_ids) if created_notion_ids else None,
        notion_confidence=max(created_notion_confidences.values())
        if created_notion_confidences
        else None,
        notion_confidences=json.dumps(created_notion_confidences, sort_keys=True)
        if created_notion_confidences
        else None,
        notion_decayed=",".join(decayed_notion_ids) if decayed_notion_ids else None,
        notion_pruned=",".join(pruned_notion_ids) if pruned_notion_ids else None,
        notion_merged=",".join(merged_notion_ids) if merged_notion_ids else None,
        notion_links_created=notion_links_created or None,
    )
    base = (
        f"Consolidation complete. "
        f"Replayed {stats.replay_events} events, "
        f"updated {stats.coactivation_updates} co-activations, "
        f"created {stats.link_updates} links, "
        f"refreshed {stats.refreshed_memories} memories."
    )
    if created_notion_ids:
        base += f" Created {len(created_notion_ids)} notion(s)."
    if decayed_notion_ids:
        base += f" Decayed {len(decayed_notion_ids)} notion(s)."
    if pruned_notion_ids:
        base += f" Pruned {len(pruned_notion_ids)} notion(s)."
    if merged_notion_ids:
        base += f" Merged {len(merged_notion_ids)} duplicate(s)."
    if notion_links_created:
        base += f" Linked {notion_links_created} notion pair(s)."
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
    except (ValueError, TypeError) as exc:
        return f"Error: {exc}"
    return f"Updated {person}.{field_name}"


_SELF_FIELD_ALIASES: dict[str, str] = {
    "confidence": "confidence_calibration",
    "goals": "current_goals",
    "values": "discovered_values",
    "narratives": "identity_narratives",
}


def _handle_update_self(config: EgoConfig, args: dict[str, Any]) -> str:
    """Update self model."""
    field_name = _SELF_FIELD_ALIASES.get(args["field"], args["field"])
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

    try:
        store.update({field_name: value})
    except (ValueError, TypeError) as exc:
        return f"Error: {exc}"
    return f"Updated self.{field_name}"


def _handle_curate_notions(args: dict[str, Any], notion_store: NotionStore) -> str:
    def _compose(data: str) -> str:
        return compose_response(data, SCAFFOLD_CURATE_NOTIONS)

    action = str(args.get("action", "")).strip()
    if action == "list":
        notions = sorted(
            notion_store.list_all(),
            key=lambda notion: (
                -notion.confidence,
                -notion.reinforcement_count,
                notion.label,
                notion.id,
            ),
        )
        update_tool_metadata(curate_action=action)
        if not notions:
            return _compose("No notions available.")
        lines = ["Notions:"]
        for notion in notions[:15]:
            person_label = notion.person_id or "-"
            age = _call_relative_time(notion.created)
            lines.append(
                f'- {notion.id}: "{notion.label}" '
                f"conf={notion.confidence:.2f} reinf={notion.reinforcement_count} "
                f"age={age} person={person_label} related={len(notion.related_notion_ids)}"
            )
        return _compose("\n".join(lines))

    notion_id = str(args.get("notion_id", "")).strip()
    if not notion_id:
        return _compose("notion_id is required.")

    if action == "delete":
        if notion_store.delete(notion_id):
            update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
            return _compose(f"Deleted {notion_id}")
        return _compose(f"Notion not found: {notion_id}")

    if action == "merge":
        merge_into = str(args.get("merge_into", "")).strip()
        if not merge_into:
            return _compose("merge_into is required for merge.")
        person_value = args.get("person")
        person: str | None = None
        if isinstance(person_value, str):
            person = person_value.strip()
        merged = notion_store.merge_notions(merge_into, notion_id, person_id=person)
        if merged is None:
            return _compose("Merge failed.")
        update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
        return _compose(f"Merged {notion_id} into {merge_into}")

    if action == "relabel":
        new_label = str(args.get("new_label", "")).strip()
        if not new_label:
            return _compose("new_label is required for relabel.")
        updates: dict[str, Any] = {"label": new_label}
        person_value = args.get("person")
        if isinstance(person_value, str):
            updates["person_id"] = person_value.strip()
        updated_notion = notion_store.update(notion_id, **updates)
        if updated_notion is None:
            return _compose(f"Notion not found: {notion_id}")
        update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
        return _compose(f"Renamed {notion_id} to {new_label}")

    return _compose(f"Unknown action: {action}")


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

    now = timezone_utils.now()
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
