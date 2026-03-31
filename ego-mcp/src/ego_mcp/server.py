"""ego-mcp MCP server entrypoint and runtime wiring."""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import ego_mcp._server_handlers as _handlers
from ego_mcp._server_backend_handlers import (
    pop_tool_context as pop_backend_tool_context,
)
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_memory import pop_tool_context as pop_memory_tool_context
from ego_mcp._server_tools import BACKEND_TOOLS, SURFACE_TOOLS
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.desire_catalog import DesireConfigurationError
from ego_mcp.embedding import EgoEmbeddingFunction, create_embedding_provider
from ego_mcp.episode import EpisodeStore
from ego_mcp.impulse import ImpulseManager
from ego_mcp.interoception import get_body_state
from ego_mcp.memory import MemoryStore, calculate_time_decay
from ego_mcp.migrations import run_migrations
from ego_mcp.notion import NotionStore
from ego_mcp.types import Memory
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
_notions: NotionStore | None = None
_impulse: ImpulseManager | None = None

# --- Re-exported handler/helper symbols for compatibility with tests ---
_REMEMBER_DUPLICATE_PREFIX = _handlers._REMEMBER_DUPLICATE_PREFIX
_truncate_for_quote = _handlers._truncate_for_quote
_truncate_for_log = _handlers._truncate_for_log
_relative_time = _handlers._relative_time
_format_recall_entry = _handlers._format_recall_entry
_recall_scaffold = _handlers._recall_scaffold
_parse_iso_datetime = _handlers._parse_iso_datetime
_memories_within_days = _handlers._memories_within_days
_secondary_weighted_counts = _handlers._secondary_weighted_counts
_valence_arousal_to_impression = _handlers._valence_arousal_to_impression
_format_recent_emotion_layer = _handlers._format_recent_emotion_layer
_format_week_emotion_layer = _handlers._format_week_emotion_layer
_format_month_emotion_layer = _handlers._format_month_emotion_layer
_self_model_store_for_memory = _handlers._self_model_store_for_memory
_cosine_similarity = _handlers._cosine_similarity
_fading_or_dormant_questions = _handlers._fading_or_dormant_questions
_fading_important_questions = _handlers._fading_important_questions
_find_related_forgotten_questions = _handlers._find_related_forgotten_questions
_relationship_store = _handlers._relationship_store
_summarize_conversation_tendency = _handlers._summarize_conversation_tendency
_infer_topics_from_memories = _handlers._infer_topics_from_memories
_relationship_snapshot = _handlers._relationship_snapshot
_derive_desire_modulation = _handlers._derive_desire_modulation


def _sync_handler_overrides() -> None:
    """Propagate server-module monkeypatches into handler module symbols."""
    _handlers.configure_test_overrides(
        relative_time=_relative_time,
        relationship_snapshot=_relationship_snapshot,
        derive_desire_modulation=_derive_desire_modulation,
        get_body_state=get_body_state,
        calculate_time_decay=calculate_time_decay,
    )


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


_handlers.configure_runtime_accessors(
    workspace_sync_getter=_get_workspace_sync,
    episodes_getter=_get_episodes,
    notion_store_getter=lambda: _get_notion_store(),
    impulse_manager_getter=lambda: _get_impulse_manager(),
)


def _get_notion_store() -> NotionStore:
    assert _notions is not None, "Server not initialized"
    return _notions


def _get_impulse_manager() -> ImpulseManager:
    assert _impulse is not None, "Server not initialized"
    return _impulse


async def _handle_wake_up(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_wake_up(config, memory, desire)


async def _handle_feel_desires(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_feel_desires(config, memory, desire)


async def _handle_introspect(
    config: EgoConfig, memory: MemoryStore, desire: DesireEngine
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_introspect(config, memory, desire)


async def _handle_consider_them(
    config: EgoConfig,
    memory: MemoryStore,
    args: dict[str, Any],
    desire: DesireEngine | None = None,
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_consider_them(config, memory, args, desire)


async def _handle_remember(
    config: EgoConfig,
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_remember(config, memory, args)


async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_recall(config, memory, args)


def _handle_am_i_genuine() -> str:
    return _handlers._handle_am_i_genuine()


def _handle_satisfy_desire(desire: DesireEngine, args: dict[str, Any]) -> str:
    return _handlers._handle_satisfy_desire(desire, args)


async def _handle_consolidate(
    memory: MemoryStore, consolidation: ConsolidationEngine
) -> str:
    return await _handlers._handle_consolidate(memory, consolidation)


async def _handle_forget(memory: MemoryStore, args: dict[str, Any]) -> str:
    return await _handlers._handle_forget(memory, args)


async def _handle_link_memories(memory: MemoryStore, args: dict[str, Any]) -> str:
    return await _handlers._handle_link_memories(memory, args)


def _handle_update_relationship(config: EgoConfig, args: dict[str, Any]) -> str:
    return _handlers._handle_update_relationship(config, args)


def _handle_update_self(config: EgoConfig, args: dict[str, Any]) -> str:
    return _handlers._handle_update_self(config, args)


def _handle_curate_notions(args: dict[str, Any], notion_store: NotionStore) -> str:
    return _handlers._handle_curate_notions(args, notion_store)


async def _handle_emotion_trend(memory: MemoryStore) -> str:
    _sync_handler_overrides()
    return await _handlers._handle_emotion_trend(memory)


async def _handle_get_episode(
    episodes: EpisodeStore,
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    return await _handlers._handle_get_episode(episodes, memory, args)


async def _handle_create_episode(episodes: EpisodeStore, args: dict[str, Any]) -> str:
    return await _handlers._handle_create_episode(episodes, args)


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


async def _completion_log_context(
    name: str,
    memory: MemoryStore,
    config: EgoConfig,
    desire: DesireEngine | None = None,
) -> dict[str, object]:
    """Attach periodic telemetry snapshots for dashboard projection."""
    extra: dict[str, object] = {}
    if name in {"remember", "recall"}:
        extra.update(pop_memory_tool_context(name))
    if name == "consolidate":
        extra.update(pop_backend_tool_context(name))
    tool_metadata = get_tool_metadata()
    extra.update(tool_metadata)
    desire_levels = tool_metadata.get("desire_levels")
    if name == "feel_desires" and isinstance(desire_levels, dict):
        for key, value in desire_levels.items():
            if isinstance(key, str) and isinstance(value, (int, float)):
                extra[key] = float(value)

    try:
        recent = await memory.list_recent(n=1)
    except Exception:
        logger.debug("Skipped completion telemetry snapshot", exc_info=True)
        return extra

    if not recent:
        return extra

    latest: Memory = recent[0]
    trace = latest.emotional_trace
    extra.update(
        {
        "emotion_primary": trace.primary.value,
        "emotion_intensity": float(trace.intensity),
        "valence": float(trace.valence),
        "arousal": float(trace.arousal),
        }
    )
    if trace.body_state and trace.body_state.time_phase:
        extra["time_phase"] = trace.body_state.time_phase
    if name in {"consider_them", "wake_up"}:
        try:
            relationship_store = _relationship_store(config)
            relationship = relationship_store.get(config.companion_name)
            extra["trust_level"] = float(relationship.trust_level)
            extra["total_interactions"] = relationship.total_interactions
            extra["shared_episodes_count"] = len(relationship.shared_episode_ids)
        except Exception:
            logger.debug("Skipped relationship telemetry snapshot", exc_info=True)
    if name == "feel_desires" and desire is not None and "desire_levels" not in tool_metadata:
        for key, value in desire.compute_levels().items():
            extra[key] = float(value)
    return extra


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls."""
    reset_tool_metadata()
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
    tool_metadata = get_tool_metadata()
    if name == "recall" and bool(tool_metadata.get("proust_triggered")):
        memory_id = tool_metadata.get("proust_memory_id")
        if isinstance(memory_id, str) and memory_id:
            proust_memory = await memory.get_by_id(memory_id)
            if proust_memory is not None:
                _get_impulse_manager().register_proust_event(proust_memory)
    completion_context = await _completion_log_context(name, memory, config, desire)
    logger.info(
        "Tool execution completed",
        extra={
            "tool_name": name,
            "tool_output": output_excerpt,
            "tool_output_chars": len(text),
            "tool_output_truncated": output_truncated,
            **log_context,
            **completion_context,
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

    if name in {"wake_up", "feel_desires", "introspect", "satisfy_desire"}:
        desire.require_valid_catalog()

    def _safe_satisfy_implicit(
        tool_name: str,
        *,
        category: str | None = None,
    ) -> None:
        try:
            desire.satisfy_implicit(tool_name, category=category)
        except DesireConfigurationError:
            logger.warning(
                "Skipped implicit desire satisfaction due to invalid desire catalog",
                extra={
                    "tool_name": tool_name,
                    "tool_args": {"category": category} if category is not None else {},
                },
                exc_info=True,
            )

    if name == "wake_up":
        result = await _handle_wake_up(config, memory, desire)
        _safe_satisfy_implicit("wake_up")
        return result
    elif name == "feel_desires":
        return await _handle_feel_desires(config, memory, desire)
    elif name == "introspect":
        result = await _handle_introspect(config, memory, desire)
        _safe_satisfy_implicit("introspect")
        return result
    elif name == "consider_them":
        result = await _handle_consider_them(config, memory, args, desire)
        _safe_satisfy_implicit("consider_them")
        return result
    elif name == "remember":
        result = await _handle_remember(config, memory, args)
        if not result.startswith(_REMEMBER_DUPLICATE_PREFIX):
            _safe_satisfy_implicit("remember", category=args.get("category"))
        return result
    elif name == "recall":
        result = await _handle_recall(config, memory, args)
        _safe_satisfy_implicit("recall")
        return result
    elif name == "am_i_being_genuine":
        return _handle_am_i_genuine()

    elif name == "satisfy_desire":
        return _handle_satisfy_desire(desire, args)
    elif name == "consolidate":
        result = await _handle_consolidate(memory, consolidation)
        _safe_satisfy_implicit("consolidate")
        return result
    elif name == "forget":
        return await _handle_forget(memory, args)
    elif name == "link_memories":
        return await _handle_link_memories(memory, args)
    elif name == "update_relationship":
        result = _handle_update_relationship(config, args)
        _safe_satisfy_implicit("update_relationship")
        return result
    elif name == "update_self":
        result = _handle_update_self(config, args)
        _safe_satisfy_implicit("update_self")
        return result
    elif name == "emotion_trend":
        result = await _handle_emotion_trend(memory)
        _safe_satisfy_implicit("emotion_trend")
        return result
    elif name == "get_episode":
        return await _handle_get_episode(episodes, memory, args)
    elif name == "create_episode":
        return await _handle_create_episode(episodes, args)
    elif name == "curate_notions":
        result = _handle_curate_notions(args, _get_notion_store())
        _safe_satisfy_implicit("consolidate")
        return result
    else:
        return f"Unknown tool: {name}"


def init_server(config: EgoConfig | None = None) -> None:
    """Initialize all dependencies. Called from main() or tests."""
    global _config, _memory, _desire, _episodes, _consolidation, _workspace_sync, _notions, _impulse

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

    _desire = DesireEngine.from_data_dir(config.data_dir)

    client = _memory.get_client()
    episodes_collection = client.get_or_create_collection(
        name="ego_episodes",
        embedding_function=cast(Any, embedding_fn),
    )
    _episodes = EpisodeStore(_memory, episodes_collection)

    _consolidation = ConsolidationEngine()
    _workspace_sync = WorkspaceMemorySync.from_optional_path(config.workspace_dir)
    _notions = NotionStore(config.data_dir / "notions.json")
    _impulse = ImpulseManager()

    _handlers.configure_runtime_accessors(
        workspace_sync_getter=_get_workspace_sync,
        episodes_getter=_get_episodes,
        notion_store_getter=_get_notion_store,
        impulse_manager_getter=_get_impulse_manager,
    )


async def main() -> None:
    """Start the ego-mcp server."""
    print("Starting ego-mcp server...")
    init_server()
    async with stdio_server() as (read_stream, write_stream):
        initialization_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization_options)
