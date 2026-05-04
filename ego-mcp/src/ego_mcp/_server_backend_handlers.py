"""Backend tool handlers."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ego_mcp._memory_serialization import memory_to_chromadb
from ego_mcp._server_context import _relationship_store
from ego_mcp._server_emotion_formatting import (
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
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import (
    DeadLink,
    NotionStore,
    find_dead_links,
    generate_notion_from_cluster,
    infer_person_id,
    is_ephemeral_cluster,
)
from ego_mcp.scaffolds import (
    SCAFFOLD_CURATE_NOTIONS,
    compose_response,
)
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import MetaField

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
    memory: MemoryStore,
    consolidation: ConsolidationEngine,
    config: EgoConfig | None = None,
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
    # Person backfill: fill involved_person_ids for memories linked via shared_episode_ids
    _backfilled_count = 0
    try:
        _person_mem_ids = _load_person_memory_ids(memory)
        _mem_to_persons: dict[str, set[str]] = {}
        for _pid, _mids in _person_mem_ids.items():
            for _mid in _mids:
                _mem_to_persons.setdefault(_mid, set()).add(_pid)
        _MAX_BACKFILL_PER_RUN = 50
        _backfilled = 0
        for _mid, _pids in list(_mem_to_persons.items())[:_MAX_BACKFILL_PER_RUN]:
            _mem = await memory.get_by_id(_mid)
            if _mem is not None and not _mem.involved_person_ids:
                _mem.involved_person_ids = sorted(_pids)
                try:
                    _col = memory.get_client().get_or_create_collection(name="ego_memories")
                    _col.update(ids=[_mem.id], metadatas=[memory_to_chromadb(_mem)])
                except Exception:
                    pass
                _backfilled += 1
        _backfilled_count = _backfilled
    except Exception:
        pass

    # Dead link detection (skip if workspace_dir is not configured)
    dead_links: list[DeadLink] = []
    if config is not None and config.workspace_dir is not None and notion_store is not None:
        try:
            dead_links = find_dead_links(notion_store, config.workspace_dir)
        except Exception:
            pass

    dead_links_file_path = sum(1 for dl in dead_links if dl.link_type == "file_path")
    dead_links_notion_ids = sum(1 for dl in dead_links if dl.link_type == "notion_ids")

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
        person_backfilled=_backfilled_count or None,
        dead_links_file_path=dead_links_file_path or None,
        dead_links_notion_ids=dead_links_notion_ids or None,
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
    if _backfilled_count:
        base += f" Backfilled involved_person_ids for {_backfilled_count} memory(s)."
    if dead_links:
        dead_link_lines = []
        for dl in dead_links:
            targets = ", ".join(dl.dead_targets)
            dead_link_lines.append(
                f"  {dl.notion_id}.{dl.meta_key} ({dl.link_type}): {targets}"
            )
        base += f"\nDead links found ({len(dead_links)}):\n" + "\n".join(dead_link_lines)
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
    resolved = relationship_store.resolve_person(person)
    if resolved is not None:
        person = resolved
    try:
        relationship_store.update(person, {field_name: value})
    except ValueError as exc:
        msg = str(exc)
        if "Invalid" in msg and "field" in msg:
            return (
                f"I don't have a sense of '{original_field}' for relationships. "
                f"What I can reflect on: {', '.join(sorted(_FIELD_ALIASES.values()))}."
            )
        return msg
    except TypeError:
        return f"The value for '{original_field}' doesn't quite fit — it may need a different type."
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
    except ValueError as exc:
        msg = str(exc)
        if "Invalid" in msg and "field" in msg:
            return (
                f"I don't have a sense of '{field_name}' in my self-model. "
                f"What I can reflect on: {', '.join(sorted(_SELF_FIELD_ALIASES.values()))}."
            )
        return msg
    except TypeError:
        return f"The value for '{field_name}' doesn't quite fit — it may need a different type."
    return f"Updated self.{field_name}"


def _handle_curate_notions(
    args: dict[str, Any],
    notion_store: NotionStore,
    config: EgoConfig | None = None,
) -> str:
    def _compose(data: str) -> str:
        return compose_response(data, SCAFFOLD_CURATE_NOTIONS)

    action = str(args.get("action", "")).strip()

    if action in ("add_meta", "update_meta", "remove_meta"):
        return _handle_curate_notions_meta(action, args, notion_store, config)

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
            meta_parts = ", ".join(
                f"{k}:{v['type']}" for k, v in notion.meta_fields.items()
            )
            meta_str = f" meta=[{meta_parts}]" if meta_parts else ""
            lines.append(
                f'- {notion.id}: "{notion.label}" '
                f"conf={notion.confidence:.2f} reinf={notion.reinforcement_count} "
                f"age={age} person={person_label} related={len(notion.related_notion_ids)}"
                f"{meta_str}"
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


def _handle_curate_notions_meta(
    action: str,
    args: dict[str, Any],
    notion_store: NotionStore,
    config: EgoConfig | None,
) -> str:
    """Handle add_meta, update_meta, remove_meta actions."""
    def _compose(data: str) -> str:
        return compose_response(data, SCAFFOLD_CURATE_NOTIONS)

    notion_id = str(args.get("notion_id", "")).strip()
    meta_key = str(args.get("meta_key", "")).strip()

    if not notion_id:
        return _compose("Error: notion_id is required.")
    if not meta_key:
        return _compose("Error: meta_key is required.")

    notion = notion_store.get_by_id(notion_id)
    if notion is None:
        return _compose(f"Error: notion {notion_id} not found.")

    if action == "add_meta":
        meta_type = str(args.get("meta_type", "")).strip()
        meta_value = args.get("meta_value")
        if not meta_type:
            return _compose("Error: meta_type is required for add_meta.")
        if meta_value is None:
            return _compose("Error: meta_value is required for add_meta.")

        if meta_key in notion.meta_fields:
            return _compose(f"Error: meta_field '{meta_key}' already exists. Use update_meta to modify.")

        meta_field = _validate_and_build_meta_field(meta_type, meta_value, notion_store, config)
        if isinstance(meta_field, str):
            return _compose(meta_field)

        notion.meta_fields[meta_key] = meta_field
        notion_store.update(notion_id, meta_fields=notion.meta_fields)
        update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
        return _compose(f"Added meta_field '{meta_key}' to notion {notion_id}.")

    if action == "update_meta":
        meta_value = args.get("meta_value")
        if meta_value is None:
            return _compose("Error: meta_value is required for update_meta.")

        if meta_key not in notion.meta_fields:
            return _compose(f"Error: meta_field '{meta_key}' does not exist. Use add_meta to create.")

        existing = notion.meta_fields[meta_key]
        meta_type = existing["type"]
        meta_field = _validate_and_build_meta_field(meta_type, meta_value, notion_store, config)
        if isinstance(meta_field, str):
            return _compose(meta_field)

        notion.meta_fields[meta_key] = meta_field
        notion_store.update(notion_id, meta_fields=notion.meta_fields)
        update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
        return _compose(f"Updated meta_field '{meta_key}' on notion {notion_id}.")

    if action == "remove_meta":
        if meta_key not in notion.meta_fields:
            return _compose(f"Error: meta_field '{meta_key}' does not exist.")

        del notion.meta_fields[meta_key]
        notion_store.update(notion_id, meta_fields=notion.meta_fields)
        update_tool_metadata(curate_action=action, curate_notion_id=notion_id)
        return _compose(f"Removed meta_field '{meta_key}' from notion {notion_id}.")

    return _compose(f"Error: unknown action: {action}")


def _resolve_workspace_path(
    workspace_dir: Path,
    meta_value: str,
) -> tuple[Path, str | None]:
    """Resolve a file_path meta_value to a workspace-absolute path.

    Returns (resolved_path, error_string).
    On success error_string is None.
    Rejects absolute paths and parent-traversal outside the workspace.
    """
    candidate = workspace_dir / meta_value
    resolved = candidate.resolve()
    workspace_resolved = workspace_dir.resolve()
    try:
        resolved.relative_to(workspace_resolved)
    except ValueError:
        return resolved, (
            f"Error: file_path '{meta_value}' resolves outside the workspace. "
            "Absolute paths and '..' escapes are not allowed."
        )
    return resolved, None


def _validate_and_build_meta_field(
    meta_type: str,
    meta_value: Any,
    notion_store: NotionStore,
    config: EgoConfig | None,
) -> MetaField | str:
    """Validate meta_value based on type and build a MetaField dict.

    Returns the MetaField on success, or an error string on failure.
    """
    if meta_type == "text":
        if not isinstance(meta_value, str):
            return "Error: meta_value must be a string for text type."
        return {"type": "text", "value": meta_value}

    if meta_type == "file_path":
        if not isinstance(meta_value, str):
            return "Error: meta_value must be a string (path) for file_path type."
        if config is None or config.workspace_dir is None:
            return (
                "Error: EGO_MCP_WORKSPACE_DIR is not configured. "
                "file_path meta_fields require a workspace directory."
            )
        resolved, err = _resolve_workspace_path(config.workspace_dir, meta_value)
        if err is not None:
            return err
        if not meta_value or not resolved.is_file():
            return f"Error: file not found: {meta_value}"
        return {"type": "file_path", "path": meta_value}

    if meta_type == "notion_ids":
        if not isinstance(meta_value, list):
            return (
                "Error: meta_value must be an array of notion_ids "
                "for notion_ids type."
            )
        validated_ids: list[str] = []
        for item in meta_value:
            if not isinstance(item, str) or not item.strip():
                return (
                    f"Error: each notion_ids entry must be a non-empty string, "
                    f"got: {item!r}"
                )
            validated_ids.append(item.strip())
        unique_ids = list(dict.fromkeys(validated_ids))
        missing = [nid for nid in unique_ids if notion_store.get_by_id(nid) is None]
        if missing:
            return f"Error: notion(s) not found: {', '.join(missing)}"
        return {"type": "notion_ids", "notion_ids": unique_ids}

    return f"Error: unknown meta_type: {meta_type}"


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
