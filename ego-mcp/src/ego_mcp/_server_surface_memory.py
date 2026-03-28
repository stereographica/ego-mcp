"""Surface handlers for remember/recall tools."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

from ego_mcp import timezone_utils
from ego_mcp._memory_queries import find_resurfacing_memories
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
from ego_mcp._server_runtime import (
    get_episodes,
    get_notion_store,
    get_workspace_sync,
    update_tool_metadata,
)
from ego_mcp.config import EgoConfig
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import update_notion_from_memory
from ego_mcp.scaffolds import SCAFFOLD_REMEMBER, compose_response

logger = logging.getLogger(__name__)
_REMEMBER_DUPLICATE_PREFIX = "Not saved — very similar memory already exists."
EMOTION_DEFAULTS: dict[str, tuple[float, float, float]] = {
    # emotion: (intensity, valence, arousal)
    "happy": (0.6, 0.6, 0.5),
    "excited": (0.8, 0.7, 0.8),
    "calm": (0.4, 0.3, 0.2),
    "neutral": (0.3, 0.0, 0.3),
    "curious": (0.6, 0.3, 0.6),
    "contemplative": (0.5, 0.1, 0.3),
    "thoughtful": (0.5, 0.1, 0.4),
    "grateful": (0.6, 0.7, 0.4),
    "vulnerable": (0.6, -0.3, 0.5),
    "content": (0.5, 0.5, 0.2),
    "fulfilled": (0.6, 0.6, 0.2),
    "touched": (0.7, 0.5, 0.4),
    "moved": (0.7, 0.5, 0.5),
    "concerned": (0.5, -0.3, 0.5),
    "hopeful": (0.6, 0.4, 0.5),
    "peaceful": (0.4, 0.4, 0.1),
    "love": (0.8, 0.8, 0.4),
    "warm": (0.5, 0.5, 0.3),
    "sad": (0.5, -0.6, 0.2),
    "anxious": (0.7, -0.6, 0.8),
    "angry": (0.8, -0.7, 0.9),
    "frustrated": (0.7, -0.5, 0.7),
    "lonely": (0.6, -0.6, 0.3),
    "afraid": (0.8, -0.8, 0.9),
    "ashamed": (0.6, -0.7, 0.4),
    "bored": (0.3, -0.3, 0.1),
    "nostalgic": (0.5, 0.1, 0.3),
    "contentment": (0.5, 0.5, 0.2),
    "melancholy": (0.5, -0.4, 0.2),
    "surprised": (0.7, 0.1, 0.9),
}
_relative_time_override: Callable[[str, datetime | None], str] | None = None
_get_body_state_override: Callable[[], dict[str, Any]] | None = None
_last_tool_context: dict[str, dict[str, object]] = {}


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


def _set_tool_context(name: str, context: dict[str, object]) -> None:
    _last_tool_context[name] = dict(context)


def pop_tool_context(name: str) -> dict[str, object]:
    return _last_tool_context.pop(name, {})


def _float_or_default(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _normalize_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, str):
        candidates = [raw_tags]
    elif isinstance(raw_tags, list):
        candidates = [item for item in raw_tags if isinstance(item, str)]
    else:
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        tag = candidate.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


async def _handle_remember(
    config: EgoConfig,
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    """Save a memory with auto-linking."""
    _set_tool_context("remember", {})
    content = args["content"]
    emotion = args.get("emotion", "neutral")
    defaults = EMOTION_DEFAULTS.get(emotion, (0.5, 0.0, 0.5))
    secondary = args.get("secondary")
    intensity = (
        _float_or_default(args.get("intensity"), defaults[0])
        if "intensity" in args
        else defaults[0]
    )
    importance = args.get("importance", 3)
    category = args.get("category", "daily")
    valence = (
        _float_or_default(args.get("valence"), defaults[1])
        if "valence" in args
        else defaults[1]
    )
    arousal = (
        _float_or_default(args.get("arousal"), defaults[2])
        if "arousal" in args
        else defaults[2]
    )
    private = bool(args.get("private", False))
    body_state = args.get("body_state") or _call_get_body_state()
    tags = _normalize_tags(args.get("tags"))
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
        tags=tags,
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

    notion_updates = update_notion_from_memory(get_notion_store(), mem)
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

    resurfaced = await find_resurfacing_memories(
        memory,
        mem.content,
        exclude_ids={mem.id},
    )
    top_links = sorted(linked_results, key=lambda r: r.distance)[:3]
    if top_links or resurfaced:
        link_lines = ["Most related:"]
        for linked_result in top_links:
            age = _call_relative_time(linked_result.memory.timestamp)
            snippet = _truncate_for_quote(linked_result.memory.content, limit=70)
            similarity = max(0.0, min(1.0, 1.0 - linked_result.distance))
            link_lines.append(
                f"- [{age}] {snippet} (similarity: {similarity:.2f})"
            )
        for resurfaced_result in resurfaced:
            age = _call_relative_time(resurfaced_result.memory.timestamp)
            snippet = _truncate_for_quote(resurfaced_result.memory.content, limit=70)
            link_lines.append(
                f"- [{age}] {snippet} (decay: {resurfaced_result.decay:.2f})"
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
            f"{SCAFFOLD_REMEMBER}"
        )
    else:
        scaffold = SCAFFOLD_REMEMBER
    remember_context: dict[str, object] = {}
    if resurfaced:
        remember_context["resurfaced_memory_id"] = ",".join(
            result.memory.id for result in resurfaced
        )
    if notion_updates:
        by_state: dict[str, list[str]] = {}
        notion_confidences: dict[str, float] = {}
        notion_store = get_notion_store()
        for notion_id, state in notion_updates:
            by_state.setdefault(state, []).append(notion_id)
            notion = notion_store.get_by_id(notion_id)
            if notion is not None:
                notion_confidences[notion_id] = notion.confidence
        if "reinforced" in by_state:
            remember_context["notion_reinforced"] = ",".join(by_state["reinforced"])
        if "weakened" in by_state:
            remember_context["notion_weakened"] = ",".join(by_state["weakened"])
        if "dormant" in by_state:
            remember_context["notion_dormant"] = ",".join(by_state["dormant"])
        if notion_confidences:
            remember_context["notion_confidence"] = max(notion_confidences.values())
            remember_context["notion_confidences"] = json.dumps(
                notion_confidences,
                sort_keys=True,
            )
    _set_tool_context("remember", remember_context)
    return compose_response(data, scaffold)


async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """Recall memories by context."""
    del config
    _set_tool_context("recall", {})
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

    results = await memory.recall(
        context,
        n_results=n_results,
        emotion_filter=emotion_filter,
        category_filter=category_filter,
        date_from=date_from,
        date_to=date_to,
        valence_range=valence_range,
        arousal_range=arousal_range,
    )

    total_count = memory.collection_count()
    if not results:
        data = "No related memories found."
    else:
        lines = [f"{len(results)} of ~{total_count} memories (showing top matches):"]
        now = timezone_utils.now()
        for i, result in enumerate(results, 1):
            lines.extend(_format_recall_entry(i, result, now=now).splitlines())

        notion_tags = sorted(
            {
                tag
                for result in results
                for tag in result.memory.tags
                if isinstance(tag, str) and tag.strip()
            }
        )
        recalled_memory_ids = [result.memory.id for result in results if result.memory.id]
        notion_store = get_notion_store()
        related_notions = notion_store.search_related(
            source_memory_ids=recalled_memory_ids,
            tags=notion_tags,
            min_tag_match=1,
        )
        if related_notions:
            lines.append("--- notions ---")
            for notion in related_notions[:3]:
                associated = notion_store.get_associated(notion.id, depth=1)
                lines.append(
                    f'"{notion.label}" {notion.emotion_tone.value} '
                    f"confidence: {notion.confidence:.1f}"
                )
                if associated:
                    lines.append(
                        "  → "
                        + ", ".join(
                            f'"{item.label}" confidence: {item.confidence:.1f}'
                            for item in associated[:2]
                        )
                    )
        data = "\n".join(lines)

    scaffold = _recall_scaffold(len(results), total_count, filters_used)
    proust_result = next((result for result in results if result.is_proust), None)
    _set_tool_context(
        "recall",
        {
            "fuzzy_recall_count": sum(1 for result in results if result.decay < 0.5),
            "proust_triggered": proust_result is not None,
            **(
                {
                    "proust_memory_id": proust_result.memory.id,
                    "proust_memory_decay": proust_result.decay,
                }
                if proust_result is not None
                else {}
            ),
        },
    )
    update_tool_metadata(
        fuzzy_recall_count=sum(1 for result in results if result.decay < 0.5),
        proust_triggered=proust_result is not None,
        proust_memory_id=(proust_result.memory.id if proust_result is not None else None),
        proust_memory_decay=(proust_result.decay if proust_result is not None else None),
    )
    return compose_response(data, scaffold)
