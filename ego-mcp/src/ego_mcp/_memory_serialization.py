"""Memory serialization helpers for ChromaDB metadata."""

from __future__ import annotations

import json
from typing import Any

from ego_mcp.types import (
    BodyState,
    Category,
    Emotion,
    EmotionalTrace,
    LinkType,
    Memory,
    MemoryLink,
)


def memory_from_chromadb(
    memory_id: str, content: str, metadata: dict[str, Any]
) -> Memory:
    """Reconstruct Memory from ChromaDB metadata."""
    emotion_str = metadata.get("emotion", "neutral")
    try:
        primary_emotion = Emotion(emotion_str)
    except ValueError:
        primary_emotion = Emotion.NEUTRAL

    category_str = metadata.get("category", "daily")
    try:
        category = Category(category_str)
    except ValueError:
        category = Category.DAILY

    linked_ids: list[MemoryLink] = []
    linked_json = metadata.get("linked_ids", "")
    if linked_json:
        try:
            link_list = json.loads(linked_json)
            for link_data in link_list:
                try:
                    linked_ids.append(
                        MemoryLink(
                            target_id=link_data.get("target_id", ""),
                            link_type=LinkType(link_data.get("link_type", "related")),
                            confidence=float(link_data.get("confidence", 0.5)),
                            note=link_data.get("note", ""),
                        )
                    )
                except (ValueError, TypeError):
                    pass
        except (json.JSONDecodeError, TypeError):
            pass

    secondary: list[Emotion] = []
    secondary_raw = metadata.get("secondary", "")
    if isinstance(secondary_raw, str) and secondary_raw:
        for token in secondary_raw.split(","):
            try:
                secondary.append(Emotion(token))
            except ValueError:
                continue

    body_state: BodyState | None = None
    body_state_raw = metadata.get("body_state", "")
    if isinstance(body_state_raw, str) and body_state_raw:
        try:
            payload = json.loads(body_state_raw)
            if isinstance(payload, dict):
                body_state = BodyState(
                    time_phase=str(payload.get("time_phase", "unknown")),
                    system_load=str(payload.get("system_load", "unknown")),
                    uptime_hours=float(payload.get("uptime_hours", 0.0)),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            body_state = None

    private_raw = metadata.get("is_private", False)
    is_private = private_raw in (True, 1, "1", "true", "True")

    return Memory(
        id=memory_id,
        content=content,
        timestamp=metadata.get("timestamp", ""),
        emotional_trace=EmotionalTrace(
            primary=primary_emotion,
            secondary=secondary,
            intensity=float(metadata.get("intensity", 0.5)),
            valence=float(metadata.get("valence", 0.0)),
            arousal=float(metadata.get("arousal", 0.5)),
            body_state=body_state,
        ),
        importance=int(metadata.get("importance", 3)),
        category=category,
        tags=metadata.get("tags", "").split(",") if metadata.get("tags") else [],
        linked_ids=linked_ids,
        is_private=is_private,
    )


def links_to_json(links: list[MemoryLink]) -> str:
    """Serialize MemoryLinks to JSON string for ChromaDB metadata."""
    return json.dumps(
        [
            {
                "target_id": link.target_id,
                "link_type": link.link_type.value,
                "confidence": link.confidence,
                "note": link.note,
            }
            for link in links
        ]
    )
