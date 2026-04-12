"""Tests for _server_context module to improve coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ego_mcp._server_context import (
    _cosine_similarity,
    _derive_desire_modulation,
    _find_related_forgotten_questions,
    _infer_topics_from_memories,
    _relationship_snapshot,
)
from ego_mcp.config import EgoConfig
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory


def _make_memory(
    *,
    content: str = "test",
    valence: float = 0.0,
    intensity: float = 0.5,
    primary: Emotion = Emotion.CALM,
    category: Category = Category.CONVERSATION,
    ts_offset_days: float = 0,
) -> Memory:
    ts = datetime.now(timezone.utc) - timedelta(days=ts_offset_days)
    return Memory(
        id="m1",
        content=content,
        timestamp=ts.isoformat(),
        category=category,
        emotional_trace=EmotionalTrace(
            primary=primary,
            valence=valence,
            arousal=0.5,
            intensity=intensity,
        ),
        tags=["test"],
        importance=3,
    )


@pytest.fixture
def config(tmp_path: Path) -> EgoConfig:
    return EgoConfig(
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        api_key="test-key",
        data_dir=tmp_path,
        companion_name="TestUser",
        workspace_dir=None,
        timezone="UTC",
    )


class TestCosineSimilarity:
    def test_empty_vectors(self) -> None:
        assert _cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_identical_vectors(self) -> None:
        result = _cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(result - 1.0) < 0.001


class TestFindRelatedForgottenQuestions:
    def test_empty_candidates(self) -> None:
        mem = MagicMock()
        result = _find_related_forgotten_questions(mem, "test", candidates=[])
        assert result == []

    def test_embedding_error_returns_empty(self) -> None:
        mem = MagicMock()
        mem.embed.side_effect = RuntimeError("embed failed")
        candidates = [{"question": "what is X?", "salience": 0.2}]
        result = _find_related_forgotten_questions(mem, "test", candidates=candidates)
        assert result == []

    def test_high_similarity_returned(self) -> None:
        mem = MagicMock()
        mem.embed.return_value = [[1.0, 0.0], [0.95, 0.05]]
        candidates = [{"question": "what is X?", "salience": 0.2}]
        result = _find_related_forgotten_questions(
            mem, "test", candidates=candidates, threshold=0.5
        )
        assert len(result) == 1
        assert result[0]["question"] == "what is X?"
        assert "band" in result[0]


class TestDeriveDesireModulation:
    @pytest.mark.asyncio
    async def test_empty_recent_with_fading_questions(self) -> None:
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])
        fading = [{"question": "why?", "importance": 4, "salience": 0.2}]
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=[], fading_important_questions=fading
        )
        assert "cognitive_coherence" in ctx
        assert emo == {}
        assert pred == {}

    @pytest.mark.asyncio
    async def test_technical_memories_boost_pattern_seeking(self) -> None:
        mems = [
            _make_memory(category=Category.TECHNICAL) for _ in range(3)
        ]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert ctx.get("pattern_seeking", 0) > 0
        assert ctx.get("predictability", 0) > 0

    @pytest.mark.asyncio
    async def test_conversation_memories_boost_resonance(self) -> None:
        mems = [
            _make_memory(category=Category.CONVERSATION) for _ in range(3)
        ]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert ctx.get("resonance", 0) > 0

    @pytest.mark.asyncio
    async def test_introspection_memories_boost_coherence(self) -> None:
        mems = [
            _make_memory(category=Category.INTROSPECTION) for _ in range(2)
        ]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert ctx.get("cognitive_coherence", 0) > 0

    @pytest.mark.asyncio
    async def test_negative_valence_emotional_modulation(self) -> None:
        mems = [_make_memory(valence=-0.4) for _ in range(3)]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert emo.get("social_thirst", 0) > 0
        assert emo.get("cognitive_coherence", 0) > 0

    @pytest.mark.asyncio
    async def test_positive_valence_emotional_modulation(self) -> None:
        mems = [_make_memory(valence=0.4) for _ in range(3)]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert emo.get("curiosity", 0) > 0
        assert emo.get("expression", 0) > 0

    @pytest.mark.asyncio
    async def test_anxious_memories_emotional_modulation(self) -> None:
        mems = [_make_memory(primary=Emotion.ANXIOUS) for _ in range(3)]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert emo.get("cognitive_coherence", 0) > 0
        assert emo.get("social_thirst", 0) > 0

    @pytest.mark.asyncio
    async def test_surprise_prediction_error(self) -> None:
        mems = [_make_memory(primary=Emotion.SURPRISED, intensity=0.8)]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=[]
        )
        assert pred.get("curiosity", 0) > 0

    @pytest.mark.asyncio
    async def test_fading_questions_with_recent(self) -> None:
        mems = [_make_memory()]
        fading = [{"question": "why?", "importance": 4, "salience": 0.2}]
        mem = AsyncMock()
        ctx, emo, pred = await _derive_desire_modulation(
            mem, recent_memories=mems, fading_important_questions=fading
        )
        assert ctx.get("cognitive_coherence", 0) > 0


class TestInferTopicsFromMemories:
    def test_technical_memory(self) -> None:
        mems = [_make_memory(content="fix the code bug")]
        preferred, sensitive = _infer_topics_from_memories(mems)
        assert "technical" in preferred

    def test_sensitive_topic_detection(self) -> None:
        mems = [
            _make_memory(
                content="the code deployment failed",
                primary=Emotion.SAD,
                valence=-0.5,
            )
        ]
        preferred, sensitive = _infer_topics_from_memories(mems)
        assert "technical" in sensitive


class TestRelationshipSnapshot:
    @pytest.mark.asyncio
    async def test_basic_snapshot(self, config: EgoConfig) -> None:
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])
        result = await _relationship_snapshot(config, mem, "TestUser")
        assert "TestUser" in result
        assert "trust=" in result
