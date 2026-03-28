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
        description="Start a session.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="feel_desires",
        description="Check current desires.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="introspect",
        description="Get self-reflection materials.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="consider_them",
        description="Think about someone.",
        inputSchema={
            "type": "object",
            "properties": {
                "person": {
                    "type": "string",
                    "description": "Person.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="remember",
        description="Save a memory.",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "emotion": {"type": "string", "default": "neutral"},
                "secondary": {"type": "array", "items": {"type": "string"}},
                "intensity": {"type": "number", "default": 0.5},
                "importance": {"type": "integer", "default": 3},
                "category": {"type": "string", "default": "daily"},
                "valence": {"type": "number", "default": 0.0},
                "arousal": {"type": "number", "default": 0.5},
                "body_state": {"type": "object"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "shared_with": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": (
                        "Person name(s) sharing this memory."
                    ),
                },
                "related_memories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Existing memory IDs to bundle with this memory."
                    ),
                },
                "private": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Keep this memory internal."
                    ),
                },
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="recall",
        description="Recall memories by context.",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Search context.",
                },
                "n_results": {
                    "type": "integer",
                    "default": 3,
                    "description": "Results (default 3, max 10)",
                },
                "emotion_filter": {"type": "string"},
                "category_filter": {"type": "string"},
                "date_from": {
                    "type": "string",
                    "description": "ISO start date.",
                },
                "date_to": {
                    "type": "string",
                    "description": "ISO end date.",
                },
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
        description="Check authenticity.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

BACKEND_TOOLS: list[Tool] = [
    Tool(
        name="satisfy_desire",
        description="Mark a desire as satisfied.",
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
        description="Run consolidation.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="forget",
        description="Delete a memory by ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "Memory ID.",
                }
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="link_memories",
        description="Link two memories.",
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
        description="Update a relationship.",
        inputSchema={
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "field": {
                    "type": "string",
                    "enum": sorted(_UPDATABLE_FIELDS),
                    "description": (
                        "Relationship field to update. Aliases like trust/facts/"
                        "topics/personality work; `intensity` belongs to remember()."
                    ),
                },
                "value": {},
            },
            "required": ["person", "field", "value"],
        },
    ),
    Tool(
        name="update_self",
        description="Update self model.",
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
        description="Analyze emotional trends.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="get_episode",
        description="Get episode details.",
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
        description="Create an episode.",
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
    Tool(
        name="curate_notions",
        description="List, merge, relabel, or delete notions.",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "merge", "relabel", "delete"],
                },
                "notion_id": {"type": "string", "description": "Notion ID."},
                "merge_into": {
                    "type": "string",
                    "description": "Target notion ID.",
                },
                "new_label": {
                    "type": "string",
                    "description": "New label for relabel.",
                },
                "person": {
                    "type": "string",
                    "description": "Associate person.",
                },
            },
            "required": ["action"],
        },
    ),
]
