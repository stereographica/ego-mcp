"""Tests for consolidation engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import MemoryStore


class FakeEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = hash(text) % 1000
            vec = [((seed + i) % 100) / 100.0 for i in range(64)]
            norm = sum(x * x for x in vec) ** 0.5
            vectors.append([x / norm for x in vec])
        return vectors


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EgoConfig:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
    return EgoConfig.from_env()


@pytest.fixture
def store(config: EgoConfig) -> MemoryStore:
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    fn = EgoEmbeddingFunction(provider)
    s = MemoryStore(config, fn)
    s.connect()
    yield s
    s.close()


class TestConsolidationEngine:
    @pytest.mark.asyncio
    async def test_replay_increases_coactivation(self, store: MemoryStore) -> None:
        m1 = await store.save(content="First memory")
        m2 = await store.save(content="Second memory")
        engine = ConsolidationEngine()
        stats = await engine.run(store, window_hours=24)
        left = await store.get_by_id(m1.id)
        assert left is not None
        link = next((item for item in left.linked_ids if item.target_id == m2.id), None)

        assert stats.replay_events >= 1
        assert stats.coactivation_updates >= 1
        assert link is not None
        assert link.confidence > 0.5

    @pytest.mark.asyncio
    async def test_empty_data_safe(self, store: MemoryStore) -> None:
        engine = ConsolidationEngine()
        stats = await engine.run(store, window_hours=24)
        assert stats.replay_events == 0
        assert stats.link_updates == 0
