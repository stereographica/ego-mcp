"""Tests for episode storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.config import EgoConfig
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore

chromadb = load_chromadb()


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
def episode_store(config: EgoConfig) -> tuple[MemoryStore, EpisodeStore]:
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    fn = EgoEmbeddingFunction(provider)
    memory = MemoryStore(config, fn)
    memory.connect()
    client = chromadb.PersistentClient(path=str(config.data_dir / "chroma"))
    collection = client.get_or_create_collection(name="ego_episodes", embedding_function=fn)
    return memory, EpisodeStore(memory, collection)


class TestEpisodeStore:
    @pytest.mark.asyncio
    async def test_create_search_get(self, episode_store: tuple[MemoryStore, EpisodeStore]) -> None:
        memory, store = episode_store
        m1 = await memory.save(content="Went for a morning walk")
        m2 = await memory.save(content="Had coffee and planned the day")
        created = await store.create([m1.id, m2.id], "Morning routine with planning")
        assert created.id.startswith("ep_")
        assert len(created.memory_ids) == 2

        found = await store.search("morning routine", n_results=3)
        assert any(ep.id == created.id for ep in found)

        loaded = await store.get_by_id(created.id)
        assert loaded is not None
        assert loaded.summary == "Morning routine with planning"

    @pytest.mark.asyncio
    async def test_invalid_id_returns_none(
        self, episode_store: tuple[MemoryStore, EpisodeStore]
    ) -> None:
        _, store = episode_store
        loaded = await store.get_by_id("ep_missing")
        assert loaded is None
