"""ego-mcp MCP server with all 16 tools."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.embedding import EgoEmbeddingFunction, create_embedding_provider
from ego_mcp.episode import EpisodeStore
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore, calculate_time_decay, count_emotions_weighted
from ego_mcp.migrations import run_migrations
from ego_mcp.relationship import RelationshipStore
from ego_mcp.scaffolds import (
    SCAFFOLD_AM_I_GENUINE,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_EMOTION_TREND,
    SCAFFOLD_FEEL_DESIRES,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render,
    render_with_data,
)
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Memory, MemorySearchResult
from ego_mcp.workspace_sync import WorkspaceMemorySync

logger = logging.getLogger(__name__)
_REMEMBER_DUPLICATE_PREFIX = "Not saved — very similar memory already exists."

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
                "n_results": {
                    "type": "integer",
                    "default": 3,
                    "description": "Number of results (default: 3, max: 10)",
                },
                "emotion_filter": {"type": "string"},
                "category_filter": {"type": "string"},
                "date_from": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
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
        name="forget",
        description=(
            "Delete a memory by ID. Returns the deleted memory's summary for "
            "confirmation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "ID of the memory to delete",
                }
            },
            "required": ["memory_id"],
        },
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
        name="emotion_trend",
        description="Analyze emotional patterns over time",
        inputSchema={"type": "object", "properties": {}, "required": []},
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


def _sanitize_tool_output_for_logging(
    name: str, args: dict[str, Any] | None, output: str
) -> str:
    """Mask sensitive values before writing tool output to logs."""
    del args
    if name != "recall":
        return output

    lines = output.splitlines()
    for idx, line in enumerate(lines[:-1]):
        if not re.match(r"^[0-9]+\. \[[^\]]+\] ", line):
            continue
        if "private" not in lines[idx + 1]:
            continue
        prefix, _sep, _rest = line.partition("] ")
        if _sep:
            lines[idx] = f"{prefix}] [REDACTED_PRIVATE_MEMORY]"
    return "\n".join(lines)


def _tool_log_context() -> dict[str, str]:
    """Attach lightweight contextual fields used by dashboard log projection."""
    body_state = get_body_state()
    time_phase = body_state.get("time_phase")
    if isinstance(time_phase, str) and time_phase:
        return {"time_phase": time_phase}
    return {}


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls."""
    safe_args = _sanitize_tool_args_for_logging(name, arguments)
    log_context = _tool_log_context()
    logger.info(
        "Tool invocation",
        extra={"tool_name": name, "tool_args": safe_args, **log_context},
    )

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
            extra={"tool_name": name, "tool_args": safe_args, **log_context},
        )
        raise

    safe_output = _sanitize_tool_output_for_logging(name, arguments, text)
    output_excerpt, output_truncated = _truncate_for_log(safe_output)
    logger.info(
        "Tool execution completed",
        extra={
            "tool_name": name,
            "tool_output": output_excerpt,
            "tool_output_chars": len(text),
            "tool_output_truncated": output_truncated,
            **log_context,
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
        result = await _handle_wake_up(config, memory, desire)
        desire.satisfy_implicit("wake_up")
        return result
    elif name == "feel_desires":
        return await _handle_feel_desires(config, memory, desire)
    elif name == "introspect":
        result = await _handle_introspect(config, memory, desire)
        desire.satisfy_implicit("introspect")
        return result
    elif name == "consider_them":
        result = await _handle_consider_them(config, memory, args)
        desire.satisfy_implicit("consider_them")
        return result
    elif name == "remember":
        result = await _handle_remember(memory, args)
        if not result.startswith(_REMEMBER_DUPLICATE_PREFIX):
            desire.satisfy_implicit("remember", category=args.get("category"))
        return result
    elif name == "recall":
        result = await _handle_recall(config, memory, args)
        desire.satisfy_implicit("recall")
        return result
    elif name == "am_i_being_genuine":
        return _handle_am_i_genuine()

    # --- Backend tools ---
    elif name == "satisfy_desire":
        return _handle_satisfy_desire(desire, args)
    elif name == "consolidate":
        result = await _handle_consolidate(memory, consolidation)
        desire.satisfy_implicit("consolidate")
        return result
    elif name == "forget":
        return await _handle_forget(memory, args)
    elif name == "link_memories":
        return await _handle_link_memories(memory, args)
    elif name == "update_relationship":
        result = _handle_update_relationship(config, args)
        desire.satisfy_implicit("update_relationship")
        return result
    elif name == "update_self":
        result = _handle_update_self(config, args)
        desire.satisfy_implicit("update_self")
        return result
    elif name == "emotion_trend":
        result = await _handle_emotion_trend(memory)
        desire.satisfy_implicit("emotion_trend")
        return result
    elif name == "get_episode":
        return await _handle_get_episode(episodes, memory, args)
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


def _relative_time(timestamp: str, now: datetime | None = None) -> str:
    """Format an ISO8601 timestamp as compact relative time (e.g. 2d ago)."""
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return "unknown time"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{max(1, seconds // 3600)}h ago"

    days = max(1, seconds // 86400)
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{max(1, days // 7)}w ago"
    if days < 365:
        return f"{max(1, days // 30)}mo ago"
    return f"{max(1, days // 365)}y ago"


def _format_recall_entry(
    index: int,
    result: MemorySearchResult,
    now: datetime | None = None,
) -> str:
    """Render a single recall result in the compact two-line format."""
    if now is None:
        now = datetime.now(timezone.utc)
    memory = result.memory
    age = _relative_time(memory.timestamp, now=now)
    content = _truncate_for_quote(memory.content, limit=70)

    emotion_label = memory.emotional_trace.primary.value
    if memory.emotional_trace.intensity >= 0.7:
        emotion_label = f"{emotion_label}({memory.emotional_trace.intensity:.1f})"

    details = [f"emotion: {emotion_label}"]
    if memory.emotional_trace.secondary:
        details.append(f"undercurrent: {memory.emotional_trace.secondary[0].value}")
    details.append(f"importance: {memory.importance}")
    details.append(f"score: {result.score:.2f}")
    if memory.is_private:
        details.append("private")

    return f"{index}. [{age}] {content}\n   {' | '.join(details)}"


def _recall_scaffold(n_shown: int, total_count: int, filters_used: list[str]) -> str:
    """Build a recall scaffold that adapts to visible results and used filters."""
    parts = ["How do these memories connect to the current moment?"]
    if n_shown < total_count:
        parts.append(f"Showing {n_shown} of ~{total_count}. Increase n_results for more.")

    all_filters = {
        "emotion_filter",
        "category_filter",
        "date_from",
        "date_to",
        "valence_range",
        "arousal_range",
    }
    if not filters_used:
        parts.append(
            "Narrow by: emotion_filter, category_filter, date_from/date_to, "
            "valence_range, arousal_range."
        )
    else:
        remaining = sorted(all_filters - set(filters_used))
        if remaining:
            parts.append(f"Also available: {', '.join(remaining)}.")

    parts.append("Need narrative detail? Use get_episode.")
    parts.append("If you found a new relation, use link_memories.")
    return "\n".join(parts)


def _parse_iso_datetime(timestamp: str) -> datetime | None:
    """Parse ISO8601 timestamp as timezone-aware datetime."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _memories_within_days(
    memories: list[Memory], days: float, now: datetime | None = None
) -> list[Memory]:
    """Return memories whose timestamps fall within the last `days` days."""
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    selected: list[Memory] = []
    for memory in memories:
        parsed = _parse_iso_datetime(getattr(memory, "timestamp", ""))
        if parsed is None:
            continue
        if parsed >= window_start:
            selected.append(memory)
    selected.sort(key=lambda m: str(getattr(m, "timestamp", "")), reverse=True)
    return selected


def _secondary_weighted_counts(memories: list[Memory]) -> dict[str, float]:
    """Count secondary emotions only, using the same 0.4 undercurrent weight."""
    counts: dict[str, float] = {}
    for memory in memories:
        for emotion in memory.emotional_trace.secondary:
            counts[emotion.value] = counts.get(emotion.value, 0.0) + 0.4
    return counts


def _valence_arousal_to_impression(avg_valence: float, avg_arousal: float) -> str:
    """Convert monthly average valence/arousal into a coarse impression phrase."""
    if avg_valence > 0.3 and avg_arousal > 0.5:
        return "an energetic, fulfilling month"
    if avg_valence > 0.3 and avg_arousal <= 0.5:
        return "a quietly content month"
    if avg_valence < -0.3 and avg_arousal > 0.5:
        return "a turbulent, unsettled month"
    if avg_valence < -0.3 and avg_arousal <= 0.5:
        return "a heavy, draining month"
    if abs(avg_valence) <= 0.3 and avg_arousal <= 0.3:
        return "a numb, uneventful month"
    return "a month of mixed feelings"


def _format_recent_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format vivid recent emotional events (~3 days)."""
    recent = _memories_within_days(memories, 3, now=now)
    lines = ["Recent (past 3 days):"]
    if not recent:
        lines.append("  - No recent emotional events in this window.")
        return "\n".join(lines)

    selected = list(recent[:3])
    peak = max(recent, key=lambda m: float(m.emotional_trace.intensity))
    if all(peak.id != item.id for item in selected):
        selected = selected[:2] + [peak]

    selected_ids = {item.id for item in selected}
    ordered_selected = [m for m in recent if m.id in selected_ids][:3]
    peak_id = peak.id
    for memory in ordered_selected:
        age = _relative_time(memory.timestamp, now=now)
        emotion = memory.emotional_trace.primary.value
        parts = [f"{emotion}"]
        if memory.id == peak_id:
            parts.append(f"peak intensity {memory.emotional_trace.intensity:.1f}")
        if memory.emotional_trace.secondary:
            parts.append(f"undercurrent: {memory.emotional_trace.secondary[0].value}")
        lines.append(
            f"  - [{age}] {_truncate_for_quote(memory.content, 70)} ({', '.join(parts)})"
        )
    return "\n".join(lines)


def _format_week_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format moderate-resolution weekly emotional trends (~7 days)."""
    week = _memories_within_days(memories, 7, now=now)
    lines = ["This week:"]
    if not week:
        lines.append("  Dominant: not enough recent data")
        return "\n".join(lines)

    weighted = count_emotions_weighted(week)
    dominant = sorted(weighted.items(), key=lambda item: item[1], reverse=True)[:2]
    if dominant:
        lines.append(
            "  Dominant: " + ", ".join(f"{name}({score:.1f})" for name, score in dominant)
        )

    secondary_counts = _secondary_weighted_counts(week)
    if secondary_counts:
        under_name, under_score = max(secondary_counts.items(), key=lambda item: item[1])
        lines.append(f"  Undercurrent: {under_name}({under_score:.1f})")

    chronological = sorted(week, key=lambda m: str(m.timestamp))
    if chronological:
        first_emotion = chronological[0].emotional_trace.primary.value
        last_emotion = chronological[-1].emotional_trace.primary.value
        lines.append(f"  Shift: {first_emotion} -> {last_emotion}")

    run_emotion = ""
    run_length = 0
    cluster_emotion: str | None = None
    for memory in chronological:
        current = memory.emotional_trace.primary.value
        if current == run_emotion:
            run_length += 1
        else:
            run_emotion = current
            run_length = 1
        if run_length >= 3:
            cluster_emotion = current
            break
    if cluster_emotion:
        lines.append(f"  ! Cluster detected: {cluster_emotion} repeated 3+ times")

    return "\n".join(lines)


def _format_month_emotion_layer(memories: list[Memory], now: datetime) -> str:
    """Format impressionistic monthly emotional summary (~30 days)."""
    month = _memories_within_days(memories, 30, now=now)
    lines = ["This month (impressionistic):"]
    if not month:
        lines.append("  Tone: not enough monthly data")
        return "\n".join(lines)

    avg_valence = sum(m.emotional_trace.valence for m in month) / len(month)
    avg_arousal = sum(m.emotional_trace.arousal for m in month) / len(month)
    lines.append(f"  Tone: {_valence_arousal_to_impression(avg_valence, avg_arousal)}.")

    peak = max(month, key=lambda m: float(m.emotional_trace.intensity))
    end = month[0]  # list_recent order is newest-first; helper preserves desc
    lines.append(f"  Peak: {_truncate_for_quote(peak.content, 70)}")
    lines.append(f"  End: {_truncate_for_quote(end.content, 70)}")

    week_primarys = {
        m.emotional_trace.primary.value for m in _memories_within_days(memories, 7, now=now)
    }
    month_counts = Counter(m.emotional_trace.primary.value for m in month)
    fading_emotion = next(
        (
            emotion
            for emotion, _count in month_counts.most_common()
            if emotion not in week_primarys
        ),
        None,
    )
    candidate_decay = 1.0
    if fading_emotion:
        candidate_memories = [
            m for m in month if m.emotional_trace.primary.value == fading_emotion
        ]
        if candidate_memories:
            candidate_decay = sum(
                calculate_time_decay(m.timestamp, now=now) for m in candidate_memories
            ) / len(candidate_memories)
    if fading_emotion and candidate_decay <= 0.5:
        lines.append(
            f"  [fading] {fading_emotion} appears mostly in older memories and is fading."
        )

    return "\n".join(lines)


def _self_model_store_for_memory(memory: MemoryStore) -> SelfModelStore:
    """Create a self-model store using the same configured data directory as memory."""
    return SelfModelStore(memory.data_dir / "self_model.json")


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity for embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _fading_or_dormant_questions(
    memory: MemoryStore, store: SelfModelStore | None = None
) -> list[dict[str, Any]]:
    """Return unresolved questions that are no longer fully active (salience <= 0.3)."""
    model_store = store or _self_model_store_for_memory(memory)
    return [
        q
        for q in model_store.get_unresolved_questions_with_salience()
        if float(q.get("salience", 0.0)) <= 0.3
    ]


def _fading_important_questions(
    memory: MemoryStore, store: SelfModelStore | None = None
) -> list[dict[str, Any]]:
    """Return fading (not dormant) high-importance unresolved questions."""
    model_store = store or _self_model_store_for_memory(memory)
    return [
        q
        for q in model_store.get_unresolved_questions_with_salience()
        if 0.1 < float(q.get("salience", 0.0)) <= 0.3
        and int(q.get("importance", 3)) >= 4
    ]


def _find_related_forgotten_questions(
    memory: MemoryStore,
    content: str,
    *,
    threshold: float = 0.4,
    max_candidates: int = 10,
    candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Find fading/dormant unresolved questions semantically related to new content."""
    source_candidates = candidates if candidates is not None else _fading_or_dormant_questions(memory)
    filtered = [
        q for q in source_candidates if isinstance(q.get("question"), str) and q.get("question")
    ][:max_candidates]
    if not filtered:
        return []

    try:
        content_embedding = memory.embed([content])[0]
        question_texts = [str(q["question"]) for q in filtered]
        question_embeddings = memory.embed(question_texts)
    except Exception as exc:
        logger.warning("Question relevance embedding failed: %s", exc)
        return []

    related: list[dict[str, Any]] = []
    for question, embedding in zip(filtered, question_embeddings):
        similarity = _cosine_similarity(content_embedding, embedding)
        if similarity > threshold:
            salience = float(question.get("salience", 0.0))
            band = "dormant" if salience <= 0.1 else "fading"
            related.append({**question, "trigger_similarity": similarity, "band": band})

    related.sort(key=lambda q: float(q.get("trigger_similarity", 0.0)), reverse=True)
    return related


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
    *,
    fading_important_questions: list[dict[str, Any]] | None = None,
    recent_memories: list[Memory] | None = None,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Infer transient desire modifiers from recent memory context."""
    recent = recent_memories if recent_memories is not None else await memory.list_recent(n=30)
    context_boosts: dict[str, float] = {}
    fading_important = (
        fading_important_questions
        if fading_important_questions is not None
        else _fading_important_questions(memory)
    )
    if not recent:
        if fading_important:
            context_boosts["cognitive_coherence"] = min(
                0.12, len(fading_important) * 0.04
            )
        return context_boosts, {}, {}

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

    anxious_count = sum(1 for m in recent if m.emotional_trace.primary.value == "anxious")
    if anxious_count >= 2:
        anxious_boost = min(0.10, anxious_count * 0.03)
        emotional_modulation["cognitive_coherence"] = (
            emotional_modulation.get("cognitive_coherence", 0.0) + anxious_boost
        )
        emotional_modulation["social_thirst"] = (
            emotional_modulation.get("social_thirst", 0.0) + min(0.08, anxious_count * 0.02)
        )

    if fading_important:
        context_boosts["cognitive_coherence"] = (
            context_boosts.get("cognitive_coherence", 0.0)
            + min(0.12, len(fading_important) * 0.04)
        )

    surprise_strength = max(
        (
            m.emotional_trace.intensity
            for m in recent
            if m.emotional_trace.primary.value in {"surprised", "excited", "frustrated"}
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
    self_store = SelfModelStore(config.data_dir / "self_model.json")
    fading_questions = _fading_important_questions(memory, store=self_store)
    (
        context_boosts,
        emotional_modulation,
        prediction_error,
    ) = await _derive_desire_modulation(
        memory,
        fading_important_questions=fading_questions,
    )
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

    scaffold = render(SCAFFOLD_FEEL_DESIRES, config.companion_name)
    if levels.get("cognitive_coherence", 0.0) >= 0.6 and fading_questions:
        scaffold += (
            "\nSomething feels unresolved. You can't quite name it, but there's a nagging feeling.\n"
            "Consider running introspect to see if anything surfaces."
        )
    return compose_response(data, scaffold)


async def _handle_introspect(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    """Introspection materials: memories + desires + self/relationship cues."""
    recent_all = await memory.list_recent(n=30)
    recent = recent_all[:3]
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
    fading_questions = _fading_important_questions(memory, store=self_store)
    (
        introspect_context_boosts,
        introspect_emotional_modulation,
        introspect_prediction_error,
    ) = await _derive_desire_modulation(
        memory,
        fading_important_questions=fading_questions,
        recent_memories=recent_all,
    )
    introspect_levels = desire.compute_levels_with_modulation(
        context_boosts=introspect_context_boosts,
        emotional_modulation=introspect_emotional_modulation,
        prediction_error=introspect_prediction_error,
    )
    coherence_level = float(introspect_levels.get("cognitive_coherence", 0.0))
    self_model = self_store.get()
    goals = (
        ", ".join(self_model.current_goals[:2]) if self_model.current_goals else "none"
    )
    self_summary = (
        f"Self model: confidence={self_model.confidence_calibration:.2f}, goals={goals}"
    )
    if self_model.last_updated:
        self_summary += f", last_updated={self_model.last_updated[:10]}"

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


def _infer_topics_from_memories(memories: list[Memory]) -> tuple[list[str], list[str]]:
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
        age = _relative_time(duplicate_of.memory.timestamp)
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
    sync = _get_workspace_sync()
    sync_note = ""
    if sync is not None and not mem.is_private:
        try:
            sync_result = sync.sync_memory(mem)
            if sync_result.latest_monologue_updated:
                sync_note = " Synced latest introspection to workspace."
            elif sync_result.daily_updated or sync_result.curated_updated:
                sync_note = " Synced to workspace memory logs."
        except OSError as exc:
            logger.warning("Workspace sync failed: %s", exc)

    top_links = sorted(linked_results, key=lambda r: r.distance)[:3]
    if top_links:
        link_lines = ["Most related:"]
        for linked_result in top_links:
            age = _relative_time(linked_result.memory.timestamp)
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

    data = (
        f"Saved (id: {mem.id}). Linked to {num_links} existing memories.{sync_note}\n"
        f"{link_section}{forgotten_section}"
    )
    scaffold = "Do any of these connections surprise you? Is there a pattern forming?"
    return compose_response(data, scaffold)


async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    """Recall memories by context."""
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

    sync = _get_workspace_sync()
    sync_note = ""
    if sync is not None and not deleted.is_private:
        try:
            removed = sync.remove_memory(memory_id)
            if removed:
                sync_note = "\nWorkspace sync: removed matching entries from memory logs."
        except OSError as exc:
            logger.warning("Workspace memory removal failed: %s", exc)

    age = _relative_time(deleted.timestamp)
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
    run_migrations(config.data_dir)

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
