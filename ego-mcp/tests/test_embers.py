"""Tests for ember generation logic."""

from __future__ import annotations

from ego_mcp.embers import generate_embers
from ego_mcp.types import Emotion, EmotionalTrace, Memory, Notion


def _mem(
    *,
    intensity: float = 0.5,
    emotion: Emotion = Emotion.NEUTRAL,
    content: str = "some memory",
) -> Memory:
    return Memory(
        id="m1",
        content=content,
        emotional_trace=EmotionalTrace(primary=emotion, intensity=intensity),
    )


def _notion(*, label: str = "something", confidence: float = 0.5) -> Notion:
    return Notion(id="n1", label=label, confidence=confidence)


class TestGenerateEmbers:
    def test_empty_inputs_returns_empty(self) -> None:
        result = generate_embers([], [], [], [])
        assert result == []

    def test_high_intensity_memory_produces_ember(self) -> None:
        mem = _mem(intensity=0.8, emotion=Emotion.SAD, content="lost the notebook")
        result = generate_embers([mem], [], [], [])
        assert len(result) == 1
        assert "sad" in result[0].lower()
        assert "lost the notebook" in result[0]

    def test_low_intensity_memory_excluded(self) -> None:
        mem = _mem(intensity=0.3, emotion=Emotion.HAPPY, content="ate lunch")
        result = generate_embers([mem], [], [], [])
        assert result == []

    def test_high_salience_question_produces_ember(self) -> None:
        q = {"question": "Why does this keep happening?", "salience": 0.6, "importance": 4}
        result = generate_embers([], [q], [], [])
        assert len(result) == 1
        assert "still wondering" in result[0].lower()
        assert "Why does this keep happening?" in result[0]

    def test_low_salience_question_excluded(self) -> None:
        q = {"question": "minor note", "salience": 0.2, "importance": 2}
        result = generate_embers([], [q], [], [])
        assert result == []

    def test_emergent_desire_produces_ember(self) -> None:
        result = generate_embers([], [], ["be_with_someone"], [])
        assert len(result) == 1
        assert "be with someone" in result[0].lower()

    def test_weakened_notion_produces_ember(self) -> None:
        n = _notion(label="trust is always repaid", confidence=0.3)
        result = generate_embers([], [], [], [n])
        assert len(result) == 1
        assert "less certain" in result[0].lower()

    def test_max_two_embers(self) -> None:
        mems = [
            _mem(intensity=0.9, emotion=Emotion.EXCITED, content="a"),
            _mem(intensity=0.8, emotion=Emotion.SAD, content="b"),
            _mem(intensity=0.7, emotion=Emotion.ANXIOUS, content="c"),
        ]
        result = generate_embers(mems, [], [], [])
        assert len(result) == 2

    def test_scoring_ranks_higher_intensity_first(self) -> None:
        mem_low = _mem(intensity=0.65, emotion=Emotion.CALM, content="lower")
        mem_high = _mem(intensity=0.95, emotion=Emotion.EXCITED, content="higher")
        result = generate_embers([mem_low, mem_high], [], [], [])
        assert len(result) == 2
        assert "higher" in result[0]

    def test_mixed_sources_ranked_by_score(self) -> None:
        mem = _mem(intensity=0.9, emotion=Emotion.MOVED, content="powerful moment")
        q = {"question": "deep question", "salience": 0.5, "importance": 3}
        result = generate_embers([mem], [q], ["feel_safe"], [_notion()])
        assert len(result) == 2
        # Highest score should be the memory (0.9 * 1.0 = 0.9)
        assert "powerful moment" in result[0]

    def test_unknown_emergent_desire_id_skipped(self) -> None:
        result = generate_embers([], [], ["nonexistent_desire"], [])
        assert result == []
