"""ego-mcp MCP server with all 15 tools."""

from __future__ import annotations

from collections import Counter
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.embedding import EgoEmbeddingFunction, create_embedding_provider
from ego_mcp.episode import EpisodeStore
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore
from ego_mcp.relationship import RelationshipStore
from ego_mcp.scaffolds import (
    SCAFFOLD_AM_I_GENUINE,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_FEEL_DESIRES,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_RECALL,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render_with_data,
)
from ego_mcp.self_model import SelfModelStore
from ego_mcp.workspace_sync import WorkspaceMemorySync

logger = logging.getLogger(__name__)

server = Server("ego-mcp")

# --- Global state (initialized in main()) ---
_config: EgoConfig | None = None
_memory: MemoryStore | None = None
_desire: DesireEngine | None = None
_episodes: EpisodeStore | None = None
_consolidation: ConsolidationEngine | None = None
_workspace_sync: WorkspaceMemorySync | None = None


def _get_config() -> EgoConfig:
    assert _config is not None, "Server not initialized"
    return _config


def _get_memory() -> MemoryStore:
    assert _memory is not None, "Server not initialized"
    return _memory


def _get_desire() -> DesireEngine:
    assert _desire is not None, "Server not initialized"
    return _desire


def _get_episodes() -> EpisodeStore:
    assert _episodes is not None, "Server not initialized"
    return _episodes


def _get_consolidation() -> ConsolidationEngine:
    assert _consolidation is not None, "Server not initialized"
    return _consolidation


def _get_workspace_sync() -> WorkspaceMemorySync | None:
    return _workspace_sync


# =====================================================================
#  Tool Definitions
# =====================================================================

SURFACE_TOOLS: list[Tool] = [
    Tool(
        name="wake_up",
        description="Start a new session. Returns last introspection and desire summary.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="feel_desires",
        description="Check current desire levels and get guidance on what to do.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="introspect",
        description="Get materials for self-reflection: recent memories, desires, open questions.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="consider_them",
        description="Think about someone. Returns relationship summary and ToM framework.",
        inputSchema={
            "type": "object",
            "properties": {
                "person": {
                    "type": "string",
                    "description": "Name of person to consider",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="remember",
        description="Save a memory with emotion and importance.",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "emotion": {"type": "string", "default": "neutral"},
                "secondary": {"type": "array", "items": {"type": "string"}},
                "intensity": {"type": "number", "default": 0.5},
                "importance": {"type": "integer", "default": 3},
                "category": {"type": "string", "default": "daily"},
                "valence": {"type": "number", "default": 0.0},
                "arousal": {"type": "number", "default": 0.5},
                "body_state": {"type": "object"},
                "private": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, keep this memory internal and skip workspace sync."
                    ),
                },
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="recall",
        description="Recall related memories by context.",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "What to recall"},
                "n_results": {"type": "integer", "default": 3},
                "emotion_filter": {"type": "string"},
                "category_filter": {"type": "string"},
                "valence_range": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "arousal_range": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "required": ["context"],
        },
    ),
    Tool(
        name="am_i_being_genuine",
        description="Check if your response is authentic.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

BACKEND_TOOLS: list[Tool] = [
    Tool(
        name="satisfy_desire",
        description="Mark a desire as satisfied",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "quality": {"type": "number", "default": 0.7},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="consolidate",
        description="Run memory consolidation",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="link_memories",
        description="Link two memories",
        inputSchema={
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "target_id": {"type": "string"},
                "link_type": {"type": "string", "default": "related"},
            },
            "required": ["source_id", "target_id"],
        },
    ),
    Tool(
        name="update_relationship",
        description="Update relationship model",
        inputSchema={
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "field": {"type": "string"},
                "value": {},
            },
            "required": ["person", "field", "value"],
        },
    ),
    Tool(
        name="update_self",
        description="Update self model",
        inputSchema={
            "type": "object",
            "properties": {
                "field": {"type": "string"},
                "value": {},
            },
            "required": ["field", "value"],
        },
    ),
    Tool(
        name="search_memories",
        description="Search memories with filters",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "emotion_filter": {"type": "string"},
                "category_filter": {"type": "string"},
                "date_from": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_episode",
        description="Get episode details",
        inputSchema={
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
            },
            "required": ["episode_id"],
        },
    ),
    Tool(
        name="create_episode",
        description="Create episode from memories",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "summary": {"type": "string"},
            },
            "required": ["memory_ids", "summary"],
        },
    ),
]


@server.list_tools()  # type: ignore[untyped-decorator,no-untyped-call]
async def list_tools() -> list[Tool]:
    """Return all available tools."""
    return SURFACE_TOOLS + BACKEND_TOOLS


def _sanitize_tool_args_for_logging(
    name: str, args: dict[str, Any] | None
) -> dict[str, Any]:
    """Mask sensitive values before writing tool arguments to logs."""
    if args is None:
        return {}

    safe_args = dict(args)
    if name == "remember" and bool(safe_args.get("private", False)):
        content = safe_args.get("content")
        if isinstance(content, str):
            safe_args["content_length"] = len(content)
        safe_args["content"] = "[REDACTED_PRIVATE_MEMORY]"
        for key in ("secondary", "body_state", "tags"):
            if key in safe_args:
                safe_args[key] = "[REDACTED_PRIVATE_FIELD]"
    return safe_args


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls."""
    safe_args = _sanitize_tool_args_for_logging(name, arguments)
    logger.info("Tool invocation", extra={"tool_name": name, "tool_args": safe_args})

    config = _get_config()
    memory = _get_memory()
    desire = _get_desire()
    episodes = _get_episodes()
    consolidation = _get_consolidation()

    try:
        text = await _dispatch(
            name, arguments, config, memory, desire, episodes, consolidation
        )
    except Exception:
        logger.exception(
            "Tool execution failed",
            extra={"tool_name": name, "tool_args": safe_args},
        )
        raise

    output_excerpt, output_truncated = _truncate_for_log(text)
    logger.info(
        "Tool execution completed",
        extra={
            "tool_name": name,
            "tool_output": output_excerpt,
            "tool_output_chars": len(text),
            "tool_output_truncated": output_truncated,
        },
    )
    return [TextContent(type="text", text=text)]


async def _dispatch(
    name: str,
    args: dict[str, Any],
    config: EgoConfig,
    memory: MemoryStore,
    desire: DesireEngine,
    episodes: EpisodeStore,
    consolidation: ConsolidationEngine,
) -> str:
    """Route tool call to handler."""
    safe_args = _sanitize_tool_args_for_logging(name, args)
    logger.debug("Routing tool call", extra={"tool_name": name, "tool_args": safe_args})

    # --- Surface tools ---
    if name == "wake_up":
        return await _handle_wake_up(config, memory, desire)
    elif name == "feel_desires":
        return await _handle_feel_desires(config, memory, desire)
    elif name == "introspect":
        return await _handle_introspect(config, memory, desire)
    elif name == "consider_them":
        return await _handle_consider_them(config, memory, args)
    elif name == "remember":
        return await _handle_remember(memory, args)
    elif name == "recall":
        return await _handle_recall(config, memory, args)
    elif name == "am_i_being_genuine":
        return _handle_am_i_genuine()

    # --- Backend tools ---
    elif name == "satisfy_desire":
        return _handle_satisfy_desire(desire, args)
    elif name == "consolidate":
        return await _handle_consolidate(memory, consolidation)
    elif name == "link_memories":
        return await _handle_link_memories(memory, args)
    elif name == "update_relationship":
        return _handle_update_relationship(config, args)
    elif name == "update_self":
        return _handle_update_self(config, args)
    elif name == "search_memories":
        return await _handle_search_memories(memory, args)
    elif name == "get_episode":
        return await _handle_get_episode(episodes, args)
    elif name == "create_episode":
        return await _handle_create_episode(episodes, args)
    else:
        return f"Unknown tool: {name}"


# =====================================================================
#  Surface Tool Handlers
# =====================================================================


def _truncate_for_quote(text: str, limit: int = 220) -> str:
    """Trim long text snippets for concise tool responses."""
    compact = " ".join(text.split()).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _truncate_for_log(text: str, limit: int = 1200) -> tuple[str, bool]:
    """Trim long tool outputs for logs while keeping metadata."""
    compact = text.strip()
    if len(compact) <= limit:
        return compact, False
    return compact[: limit - 3].rstrip() + "...", True


async def _relationship_snapshot(
    config: EgoConfig, memory: MemoryStore, person: str
) -> str:
    """Build a compact relationship summary line for surface tools."""
    store = _relationship_store(config)
    rel = store.get(person)
    frequency, dominant_tone, _, _ = await _summarize_conversation_tendency(
        memory, person
    )
    parts = [
        f"{person}: trust={rel.trust_level:.2f}",
        f"interactions={rel.total_interactions}",
        f"shared_episodes={len(rel.shared_episode_ids)}",
        f"dominant_tone={dominant_tone}",
    ]
    if rel.last_interaction:
        parts.append(f"last_interaction={rel.last_interaction[:10]}")
    parts.append(f"recent_frequency={frequency}")
    return ", ".join(parts)


async def _derive_desire_modulation(
    memory: MemoryStore,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Infer transient desire modifiers from recent memory context."""
    recent = await memory.list_recent(n=30)
    if not recent:
        return {}, {}, {}

    context_boosts: dict[str, float] = {}
    emotional_modulation: dict[str, float] = {}
    prediction_error: dict[str, float] = {}

    categories = Counter(m.category.value for m in recent)
    if categories.get("technical", 0) >= 3:
        context_boosts["pattern_seeking"] = (
            context_boosts.get("pattern_seeking", 0.0) + 0.08
        )
        context_boosts["predictability"] = (
            context_boosts.get("predictability", 0.0) + 0.06
        )
    if categories.get("introspection", 0) >= 2:
        context_boosts["cognitive_coherence"] = (
            context_boosts.get("cognitive_coherence", 0.0) + 0.07
        )
    if categories.get("conversation", 0) >= 3:
        context_boosts["resonance"] = context_boosts.get("resonance", 0.0) + 0.06
        context_boosts["social_thirst"] = (
            context_boosts.get("social_thirst", 0.0) - 0.04
        )

    valences = [m.emotional_trace.valence for m in recent]
    avg_valence = sum(valences) / len(valences)
    if avg_valence <= -0.2:
        emotional_modulation["social_thirst"] = (
            emotional_modulation.get("social_thirst", 0.0) + 0.10
        )
        emotional_modulation["cognitive_coherence"] = (
            emotional_modulation.get("cognitive_coherence", 0.0) + 0.07
        )
    elif avg_valence >= 0.2:
        emotional_modulation["curiosity"] = (
            emotional_modulation.get("curiosity", 0.0) + 0.06
        )
        emotional_modulation["expression"] = (
            emotional_modulation.get("expression", 0.0) + 0.04
        )

    surprise_strength = max(
        (
            m.emotional_trace.intensity
            for m in recent
            if m.emotional_trace.primary.value in {"surprised", "excited"}
        ),
        default=0.0,
    )
    if surprise_strength > 0.0:
        prediction_error["curiosity"] = min(0.20, 0.06 + surprise_strength * 0.14)

    return context_boosts, emotional_modulation, prediction_error


async def _handle_wake_up(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Session start: last introspection + desires + relationship summary."""
    sync = _get_workspace_sync()
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

    desire_summary = desire.format_summary()
    relationship_line = await _relationship_snapshot(
        config, memory, config.companion_name
    )

    parts = [intro_line, f"\nDesires: {desire_summary}", relationship_line]
    data = "\n".join(parts)

    return render_with_data(data, SCAFFOLD_WAKE_UP, config.companion_name)


async def _handle_feel_desires(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Check desire levels with scaffold."""
    (
        context_boosts,
        emotional_modulation,
        prediction_error,
    ) = await _derive_desire_modulation(memory)
    levels = desire.compute_levels_with_modulation(
        context_boosts=context_boosts,
        emotional_modulation=emotional_modulation,
        prediction_error=prediction_error,
    )
    body_state = get_body_state()
    phase = body_state.get("time_phase", "unknown")
    load = body_state.get("system_load", "unknown")

    if phase == "late_night":
        levels["cognitive_coherence"] = min(
            1.0, levels.get("cognitive_coherence", 0.0) + 0.1
        )
        levels["social_thirst"] = max(0.0, levels.get("social_thirst", 0.0) - 0.1)
    elif phase == "morning":
        levels["curiosity"] = min(1.0, levels.get("curiosity", 0.0) + 0.05)

    if load == "high":
        levels = {
            name: round(max(0.0, min(1.0, level * 0.9)), 3)
            for name, level in levels.items()
        }

    sorted_desires = sorted(levels.items(), key=lambda x: -x[1])

    def tag(level: float) -> str:
        if level >= 0.7:
            return "high"
        elif level >= 0.4:
            return "mid"
        else:
            return "low"

    lines = [f"{name}[{level:.1f}/{tag(level)}]" for name, level in sorted_desires]
    data = " ".join(lines)

    return render_with_data(data, SCAFFOLD_FEEL_DESIRES, config.companion_name)


async def _handle_introspect(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Introspection materials: memories + desires + self/relationship cues."""
    recent = await memory.list_recent(n=3)
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

    desire_summary = desire.format_summary()
    self_store = SelfModelStore(config.data_dir / "self_model.json")
    self_model = self_store.get()
    goals = (
        ", ".join(self_model.current_goals[:2]) if self_model.current_goals else "none"
    )
    self_summary = (
        f"Self model: confidence={self_model.confidence_calibration:.2f}, goals={goals}"
    )
    if self_model.last_updated:
        self_summary += f", last_updated={self_model.last_updated[:10]}"

    if self_model.unresolved_questions:
        questions = "\n".join(f"- {q}" for q in self_model.unresolved_questions[:3])
        open_questions = f"Unresolved questions:\n{questions}"
    else:
        open_questions = "No unresolved questions yet."

    recent_all = await memory.list_recent(n=30)
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

    relationship_summary = await _relationship_snapshot(
        config, memory, config.companion_name
    )

    parts = [
        memory_section,
        f"\nDesires: {desire_summary}",
        self_summary,
        relationship_summary,
        open_questions,
        trend,
    ]
    data = "\n".join(parts)

    return render_with_data(data, SCAFFOLD_INTROSPECT, config.companion_name)


def _relationship_store(config: EgoConfig) -> RelationshipStore:
    return RelationshipStore(config.data_dir / "relationships" / "models.json")


async def _summarize_conversation_tendency(
    memory: MemoryStore, person: str
) -> tuple[str, str, list[str], list[str]]:
    conversations = await memory.list_recent(n=200, category_filter="conversation")
    person_lc = person.lower()

    filtered = [m for m in conversations if person_lc in m.content.lower()]
    pool = filtered if filtered else conversations
    if not pool:
        return "no recent conversation memories", "unknown tone", [], []

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)

    last_7d = 0
    tones: dict[str, int] = {}
    for mem in pool:
        tone = mem.emotional_trace.primary.value
        tones[tone] = tones.get(tone, 0) + 1
        try:
            ts = datetime.fromisoformat(mem.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= window_start:
                last_7d += 1
        except ValueError:
            continue

    dominant_tone = max(tones.items(), key=lambda x: x[1])[0]
    frequency = (
        f"{last_7d} mentions in last 7d"
        if filtered
        else f"{last_7d} conversations in last 7d"
    )
    preferred_topics, sensitive_topics = _infer_topics_from_memories(pool)
    return frequency, dominant_tone, preferred_topics, sensitive_topics


def _infer_topics_from_memories(memories: list[Any]) -> tuple[list[str], list[str]]:
    """Infer coarse preferred/sensitive topics from conversation memories."""
    topic_keywords: dict[str, tuple[str, ...]] = {
        "technical": ("code", "config", "test", "bug", "mcp", "deploy", "python"),
        "planning": ("plan", "schedule", "deadline", "priority", "roadmap"),
        "relationship": ("feel", "thanks", "support", "help", "trust"),
        "learning": ("learn", "research", "explore", "curious", "study"),
    }
    counts: Counter[str] = Counter()
    sensitive_counts: Counter[str] = Counter()

    for m in memories:
        content = m.content.lower()
        is_sensitive_mood = (
            m.emotional_trace.primary.value == "sad" or m.emotional_trace.valence < -0.3
        )
        for topic, keywords in topic_keywords.items():
            if any(keyword in content for keyword in keywords):
                counts[topic] += 1
                if is_sensitive_mood:
                    sensitive_counts[topic] += 1

    preferred_topics = [topic for topic, count in counts.most_common(3) if count > 0]
    sensitive_topics = [
        topic for topic, count in sensitive_counts.most_common(2) if count > 0
    ]
    return preferred_topics, sensitive_topics


async def _handle_consider_them(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """ToM: relationship summary + scaffold."""
    person = args.get("person", config.companion_name)
    store = _relationship_store(config)
    (
        frequency,
        dominant_tone,
        preferred_topics,
        sensitive_topics,
    ) = await _summarize_conversation_tendency(memory, person)

    now_iso = datetime.now(timezone.utc).isoformat()
    if dominant_tone != "unknown tone":
        store.add_interaction(person, now_iso, dominant_tone)
    rel = store.apply_tom_feedback(
        person_id=person,
        dominant_tone=dominant_tone,
        preferred_topics=preferred_topics,
        sensitive_topics=sensitive_topics,
    )

    relationship_summary = (
        f"{person}: trust={rel.trust_level:.2f}, "
        f"interactions={rel.total_interactions}, "
        f"shared_episodes={len(rel.shared_episode_ids)}"
    )
    if rel.preferred_topics:
        relationship_summary += (
            f", preferred_topics={','.join(rel.preferred_topics[:2])}"
        )
    if rel.sensitive_topics:
        relationship_summary += (
            f", sensitive_topics={','.join(rel.sensitive_topics[:2])}"
        )
    if rel.last_interaction:
        relationship_summary += f", last_interaction={rel.last_interaction[:10]}"

    tendency = f"Recent dialog tendency: {frequency}, dominant tone={dominant_tone}"
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
    return render_with_data(data, SCAFFOLD_CONSIDER_THEM, config.companion_name)


async def _handle_remember(memory: MemoryStore, args: dict[str, Any]) -> str:
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
    body_state = args.get("body_state") or get_body_state()

    mem, num_links = await memory.save_with_auto_link(
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
    sync = _get_workspace_sync()
    sync_note = ""
    if sync is not None and not mem.is_private:
        try:
            result = sync.sync_memory(mem)
            if result.latest_monologue_updated:
                sync_note = " Synced latest introspection to workspace."
            elif result.daily_updated or result.curated_updated:
                sync_note = " Synced to workspace memory logs."
        except OSError as exc:
            logger.warning("Workspace sync failed: %s", exc)

    return f"Saved (id: {mem.id}). Linked to {num_links} existing memories.{sync_note}"


async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """Recall memories by context."""
    context = args["context"]
    n_results = args.get("n_results", 3)
    emotion_filter = args.get("emotion_filter")
    category_filter = args.get("category_filter")
    valence_range = args.get("valence_range")
    arousal_range = args.get("arousal_range")

    if emotion_filter or category_filter:
        results = await memory.search(
            context,
            n_results=n_results,
            emotion_filter=emotion_filter,
            category_filter=category_filter,
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

    if not results:
        data = "No related memories found."
    else:
        lines = [f"{len(results)} related memories:"]
        for i, r in enumerate(results, 1):
            m = r.memory
            ts = m.timestamp[:10] if len(m.timestamp) >= 10 else m.timestamp
            emotion = m.emotional_trace.primary.value
            private_flag = "true" if m.is_private else "false"
            content = m.content[:80] + "..." if len(m.content) > 80 else m.content
            lines.append(
                f"{i}. [{ts}] {content} (emotion: {emotion}, private: {private_flag})"
            )
        data = "\n".join(lines)

    return render_with_data(data, SCAFFOLD_RECALL, config.companion_name)


def _handle_am_i_genuine() -> str:
    """Authenticity check with consistent data+scaffold format."""
    data = "Self-check triggered."
    return compose_response(data, SCAFFOLD_AM_I_GENUINE)


# =====================================================================
#  Backend Tool Handlers
# =====================================================================


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
    d = stats.to_dict()
    return (
        f"Consolidation complete. "
        f"Replayed {d['replay_events']} events, "
        f"updated {d['coactivation_updates']} co-activations, "
        f"created {d['link_updates']} links, "
        f"refreshed {d['refreshed_memories']} memories."
    )


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
    field_name = args["field"]
    value = args["value"]
    store = _relationship_store(config)
    store.update(person, {field_name: value})
    return f"Updated {person}.{field_name}"


def _handle_update_self(config: EgoConfig, args: dict[str, Any]) -> str:
    """Update self model."""
    field_name = args["field"]
    value = args["value"]
    store = SelfModelStore(config.data_dir / "self_model.json")
    store.update({field_name: value})
    return f"Updated self.{field_name}"


async def _handle_search_memories(memory: MemoryStore, args: dict[str, Any]) -> str:
    """Search memories with filters including date range."""
    query = args["query"]
    emotion_filter = args.get("emotion_filter")
    category_filter = args.get("category_filter")
    date_from = args.get("date_from")
    date_to = args.get("date_to")

    results = await memory.search(
        query,
        n_results=10,
        emotion_filter=emotion_filter,
        category_filter=category_filter,
        date_from=date_from,
        date_to=date_to,
    )

    if not results:
        return "No memories found."

    lines = [f"Found {len(results)} memories:"]
    for i, r in enumerate(results, 1):
        m = r.memory
        ts = m.timestamp[:10] if len(m.timestamp) >= 10 else m.timestamp
        content = m.content[:60] + "..." if len(m.content) > 60 else m.content
        private_flag = "true" if m.is_private else "false"
        lines.append(
            f"{i}. [{ts}] {content} (score: {r.score:.3f}, private: {private_flag})"
        )
    return "\n".join(lines)


async def _handle_get_episode(episodes: EpisodeStore, args: dict[str, Any]) -> str:
    """Get episode details."""
    episode_id = args["episode_id"]
    ep = await episodes.get_by_id(episode_id)
    if ep is None:
        return f"Episode not found: {episode_id}"
    return (
        f"Episode: {ep.id}\n"
        f"Summary: {ep.summary}\n"
        f"Memories: {len(ep.memory_ids)}\n"
        f"Period: {ep.start_time} → {ep.end_time}\n"
        f"Importance: {ep.importance}"
    )


async def _handle_create_episode(episodes: EpisodeStore, args: dict[str, Any]) -> str:
    """Create episode from memories."""
    memory_ids = args["memory_ids"]
    summary = args["summary"]
    ep = await episodes.create(memory_ids=memory_ids, summary=summary)
    return f"Created episode {ep.id} with {len(ep.memory_ids)} memories."


# =====================================================================
#  Server Startup
# =====================================================================


def init_server(config: EgoConfig | None = None) -> None:
    """Initialize all dependencies. Called from main() or tests."""
    global _config, _memory, _desire, _episodes, _consolidation, _workspace_sync

    if config is None:
        config = EgoConfig.from_env()

    if _memory is not None:
        _memory.close()

    _config = config

    config.data_dir.mkdir(parents=True, exist_ok=True)

    provider = create_embedding_provider(config)
    embedding_fn = EgoEmbeddingFunction(provider)

    _memory = MemoryStore(config, embedding_fn)
    _memory.connect()

    _desire = DesireEngine(config.data_dir / "desires.json")

    # Initialize episode store using the same vector-store client as memories.
    client = _memory.get_client()
    episodes_collection = client.get_or_create_collection(
        name="ego_episodes",
        embedding_function=cast(Any, embedding_fn),
    )
    _episodes = EpisodeStore(_memory, episodes_collection)

    _consolidation = ConsolidationEngine()
    _workspace_sync = WorkspaceMemorySync.from_optional_path(config.workspace_dir)


async def main() -> None:
    """Start the ego-mcp server."""
    print("Starting ego-mcp server...")
    init_server()
    async with stdio_server() as (read_stream, write_stream):
        initialization_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization_options)
