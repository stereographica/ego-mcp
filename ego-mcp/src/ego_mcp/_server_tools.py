"""Tool schema definitions for the MCP server."""

from __future__ import annotations

from mcp.types import Tool

from ego_mcp.relationship import _UPDATABLE_FIELDS

_FIELD_ALIASES: dict[str, str] = {
    "trust": "trust_level",
    "facts": "known_facts",
    "personality": "inferred_personality",
    "topics": "preferred_topics",
    "dominant_tone": "emotional_baseline",
}

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
                "shared_with": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": (
                        "Person name(s) this memory is shared with. Creates an "
                        "episode and links it to the relationship."
                    ),
                },
                "related_memories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Existing memory IDs to bundle into the episode alongside "
                        "this new memory."
                    ),
                },
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
                "field": {
                    "type": "string",
                    "enum": sorted(_UPDATABLE_FIELDS),
                    "description": (
                        "Relationship field to update. Examples: trust_level, "
                        "known_facts, preferred_topics, emotional_baseline. "
                        "Aliases like trust/facts/topics/personality are resolved "
                        "automatically. Note: `intensity` belongs to remember() and "
                        "cannot be updated here."
                    ),
                },
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
