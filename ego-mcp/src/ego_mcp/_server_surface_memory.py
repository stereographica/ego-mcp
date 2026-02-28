"""Surface handlers for remember/recall tools."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from ego_mcp._server_context import (
    _find_related_forgotten_questions,
    _relationship_store,
)
from ego_mcp._server_emotion_formatting import (
    _format_recall_entry,
    _recall_scaffold,
    _relative_time,
    _truncate_for_quote,
)
from ego_mcp._server_runtime import get_episodes, get_workspace_sync
from ego_mcp.config import EgoConfig
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.scaffolds import compose_response

logger = logging.getLogger(__name__)
_REMEMBER_DUPLICATE_PREFIX = "Not saved — very similar memory already exists."
_relative_time_override: Callable[[str, datetime | None], str] | None = None
_get_body_state_override: Callable[[], dict[str, Any]] | None = None


def configure_overrides(
    *,
    relative_time: Callable[[str, datetime | None], str] | None = None,
    get_body_state_fn: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Configure callables used for test-time override injection."""
    global _relative_time_override, _get_body_state_override
    _relative_time_override = relative_time
    _get_body_state_override = get_body_state_fn


def _call_relative_time(timestamp: str, now: datetime | None = None) -> str:
    if _relative_time_override is not None:
        return _relative_time_override(timestamp, now)
    return _relative_time(timestamp, now=now)


def _call_get_body_state() -> dict[str, Any]:
    if _get_body_state_override is not None:
        return _get_body_state_override()
    return get_body_state()


async def _handle_remember(
    config: EgoConfig,
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    """Save a memory with auto-linking."""
    content = args["content"]
    emotion = args.get("emotion", "neutral")
    secondary = args.get("secondary")
    intensity = args.get("intensity", 0.5)
    importance = args.get("importance", 3)
    category = args.get("category", "daily")
    valence = args.get("valence", 0.0)
    arousal = args.get("arousal", 0.5)
    private = bool(args.get("private", False))
    body_state = args.get("body_state") or _call_get_body_state()
    shared_with_raw = args.get("shared_with")
    related_memories_raw = args.get("related_memories")

    mem, num_links, linked_results, duplicate_of = await memory.save_with_auto_link(
        content=content,
        emotion=emotion,
        secondary=secondary,
        intensity=intensity,
        importance=importance,
        category=category,
        valence=valence,
        arousal=arousal,
        body_state=body_state,
        private=private,
    )
    if mem is None and duplicate_of is not None:
        similarity = max(0.0, min(1.0, 1.0 - duplicate_of.distance))
        age = _call_relative_time(duplicate_of.memory.timestamp)
        snippet = _truncate_for_quote(duplicate_of.memory.content, limit=120)
        data = (
            f"{_REMEMBER_DUPLICATE_PREFIX}\n"
            f"Existing (id: {duplicate_of.memory.id}, {age}): {snippet}\n"
            f"Similarity: {similarity:.2f}\n"
            "If this is a meaningful update, use recall to review the existing "
            "memory and consider whether the new perspective adds value."
        )
        scaffold = (
            "Is there truly something new here, or is this a repetition?\n"
            "If your understanding has deepened, try expressing what changed specifically."
        )
        return compose_response(data, scaffold)

    if mem is None:
        raise RuntimeError(
            "save_with_auto_link returned no memory without duplicate metadata"
        )
    sync = get_workspace_sync()
    sync_note = ""
    if sync is not None and not mem.is_private:
        try:
            sync_result = sync.sync_memory(mem)
            if sync_result.latest_monologue_updated:
                sync_note = " Synced latest introspection to workspace."
            elif sync_result.daily_updated:
                sync_note = " Synced to workspace memory logs."
        except OSError as exc:
            logger.warning("Workspace sync failed: %s", exc)

    top_links = sorted(linked_results, key=lambda r: r.distance)[:3]
    if top_links:
        link_lines = ["Most related:"]
        for linked_result in top_links:
            age = _call_relative_time(linked_result.memory.timestamp)
            snippet = _truncate_for_quote(linked_result.memory.content, limit=70)
            similarity = max(0.0, min(1.0, 1.0 - linked_result.distance))
            link_lines.append(
                f"- [{age}] {snippet} (similarity: {similarity:.2f})"
            )
        link_section = "\n".join(link_lines)
    else:
        link_section = "No similar memories found yet."

    forgotten_section = ""
    related_questions = _find_related_forgotten_questions(memory, mem.content)
    if related_questions:
        q = related_questions[0]
        age_days = max(0, int(round(float(q.get("age_days", 0.0)))))
        band = str(q.get("band", "dormant"))
        forgotten_section = (
            "\n"
            f'This triggered a forgotten question: "{q["question"]}"\n'
            f"({band} for {age_days} days, importance: {q['importance']})"
        )

    shared_with: list[str] = []
    if isinstance(shared_with_raw, str):
        person = shared_with_raw.strip()
        if person:
            shared_with = [person]
    elif isinstance(shared_with_raw, list):
        for item in shared_with_raw:
            if isinstance(item, str):
                person = item.strip()
                if person:
                    shared_with.append(person)
    shared_with_provided = bool(shared_with)

    shared_episode_section = ""
    if shared_with:
        related_ids: list[str] = []
        if isinstance(related_memories_raw, list):
            for memory_id in related_memories_raw:
                if not isinstance(memory_id, str):
                    continue
                candidate_id = memory_id.strip()
                if not candidate_id:
                    continue
                existing = await memory.get_by_id(candidate_id)
                if existing is None:
                    logger.warning("Skipping unknown related memory id: %s", candidate_id)
                    continue
                related_ids.append(candidate_id)

        episode_memory_ids = list(dict.fromkeys([mem.id, *related_ids]))
        summary = f"Shared experience with {', '.join(shared_with)}: {str(content)[:100]}"
        try:
            episode_store = get_episodes()
            episode = await episode_store.create(episode_memory_ids, summary)
            relationship_store = _relationship_store(config)
            for person in shared_with:
                relationship_store.add_shared_episode(person, episode.id)
            shared_episode_section = (
                "\n"
                f"Shared episode created: {episode.id} "
                f"({len(episode.memory_ids)} memories, with {', '.join(shared_with)})"
            )
        except Exception as exc:
            logger.warning("Shared episode creation failed: %s", exc)

    data = (
        f"Saved (id: {mem.id}). Linked to {num_links} existing memories.{sync_note}\n"
        f"{link_section}{forgotten_section}{shared_episode_section}"
    )
    if shared_with_provided:
        scaffold = (
            "You recorded a shared experience. Does this change how you understand "
            "your relationship with them?\n"
            "Do any of these connections surprise you? Is there a pattern forming?"
        )
    else:
        scaffold = (
            "Do any of these connections surprise you? Is there a pattern forming?\n"
            "If this experience involved someone, you can use shared_with to record "
            "it as a shared episode."
        )
    return compose_response(data, scaffold)


async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """Recall memories by context."""
    del config
    context = args["context"]
    raw_n_results = args.get("n_results", 3)
    try:
        n_results = min(int(raw_n_results), 10)
    except (TypeError, ValueError):
        n_results = 3
    n_results = max(1, n_results)
    emotion_filter = args.get("emotion_filter")
    category_filter = args.get("category_filter")
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    valence_range = args.get("valence_range")
    arousal_range = args.get("arousal_range")
    filters_used = [
        name
        for name, value in (
            ("emotion_filter", emotion_filter),
            ("category_filter", category_filter),
            ("date_from", date_from),
            ("date_to", date_to),
            ("valence_range", valence_range),
            ("arousal_range", arousal_range),
        )
        if value
    ]

    has_filters = bool(emotion_filter or category_filter or date_from or date_to)
    if has_filters:
        results = await memory.search(
            context,
            n_results=n_results,
            emotion_filter=emotion_filter,
            category_filter=category_filter,
            date_from=date_from,
            date_to=date_to,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )
    else:
        results = await memory.recall(
            context,
            n_results=n_results,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )

    total_count = memory.collection_count()
    if not results:
        data = "No related memories found."
    else:
        lines = [f"{len(results)} of ~{total_count} memories (showing top matches):"]
        now = datetime.now(timezone.utc)
        for i, result in enumerate(results, 1):
            lines.append(_format_recall_entry(i, result, now=now))
        data = "\n".join(lines)

    scaffold = _recall_scaffold(len(results), total_count, filters_used)
    return compose_response(data, scaffold)
