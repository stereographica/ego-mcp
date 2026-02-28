"""Compatibility layer that re-exports server handler helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

import ego_mcp._server_backend_handlers as _backend_handlers_module
import ego_mcp._server_emotion_formatting as _emotion_formatting_module
import ego_mcp._server_surface_core as _surface_core_module
import ego_mcp._server_surface_memory as _surface_memory_module
from ego_mcp._server_backend_handlers import (
    _handle_consolidate,
    _handle_create_episode,
    _handle_emotion_trend,
    _handle_forget,
    _handle_get_episode,
    _handle_link_memories,
    _handle_satisfy_desire,
    _handle_update_relationship,
    _handle_update_self,
)
from ego_mcp._server_context import (
    _cosine_similarity,
    _derive_desire_modulation,
    _fading_important_questions,
    _fading_or_dormant_questions,
    _find_related_forgotten_questions,
    _infer_topics_from_memories,
    _relationship_snapshot,
    _relationship_store,
    _self_model_store_for_memory,
    _summarize_conversation_tendency,
)
from ego_mcp._server_emotion_formatting import (
    _format_month_emotion_layer,
    _format_recall_entry,
    _format_recent_emotion_layer,
    _format_week_emotion_layer,
    _memories_within_days,
    _parse_iso_datetime,
    _recall_scaffold,
    _relative_time,
    _secondary_weighted_counts,
    _truncate_for_log,
    _truncate_for_quote,
    _valence_arousal_to_impression,
)
from ego_mcp._server_runtime import configure_runtime_accessors
from ego_mcp._server_surface_handlers import (
    _REMEMBER_DUPLICATE_PREFIX,
    _handle_am_i_genuine,
    _handle_consider_them,
    _handle_feel_desires,
    _handle_introspect,
    _handle_recall,
    _handle_remember,
    _handle_wake_up,
)


def configure_test_overrides(
    *,
    relative_time: Callable[[str, datetime | None], str],
    relationship_snapshot: Callable[[Any, Any, str], Awaitable[str]],
    derive_desire_modulation: Callable[
        ...,
        Awaitable[tuple[dict[str, float], dict[str, float], dict[str, float]]],
    ],
    get_body_state: Callable[[], dict[str, Any]],
    calculate_time_decay: Callable[[str, datetime | None, float], float],
) -> None:
    """Apply server-module overrides to split handler modules."""
    _surface_core_module.configure_overrides(
        relationship_snapshot=relationship_snapshot,
        derive_desire_modulation=derive_desire_modulation,
        get_body_state_fn=get_body_state,
    )
    _surface_memory_module.configure_overrides(
        relative_time=relative_time,
        get_body_state_fn=get_body_state,
    )
    _backend_handlers_module.configure_overrides(relative_time=relative_time)
    _emotion_formatting_module.configure_overrides(
        relative_time=relative_time,
        calculate_time_decay_fn=calculate_time_decay,
    )


__all__ = [
    "_REMEMBER_DUPLICATE_PREFIX",
    "_truncate_for_quote",
    "_truncate_for_log",
    "_relative_time",
    "_format_recall_entry",
    "_recall_scaffold",
    "_parse_iso_datetime",
    "_memories_within_days",
    "_secondary_weighted_counts",
    "_valence_arousal_to_impression",
    "_format_recent_emotion_layer",
    "_format_week_emotion_layer",
    "_format_month_emotion_layer",
    "_self_model_store_for_memory",
    "_cosine_similarity",
    "_fading_or_dormant_questions",
    "_fading_important_questions",
    "_find_related_forgotten_questions",
    "_relationship_store",
    "_summarize_conversation_tendency",
    "_infer_topics_from_memories",
    "_relationship_snapshot",
    "_derive_desire_modulation",
    "_handle_wake_up",
    "_handle_feel_desires",
    "_handle_introspect",
    "_handle_consider_them",
    "_handle_remember",
    "_handle_recall",
    "_handle_am_i_genuine",
    "_handle_satisfy_desire",
    "_handle_consolidate",
    "_handle_forget",
    "_handle_link_memories",
    "_handle_update_relationship",
    "_handle_update_self",
    "_handle_emotion_trend",
    "_handle_get_episode",
    "_handle_create_episode",
    "configure_runtime_accessors",
    "configure_test_overrides",
]
