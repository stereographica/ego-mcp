"""Tests for current_interest derivation view."""

from __future__ import annotations

from ego_mcp import timezone_utils
from ego_mcp.current_interest import (
    _generic_categories,
    derive_current_interests,
)
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory, Notion


def _make_memory(
    *,
    tags: list[str] | None = None,
    category: Category = Category.DAILY,
    emotion: Emotion = Emotion.NEUTRAL,
    hours_ago: float = 1.0,
) -> Memory:
    ts = (
        timezone_utils.now()
        - __import__("datetime").timedelta(hours=hours_ago)
    ).isoformat()
    return Memory(
        id=f"mem-{id(tags)}-{hours_ago}",
        content="test content",
        timestamp=ts,
        emotional_trace=EmotionalTrace(primary=emotion),
        category=category,
        tags=tags or [],
    )


def _make_notion(
    *,
    label: str = "test-notion",
    hours_since_reinforced: float = 1.0,
) -> Notion:
    ts = (
        timezone_utils.now()
        - __import__("datetime").timedelta(hours=hours_since_reinforced)
    ).isoformat()
    return Notion(
        id=f"notion-{label}",
        label=label,
        last_reinforced=ts,
        confidence=0.8,
    )


class TestEmptyInputs:
    def test_empty_inputs_returns_empty_list(self) -> None:
        result = derive_current_interests(
            recent_memories=[],
            background_memories=[],
            emergent_desires=[],
            recent_notions=[],
        )
        assert result == []

    def test_no_recent_memories_with_notions_still_works(self) -> None:
        notion = _make_notion(label="art")
        result = derive_current_interests(
            recent_memories=[],
            background_memories=[],
            emergent_desires=[],
            recent_notions=[notion],
        )
        assert len(result) >= 1
        assert result[0]["topic"] == "art"


class TestTagBasedTopics:
    def test_single_memory_tag_becomes_topic(self) -> None:
        mem = _make_memory(tags=["python"], hours_ago=1.0)
        result = derive_current_interests(
            recent_memories=[mem],
            background_memories=[mem],
            emergent_desires=[],
            recent_notions=[],
        )
        assert len(result) >= 1
        topics = [r["topic"] for r in result]
        assert "python" in topics

    def test_repeated_tag_accumulates_weight(self) -> None:
        mems = [
            _make_memory(tags=["python"], hours_ago=1.0),
            _make_memory(tags=["python"], hours_ago=2.0),
            _make_memory(tags=["rust"], hours_ago=1.0),
        ]
        result = derive_current_interests(
            recent_memories=mems,
            background_memories=mems,
            emergent_desires=[],
            recent_notions=[],
        )
        assert len(result) >= 1
        assert result[0]["topic"] == "python"


class TestNotionWeighting:
    def test_notion_label_weighted_higher_than_tag(self) -> None:
        mem = _make_memory(tags=["python"], hours_ago=1.0)
        notion = _make_notion(label="art", hours_since_reinforced=1.0)
        result = derive_current_interests(
            recent_memories=[mem],
            background_memories=[mem],
            emergent_desires=[],
            recent_notions=[notion],
        )
        assert len(result) >= 2
        # Notion label (weight 2.0) should outrank tag (weight 1.0)
        assert result[0]["topic"] == "art"


class TestGenericCategories:
    def test_generic_category_downweighted(self) -> None:
        # 5 out of 6 memories are "daily" -> daily is generic (83%)
        bg = [_make_memory(category=Category.DAILY, hours_ago=float(i)) for i in range(1, 6)]
        bg.append(_make_memory(category=Category.TECHNICAL, tags=["rare"], hours_ago=1.0))

        # A recent memory with daily category should be downweighted
        recent_daily = _make_memory(category=Category.DAILY, hours_ago=0.5)
        recent_tech = _make_memory(category=Category.TECHNICAL, tags=["rare"], hours_ago=0.5)

        result = derive_current_interests(
            recent_memories=[recent_daily, recent_tech],
            background_memories=bg,
            emergent_desires=[],
            recent_notions=[],
        )
        topics = [r["topic"] for r in result]
        # "rare" tag (weight 1.0) or "technical" (non-generic, weight 0.5)
        # should rank higher than "daily" (generic, weight 0.15)
        if len(topics) >= 2:
            assert "rare" in topics[:2]

    def test_generic_categories_detection(self) -> None:
        mems = [_make_memory(category=Category.DAILY) for _ in range(4)]
        generics = _generic_categories(mems, threshold=0.25)
        assert "daily" in generics

    def test_generic_categories_empty_input(self) -> None:
        assert _generic_categories([], threshold=0.25) == set()

    def test_minority_category_not_generic(self) -> None:
        mems = [_make_memory(category=Category.DAILY) for _ in range(4)]
        mems.append(_make_memory(category=Category.TECHNICAL))
        generics = _generic_categories(mems, threshold=0.25)
        assert "technical" not in generics
        assert "daily" in generics


class TestMaxInterests:
    def test_max_interests_respected(self) -> None:
        mems = [
            _make_memory(tags=[f"topic-{i}"], hours_ago=float(i))
            for i in range(10)
        ]
        result = derive_current_interests(
            recent_memories=mems,
            background_memories=mems,
            emergent_desires=[],
            recent_notions=[],
            max_interests=2,
        )
        assert len(result) <= 2


class TestEmotionColor:
    def test_emotion_color_from_recent_memory(self) -> None:
        mem = _make_memory(
            tags=["music"],
            hours_ago=1.0,
            emotion=Emotion.HAPPY,
        )
        result = derive_current_interests(
            recent_memories=[mem],
            background_memories=[mem],
            emergent_desires=[],
            recent_notions=[],
        )
        assert len(result) >= 1
        assert result[0]["emotion_color"] == "happy"


class TestRecencyDecay:
    def test_12h_half_life_decay(self) -> None:
        old_mem = _make_memory(tags=["old-topic"], hours_ago=12.0)
        new_mem = _make_memory(tags=["new-topic"], hours_ago=0.5)

        result = derive_current_interests(
            recent_memories=[old_mem, new_mem],
            background_memories=[old_mem, new_mem],
            emergent_desires=[],
            recent_notions=[],
        )
        assert len(result) >= 2
        # Newer memory should rank first
        assert result[0]["topic"] == "new-topic"


class TestEmergentDesires:
    def test_emergent_desire_contributes_topic(self) -> None:
        result = derive_current_interests(
            recent_memories=[],
            background_memories=[],
            emergent_desires=["be_with_someone"],
            recent_notions=[],
        )
        assert len(result) >= 1
        assert result[0]["source"] == "emergent_desire"


class TestOutputStructure:
    def test_result_has_required_keys(self) -> None:
        mem = _make_memory(tags=["test"], hours_ago=1.0, emotion=Emotion.CURIOUS)
        result = derive_current_interests(
            recent_memories=[mem],
            background_memories=[mem],
            emergent_desires=[],
            recent_notions=[],
        )
        assert len(result) >= 1
        entry = result[0]
        assert "topic" in entry
        assert "source" in entry
        assert "emotion_color" in entry
