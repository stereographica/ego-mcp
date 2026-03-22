"""Tests for decay-aware memory formatting."""

from __future__ import annotations

from datetime import datetime, timezone

from ego_mcp._memory_formatting import format_memory_by_decay
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory


def _memory(timestamp: str, content: str = "A memory about signal and pattern") -> Memory:
    return Memory(
        content=content,
        timestamp=timestamp,
        category=Category.INTROSPECTION,
        importance=4,
        tags=["signal", "pattern"],
        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS),
    )


def test_format_memory_by_decay_preserves_detail_for_fresh_memories() -> None:
    memory = _memory("2026-02-26T11:30:00+00:00")

    text = format_memory_by_decay(
        memory,
        decay=0.9,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith(memory.content)
    assert "emotion: curious" in text
    assert "category: introspection" in text
    assert "importance: 4" in text
    assert "tags: signal, pattern" in text


def test_format_memory_by_decay_degrades_to_fading_summary() -> None:
    memory = _memory("2026-02-16T12:00:00+00:00")

    text = format_memory_by_decay(
        memory,
        decay=0.3,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith("curious introspection")
    assert "signal" in text
    assert "pattern" in text
    assert "~10 days ago" in text
    assert "decay: 0.30" in text


def test_format_memory_by_decay_degrades_to_faint_summary() -> None:
    memory = _memory("2024-02-26T12:00:00+00:00", content="Old signal")

    text = format_memory_by_decay(
        memory,
        decay=0.1,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text == "curious, ~2 years ago decay: 0.10"


def test_format_memory_by_decay_extracts_cjk_keywords() -> None:
    memory = _memory(
        "2026-02-16T12:00:00+00:00",
        content="安全な場所に帰りたい 記憶の断片",
    )

    text = format_memory_by_decay(
        memory,
        decay=0.3,
        now=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert text.startswith("curious introspection")
    assert "安全な場所に帰りたい" in text
    assert "decay: 0.30" in text
