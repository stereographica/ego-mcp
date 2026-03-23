"""Tests for notion generation and reinforcement."""

from __future__ import annotations

from pathlib import Path

from ego_mcp.notion import (
    NotionStore,
    generate_notion_from_cluster,
    update_notion_from_memory,
)
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory, Notion


def _memory(
    *,
    memory_id: str,
    content: str,
    emotion: Emotion,
    valence: float,
    tags: list[str],
) -> Memory:
    return Memory(
        id=memory_id,
        content=content,
        category=Category.INTROSPECTION,
        emotional_trace=EmotionalTrace(primary=emotion, valence=valence),
        tags=tags,
    )


def test_generate_notion_from_cluster_uses_shared_tags_and_emotion() -> None:
    memories = [
        _memory(
            memory_id="mem_a",
            content="alpha signal",
            emotion=Emotion.CURIOUS,
            valence=0.4,
            tags=["pattern", "signal"],
        ),
        _memory(
            memory_id="mem_b",
            content="beta signal",
            emotion=Emotion.CURIOUS,
            valence=0.2,
            tags=["signal", "pattern"],
        ),
    ]

    notion = generate_notion_from_cluster(memories)

    assert notion.label == "pattern & signal (curious)"
    assert notion.emotion_tone == Emotion.CURIOUS
    assert notion.confidence == 0.5
    assert notion.source_memory_ids == ["mem_a", "mem_b"]
    assert notion.tags == ["pattern", "signal"]


def test_generate_notion_from_cluster_falls_back_to_content_when_tags_missing() -> None:
    memories = [
        _memory(
            memory_id="mem_a",
            content="A recurring thought about continuity. emotion traces might carry weight.",
            emotion=Emotion.CURIOUS,
            valence=0.4,
            tags=[],
        ),
        _memory(
            memory_id="mem_b",
            content="A recurring thought about continuity.\nMore detail follows here.",
            emotion=Emotion.CURIOUS,
            valence=0.2,
            tags=[],
        ),
    ]

    notion = generate_notion_from_cluster(memories)

    assert notion.label == "A recurring thought about continuity (curious)"
    assert notion.tags == []


def test_notion_store_reinforces_and_weakens_by_tag_overlap(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    reinforcing = Notion(
        id="notion_1",
        label="pattern & signal (curious)",
        emotion_tone=Emotion.CURIOUS,
        valence=0.5,
        confidence=0.4,
        source_memory_ids=["mem_a"],
        tags=["pattern", "signal"],
        created="2026-02-26T00:00:00+00:00",
        last_reinforced="2026-02-26T00:00:00+00:00",
    )
    weakening = Notion(
        id="notion_2",
        label="tension & friction (sad)",
        emotion_tone=Emotion.SAD,
        valence=-0.6,
        confidence=0.25,
        source_memory_ids=["mem_b"],
        tags=["friction", "tension"],
        created="2026-02-26T00:00:00+00:00",
        last_reinforced="2026-02-26T00:00:00+00:00",
    )
    store.save(reinforcing)
    store.save(weakening)

    memory = _memory(
        memory_id="mem_new",
        content="new signal",
        emotion=Emotion.CURIOUS,
        valence=0.4,
        tags=["signal", "pattern", "friction"],
    )

    updates = update_notion_from_memory(store, memory)

    updated = store.get_by_id("notion_1")
    assert updated is not None
    assert updated.confidence == 0.5
    assert updated.source_memory_ids == ["mem_a", "mem_new"]
    assert updated.last_reinforced != ""

    assert store.get_by_id("notion_2") is None
    assert {item for item in updates} == {("notion_1", "reinforced"), ("notion_2", "dormant")}


def test_notion_store_search_by_tags_ranks_overlap_and_confidence(
    tmp_path: Path,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_a",
            label="signal",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.9,
            tags=["pattern", "signal"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )
    store.save(
        Notion(
            id="notion_b",
            label="pattern",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.4,
            tags=["pattern"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )

    matches = store.search_by_tags(["pattern", "signal"], min_match=1)

    assert [item.id for item in matches] == ["notion_a", "notion_b"]
