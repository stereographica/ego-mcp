"""Tests for associative expansion."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ego_mcp.association import AssociationEngine
from ego_mcp.config import EgoConfig
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
def store(config: EgoConfig) -> Iterator[MemoryStore]:
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    fn = EgoEmbeddingFunction(provider)
    s = MemoryStore(config, fn)
    s.connect()
    yield s
    s.close()


class TestAssociationEngine:
    @pytest.mark.asyncio
    async def test_multi_hop_expansion(self, store: MemoryStore) -> None:
        a = await store.save(content="alpha memory")
        b = await store.save(content="beta memory")
        c = await store.save(content="gamma memory")
        await store.link_memories(a.id, b.id, "related")
        await store.link_memories(b.id, c.id, "related")

        engine = AssociationEngine()
        results = await engine.spread([a.id], memory_store=store, depth=2, top_k=10)
        ids = [r.memory_id for r in results]
        assert b.id in ids
        assert c.id in ids

    @pytest.mark.asyncio
    async def test_depth_limit(self, store: MemoryStore) -> None:
        a = await store.save(content="A")
        b = await store.save(content="B")
        c = await store.save(content="C")
        await store.link_memories(a.id, b.id, "related")
        await store.link_memories(b.id, c.id, "related")

        engine = AssociationEngine(implicit_weight=0.0)
        results = await engine.spread([a.id], memory_store=store, depth=1, top_k=10)
        ids = [r.memory_id for r in results]
        assert b.id in ids
        assert c.id not in ids

    @pytest.mark.asyncio
    async def test_deduplicate_candidates(self, store: MemoryStore) -> None:
        a = await store.save(content="shared topic: architecture")
        b = await store.save(content="shared topic: architecture and design")
        await store.link_memories(a.id, b.id, "related")

        engine = AssociationEngine()
        results = await engine.spread([a.id], memory_store=store, depth=2, top_k=10)
        ids = [r.memory_id for r in results]
        assert ids.count(b.id) == 1
