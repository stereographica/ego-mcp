"""Ember generation — short smouldering text fragments for wake_up."""

from __future__ import annotations

from ego_mcp.emergent_desires import emergent_desire_fragment
from ego_mcp.types import Memory, Notion

_MAX_EMBERS = 2
_INTENSITY_THRESHOLD = 0.6
_SNIPPET_LEN = 60


def _snippet(text: str, max_len: int = _SNIPPET_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def generate_embers(
    recent_memories: list[Memory],
    emergent_desires: list[str],
    weakened_notions: list[Notion],
) -> list[str]:
    """Generate up to 2 ember text fragments from multiple sources.

    Each candidate is scored, ranked, and the top ``_MAX_EMBERS`` are
    rendered as short prose fragments.
    """
    candidates: list[tuple[float, str]] = []

    # High-intensity memories
    for mem in recent_memories:
        intensity = mem.emotional_trace.intensity
        if intensity <= _INTENSITY_THRESHOLD:
            continue
        score = intensity  # recency_weight=1.0 (all recent)
        emotion = mem.emotional_trace.primary.value
        text = f"...{emotion} about: {_snippet(mem.content)}"
        candidates.append((score, text))

    # Active emergent desires
    for desire_id in emergent_desires:
        fragment = emergent_desire_fragment(desire_id)
        if fragment is None:
            continue
        score = 0.5
        text = f"...{fragment}"
        candidates.append((score, text))

    # Weakened notions
    for _notion in weakened_notions:
        score = 0.4
        text = "...something I thought I understood feels less certain now"
        candidates.append((score, text))

    # Sort descending by score, take top N
    candidates.sort(key=lambda c: c[0], reverse=True)
    return [text for _, text in candidates[:_MAX_EMBERS]]
