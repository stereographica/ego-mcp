"""Tests for consolidation engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import (
    ConsolidationEngine,
    ConsolidationStats,
    MergeCandidate,
)
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import MemoryStore
from ego_mcp.types import Memory, MemorySearchResult


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


class TestConsolidationEngine:
    @staticmethod
    def _result(memory: Memory, distance: float) -> MemorySearchResult:
        return MemorySearchResult(memory=memory, distance=distance, score=distance)

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
        assert stats.merge_candidates == ()

    @pytest.mark.asyncio
    async def test_detects_merge_candidates(self, store: MemoryStore) -> None:
        m1 = await store.save(content="merge candidate alpha")
        m2 = await store.save(content="merge candidate beta")
        m3 = await store.save(content="unrelated memory")
        mapping: dict[str, list[MemorySearchResult]] = {
            m1.content: [
                self._result(m1, 0.0),
                self._result(m2, 0.05),
                self._result(m3, 0.40),
            ],
            m2.content: [
                self._result(m2, 0.0),
                self._result(m1, 0.05),
            ],
            m3.content: [self._result(m3, 0.0)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            return list(mapping.get(query, []))

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(store, "search", fake_search)
        try:
            stats = await engine.run(store, window_hours=24, merge_threshold=0.10)
        finally:
            monkeypatch.undo()

        assert len(stats.merge_candidates) == 1
        candidate = stats.merge_candidates[0]
        assert {candidate.memory_a_id, candidate.memory_b_id} == {m1.id, m2.id}
        assert candidate.distance == pytest.approx(0.05)
        assert candidate.snippet_a == m1.content[:100] or candidate.snippet_a == m2.content[:100]
        assert candidate.snippet_b == m1.content[:100] or candidate.snippet_b == m2.content[:100]

    @pytest.mark.asyncio
    async def test_merge_threshold_filters_out_candidates(
        self, store: MemoryStore
    ) -> None:
        m1 = await store.save(content="threshold left")
        m2 = await store.save(content="threshold right")
        mapping = {
            m1.content: [self._result(m1, 0.0), self._result(m2, 0.11)],
            m2.content: [self._result(m2, 0.0), self._result(m1, 0.11)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            return list(mapping.get(query, []))

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(store, "search", fake_search)
        try:
            stats = await engine.run(store, window_hours=24, merge_threshold=0.10)
        finally:
            monkeypatch.undo()

        assert stats.merge_candidates == ()

    @pytest.mark.asyncio
    async def test_max_merge_candidates_limits_results(self, store: MemoryStore) -> None:
        m1 = await store.save(content="limit pair 1a")
        m2 = await store.save(content="limit pair 1b")
        m3 = await store.save(content="limit pair 2a")
        m4 = await store.save(content="limit pair 2b")
        m5 = await store.save(content="limit pair 3a")
        m6 = await store.save(content="limit pair 3b")
        mapping = {
            m1.content: [self._result(m1, 0.0), self._result(m2, 0.05)],
            m2.content: [self._result(m2, 0.0), self._result(m1, 0.05)],
            m3.content: [self._result(m3, 0.0), self._result(m4, 0.05)],
            m4.content: [self._result(m4, 0.0), self._result(m3, 0.05)],
            m5.content: [self._result(m5, 0.0), self._result(m6, 0.05)],
            m6.content: [self._result(m6, 0.0), self._result(m5, 0.05)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            return list(mapping.get(query, []))

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(store, "search", fake_search)
        try:
            stats = await engine.run(
                store,
                window_hours=24,
                merge_threshold=0.10,
                max_merge_candidates=2,
            )
        finally:
            monkeypatch.undo()

        assert len(stats.merge_candidates) == 2

    @pytest.mark.asyncio
    async def test_merge_candidate_pairs_are_not_duplicated(
        self, store: MemoryStore
    ) -> None:
        m1 = await store.save(content="dedupe pair left")
        m2 = await store.save(content="dedupe pair right")
        mapping = {
            m1.content: [self._result(m1, 0.0), self._result(m2, 0.03)],
            m2.content: [self._result(m2, 0.0), self._result(m1, 0.03)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            return list(mapping.get(query, []))

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(store, "search", fake_search)
        try:
            stats = await engine.run(store, window_hours=24)
        finally:
            monkeypatch.undo()

        assert len(stats.merge_candidates) == 1

    def test_to_dict_includes_merge_candidates(self) -> None:
        stats = ConsolidationStats(
            replay_events=1,
            coactivation_updates=2,
            link_updates=3,
            refreshed_memories=4,
            merge_candidates=(
                MergeCandidate(
                    memory_a_id="mem_a",
                    memory_b_id="mem_b",
                    distance=0.07,
                    snippet_a="alpha",
                    snippet_b="beta",
                ),
            ),
        )
        payload = stats.to_dict()
        assert "merge_candidates" in payload
        merge_candidates = payload["merge_candidates"]
        assert isinstance(merge_candidates, list)
        assert merge_candidates[0]["memory_a_id"] == "mem_a"
        assert merge_candidates[0]["distance"] == pytest.approx(0.07)

    @pytest.mark.asyncio
    async def test_no_similar_memories_yields_empty_merge_candidates(
        self, store: MemoryStore
    ) -> None:
        m1 = await store.save(content="no similar 1")
        m2 = await store.save(content="no similar 2")
        mapping = {
            m1.content: [self._result(m1, 0.0)],
            m2.content: [self._result(m2, 0.0)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            return list(mapping.get(query, []))

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(store, "search", fake_search)
        try:
            stats = await engine.run(store, window_hours=24, merge_threshold=0.10)
        finally:
            monkeypatch.undo()

        assert stats.merge_candidates == ()

    @pytest.mark.asyncio
    async def test_single_recent_memory_still_checks_merge_candidates(
        self,
        store: MemoryStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        recent_memory = await store.save(content="single recent memory")
        older_memory = await store.save(content="older duplicate-ish memory")

        async def fake_list_recent(*_args: object, **_kwargs: object) -> list[Memory]:
            return [recent_memory]

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            if query == recent_memory.content:
                return [
                    self._result(recent_memory, 0.0),
                    self._result(older_memory, 0.08),
                ]
            return []

        monkeypatch.setattr(store, "list_recent", fake_list_recent)
        monkeypatch.setattr(store, "search", fake_search)

        engine = ConsolidationEngine()
        stats = await engine.run(store, window_hours=24, merge_threshold=0.10)

        assert stats.replay_events == 0
        assert len(stats.merge_candidates) == 1
        pair = stats.merge_candidates[0]
        assert {pair.memory_a_id, pair.memory_b_id} == {recent_memory.id, older_memory.id}
