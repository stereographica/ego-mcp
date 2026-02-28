"""Tests for MemoryStore."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ego_mcp.config import EgoConfig
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import (
    MemoryStore,
    calculate_emotion_boost,
    calculate_final_score,
    calculate_importance_boost,
    calculate_time_decay,
    count_emotions_weighted,
)
from ego_mcp.types import Emotion, EmotionalTrace, Memory, MemorySearchResult

# --- Fake embedding provider for tests ---


class FakeEmbeddingProvider:
    """Returns deterministic embeddings for testing."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate simple hash-based embeddings."""
        results = []
        for text in texts:
            # Simple deterministic embedding based on text hash
            h = hash(text) % 10000
            vec = [(h + i) % 100 / 100.0 for i in range(64)]
            # Normalize
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
            results.append(vec)
        return results


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path / "ego-data"


@pytest.fixture
def config(tmp_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> EgoConfig:
    """Create test config."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_data_dir))
    return EgoConfig.from_env()


@pytest.fixture
def store(config: EgoConfig) -> Iterator[MemoryStore]:
    """Create a MemoryStore with fake embeddings."""
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    fn = EgoEmbeddingFunction(provider)
    s = MemoryStore(config, fn)
    s.connect()
    yield s
    s.close()


# --- Scoring function tests ---


class TestScoringFunctions:
    def test_time_decay_fresh(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        result = calculate_time_decay(now.isoformat(), now)
        assert result == pytest.approx(1.0)

    def test_time_decay_old(self) -> None:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        old = now - timedelta(days=365)
        result = calculate_time_decay(old.isoformat(), now)
        assert result < 0.01

    def test_emotion_boost(self) -> None:
        assert calculate_emotion_boost("excited") == 0.4
        assert calculate_emotion_boost("frustrated") == 0.28
        assert calculate_emotion_boost("anxious") == 0.22
        assert calculate_emotion_boost("melancholy") == 0.18
        assert calculate_emotion_boost("contentment") == 0.08
        assert calculate_emotion_boost("neutral") == 0.0
        assert calculate_emotion_boost("unknown") == 0.0

    def test_importance_boost(self) -> None:
        assert calculate_importance_boost(1) == 0.0
        assert calculate_importance_boost(5) == pytest.approx(0.4)

    def test_final_score(self) -> None:
        score = calculate_final_score(
            semantic_distance=0.5,
            time_decay=1.0,
            emotion_boost=0.2,
            importance_boost=0.2,
        )
        assert score >= 0.0

    def test_count_emotions_weighted_uses_primary_and_secondary_weights(self) -> None:
        memories = [
            Memory(
                content="a",
                emotional_trace=EmotionalTrace(
                    primary=Emotion.CURIOUS,
                    secondary=[Emotion.ANXIOUS, Emotion.HAPPY],
                ),
            ),
            Memory(
                content="b",
                emotional_trace=EmotionalTrace(
                    primary=Emotion.ANXIOUS,
                    secondary=[Emotion.CURIOUS],
                ),
            ),
        ]
        counts = count_emotions_weighted(memories)
        assert counts["curious"] == pytest.approx(1.4)
        assert counts["anxious"] == pytest.approx(1.4)
        assert counts["happy"] == pytest.approx(0.4)


# --- MemoryStore tests ---


class TestMemorySave:
    @pytest.mark.asyncio
    async def test_save_returns_memory(self, store: MemoryStore) -> None:
        mem = await store.save(content="Hello world", emotion="happy", importance=4)
        assert mem.id.startswith("mem_")
        assert mem.content == "Hello world"
        assert mem.emotional_trace.primary.value == "happy"
        assert mem.importance == 4

    @pytest.mark.asyncio
    async def test_save_then_search(self, store: MemoryStore) -> None:
        await store.save(content="The sunset was beautiful", emotion="moved")
        results = await store.search("sunset")
        assert len(results) >= 1
        assert "sunset" in results[0].memory.content

    @pytest.mark.asyncio
    async def test_save_emotional_trace_fields(self, store: MemoryStore) -> None:
        mem = await store.save(
            content="I felt conflicted but calm",
            emotion="curious",
            secondary=["sad", "happy"],
            intensity=0.8,
            valence=-0.2,
            arousal=0.3,
            body_state={
                "time_phase": "evening",
                "system_load": "low",
                "uptime_hours": 1.5,
            },
        )
        loaded = await store.get_by_id(mem.id)
        assert loaded is not None
        assert loaded.emotional_trace.intensity == pytest.approx(0.8)
        assert loaded.emotional_trace.valence == pytest.approx(-0.2)
        assert loaded.emotional_trace.arousal == pytest.approx(0.3)
        assert [e.value for e in loaded.emotional_trace.secondary] == ["sad", "happy"]
        assert loaded.emotional_trace.body_state is not None
        assert loaded.emotional_trace.body_state.time_phase == "evening"

    @pytest.mark.asyncio
    async def test_save_private_roundtrip(self, store: MemoryStore) -> None:
        mem = await store.save(
            content="This is private context",
            private=True,
        )
        loaded = await store.get_by_id(mem.id)
        assert loaded is not None
        assert loaded.is_private is True


class TestMemoryAutoLink:
    @pytest.mark.asyncio
    async def test_auto_link_similar(self, store: MemoryStore) -> None:
        await store.save(content="I love programming in Python")
        mem, num_links, linked_results, duplicate_of = await store.save_with_auto_link(
            content="I love programming in Python too",
            dedup_threshold=0.0,
        )
        # May or may not link depending on embedding similarity
        assert mem is not None
        assert isinstance(linked_results, list)
        assert isinstance(num_links, int)
        assert num_links >= 0
        assert duplicate_of is None

    @pytest.mark.asyncio
    async def test_auto_link_preserves_private_flag(self, store: MemoryStore) -> None:
        await store.save(content="anchor context for links")
        mem, _num_links, _linked_results, duplicate_of = await store.save_with_auto_link(
            content="anchor context for links with private notes",
            private=True,
            dedup_threshold=0.0,
        )
        assert mem is not None
        assert duplicate_of is None
        loaded = await store.get_by_id(mem.id)
        assert loaded is not None
        assert loaded.is_private is True

    @pytest.mark.asyncio
    async def test_save_with_auto_link_returns_four_tuple_items(
        self, store: MemoryStore
    ) -> None:
        result = await store.save_with_auto_link(content="tuple shape check")
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_save_with_auto_link_blocks_near_duplicate_before_saving(
        self, store: MemoryStore
    ) -> None:
        first, _num_links, _linked_results, first_duplicate = await store.save_with_auto_link(
            content="duplicate guard exact content",
        )
        assert first is not None
        assert first_duplicate is None
        assert store.collection_count() == 1

        second, num_links, linked_results, duplicate_of = await store.save_with_auto_link(
            content="duplicate guard exact content",
        )
        assert second is None
        assert num_links == 0
        assert linked_results == []
        assert duplicate_of is not None
        assert duplicate_of.memory.id == first.id
        assert duplicate_of.distance < 0.05
        assert store.collection_count() == 1

    @pytest.mark.asyncio
    async def test_save_with_auto_link_allows_save_when_distance_above_dedup_threshold(
        self,
        store: MemoryStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        anchor = await store.save(content="anchor memory for dedup threshold")
        search_calls: list[int] = []

        async def fake_search(query: str, **kwargs: Any) -> list[MemorySearchResult]:
            del query
            search_calls.append(int(kwargs.get("n_results", 0)))
            return [MemorySearchResult(memory=anchor, distance=0.20, score=0.20)]

        monkeypatch.setattr(store, "search", fake_search)

        mem, _num_links, _linked_results, duplicate_of = await store.save_with_auto_link(
            content="new memory should still save",
            dedup_threshold=0.05,
        )
        assert mem is not None
        assert duplicate_of is None
        assert mem.id != anchor.id
        assert search_calls
        assert search_calls[0] == 1

    @pytest.mark.asyncio
    async def test_save_with_auto_link_skips_dedup_search_when_collection_empty(
        self,
        store: MemoryStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        search_calls: list[int] = []

        async def fake_search(query: str, **kwargs: Any) -> list[MemorySearchResult]:
            del query
            search_calls.append(int(kwargs.get("n_results", 0)))
            return []

        monkeypatch.setattr(store, "search", fake_search)

        mem, _num_links, _linked_results, duplicate_of = await store.save_with_auto_link(
            content="first memory should bypass dedup check",
        )
        assert mem is not None
        assert duplicate_of is None
        # Auto-link search still runs after save (default max_links=5 => n_results=6).
        assert search_calls == [6]


class TestMemoryRecall:
    @pytest.mark.asyncio
    async def test_recall_returns_results(self, store: MemoryStore) -> None:
        await store.save(content="Learned about machine learning today")
        results = await store.recall("machine learning")
        assert len(results) >= 1


class TestMemoryListRecent:
    @pytest.mark.asyncio
    async def test_list_recent_ordered(self, store: MemoryStore) -> None:
        await store.save(content="First memory")
        await store.save(content="Second memory")
        await store.save(content="Third memory")

        recent = await store.list_recent(n=3)
        assert len(recent) == 3
        # Should be timestamp descending
        for i in range(len(recent) - 1):
            assert recent[i].timestamp >= recent[i + 1].timestamp

    @pytest.mark.asyncio
    async def test_list_recent_empty(self, store: MemoryStore) -> None:
        recent = await store.list_recent(n=5)
        assert recent == []


class TestMemoryFilters:
    @pytest.mark.asyncio
    async def test_emotion_filter(self, store: MemoryStore) -> None:
        await store.save(content="Happy moment", emotion="happy")
        await store.save(content="Sad moment", emotion="sad")

        results = await store.search("moment", emotion_filter="happy")
        assert all(r.memory.emotional_trace.primary.value == "happy" for r in results)

    @pytest.mark.asyncio
    async def test_category_filter(self, store: MemoryStore) -> None:
        await store.save(content="A deep thought", category="philosophical")
        await store.save(content="A daily event", category="daily")

        results = await store.search("thought", category_filter="philosophical")
        assert all(r.memory.category.value == "philosophical" for r in results)

    @pytest.mark.asyncio
    async def test_valence_range_filter(self, store: MemoryStore) -> None:
        await store.save(content="Negative memory", valence=-0.7, arousal=0.4)
        await store.save(content="Positive memory", valence=0.8, arousal=0.6)
        results = await store.search("memory", valence_range=[-1.0, -0.3])
        assert len(results) >= 1
        assert all(-1.0 <= r.memory.emotional_trace.valence <= -0.3 for r in results)

    @pytest.mark.asyncio
    async def test_arousal_range_filter(self, store: MemoryStore) -> None:
        await store.save(content="Calm memory", valence=0.0, arousal=0.2)
        await store.save(content="Energetic memory", valence=0.0, arousal=0.9)
        results = await store.search("memory", arousal_range=[0.0, 0.4])
        assert len(results) >= 1
        assert all(0.0 <= r.memory.emotional_trace.arousal <= 0.4 for r in results)

    @pytest.mark.asyncio
    async def test_emotional_post_filter_uses_overfetch(
        self, store: MemoryStore
    ) -> None:
        class FakeCollection:
            def __init__(self) -> None:
                self.last_n_results = 0

            def count(self) -> int:
                return 50

            def query(self, **kwargs: Any) -> dict[str, Any]:
                self.last_n_results = int(kwargs["n_results"])
                ids = [f"mem_{i}" for i in range(20)]
                docs = [f"memory {i}" for i in range(20)]
                metas: list[dict[str, object]] = []
                distances: list[float] = []
                for i in range(20):
                    metas.append(
                        {
                            "emotion": "neutral",
                            "importance": 3,
                            "category": "daily",
                            "timestamp": "2026-02-20T00:00:00+00:00",
                            "valence": 0.8 if i < 15 else -0.7,
                            "arousal": 0.5,
                            "linked_ids": "[]",
                        }
                    )
                    distances.append(0.1)
                return {
                    "ids": [ids],
                    "documents": [docs],
                    "metadatas": [metas],
                    "distances": [distances],
                }

        fake = FakeCollection()
        store._collection = fake
        results = await store.search("memory", n_results=3, valence_range=[-1.0, -0.3])
        assert fake.last_n_results >= 20
        assert len(results) == 3
        assert all(-1.0 <= r.memory.emotional_trace.valence <= -0.3 for r in results)


class TestMemoryGetById:
    @pytest.mark.asyncio
    async def test_get_existing(self, store: MemoryStore) -> None:
        mem = await store.save(content="Find me later")
        found = await store.get_by_id(mem.id)
        assert found is not None
        assert found.content == "Find me later"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store: MemoryStore) -> None:
        found = await store.get_by_id("nonexistent_id")
        assert found is None


class TestMemoryDelete:
    @pytest.mark.asyncio
    async def test_delete_unlinked_memory_returns_deleted_memory(
        self, store: MemoryStore
    ) -> None:
        mem = await store.save(content="delete me")

        deleted = await store.delete(mem.id)

        assert deleted is not None
        assert deleted.id == mem.id
        assert deleted.content == "delete me"
        assert await store.get_by_id(mem.id) is None

    @pytest.mark.asyncio
    async def test_delete_removes_reverse_link_from_target(self, store: MemoryStore) -> None:
        source = await store.save(content="source memory")
        target = await store.save(content="target memory")
        created = await store.link_memories(source.id, target.id)
        assert created is True

        before = await store.get_by_id(target.id)
        assert before is not None
        assert any(link.target_id == source.id for link in before.linked_ids)

        deleted = await store.delete(source.id)

        assert deleted is not None
        after = await store.get_by_id(target.id)
        assert after is not None
        assert all(link.target_id != source.id for link in after.linked_ids)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_none(self, store: MemoryStore) -> None:
        deleted = await store.delete("nonexistent_id")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_decrements_collection_count(self, store: MemoryStore) -> None:
        first = await store.save(content="one")
        await store.save(content="two")
        before = store.collection_count()

        deleted = await store.delete(first.id)

        assert deleted is not None
        assert store.collection_count() == before - 1


class TestMemoryLinking:
    @pytest.mark.asyncio
    async def test_link_memories_returns_false_when_either_side_is_missing(
        self, store: MemoryStore
    ) -> None:
        created = await store.link_memories("mem_missing_a", "mem_missing_b")
        assert created is False

    @pytest.mark.asyncio
    async def test_link_memories_is_idempotent(self, store: MemoryStore) -> None:
        source = await store.save(content="source for idempotent link")
        target = await store.save(content="target for idempotent link")

        first = await store.link_memories(source.id, target.id, link_type="related")
        second = await store.link_memories(source.id, target.id, link_type="related")

        assert first is True
        assert second is False
        reloaded = await store.get_by_id(source.id)
        assert reloaded is not None
        assert [link.target_id for link in reloaded.linked_ids].count(target.id) == 1

    @pytest.mark.asyncio
    async def test_bump_link_confidence_creates_link_and_caps_at_one(
        self, store: MemoryStore
    ) -> None:
        source = await store.save(content="source for confidence bump")
        target = await store.save(content="target for confidence bump")

        created = await store.bump_link_confidence(source.id, target.id, delta=0.8)
        assert created is True

        source_reloaded = await store.get_by_id(source.id)
        target_reloaded = await store.get_by_id(target.id)
        assert source_reloaded is not None
        assert target_reloaded is not None

        source_link = next(
            link for link in source_reloaded.linked_ids if link.target_id == target.id
        )
        target_link = next(
            link for link in target_reloaded.linked_ids if link.target_id == source.id
        )
        assert source_link.confidence == pytest.approx(1.0)
        assert target_link.confidence == pytest.approx(1.0)

        unchanged = await store.bump_link_confidence(source.id, target.id, delta=0.5)
        assert unchanged is False


class TestMemoryFallbacks:
    @pytest.mark.asyncio
    async def test_save_unknown_emotion_and_category_falls_back_to_defaults(
        self, store: MemoryStore
    ) -> None:
        mem = await store.save(
            content="unknown emotion/category",
            emotion="not-an-emotion",
            secondary=["happy", "not-an-emotion"],
            category="not-a-category",
        )

        assert mem.emotional_trace.primary == Emotion.NEUTRAL
        assert [emotion.value for emotion in mem.emotional_trace.secondary] == ["happy"]
        assert mem.category.value == "daily"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_collection_errors(
        self, store: MemoryStore
    ) -> None:
        class BrokenCollection:
            def get(self, **_kwargs: Any) -> dict[str, Any]:
                raise KeyError("broken metadata")

        store._collection = BrokenCollection()
        found = await store.get_by_id("mem_any")
        assert found is None
