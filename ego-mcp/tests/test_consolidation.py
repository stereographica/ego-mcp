"""Tests for consolidation engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

import ego_mcp._server_backend_handlers as backend_handlers_mod
from ego_mcp._memory_serialization import links_to_json
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import (
    ConsolidationEngine,
    ConsolidationStats,
    MergeCandidate,
)
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import NotionStore
from ego_mcp.types import Emotion, LinkType, Memory, MemoryLink, MemorySearchResult


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
            pruned_links=5,
            emotion_links=6,
            theme_links=7,
            cross_category_links=8,
            notions_created=9,
            detected_clusters=(("mem_a", "mem_b", "mem_c"),),
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
        assert payload["pruned_links"] == 5
        assert payload["emotion_links"] == 6
        assert payload["theme_links"] == 7
        assert payload["cross_category_links"] == 8
        assert payload["notions_created"] == 9
        assert payload["detected_clusters"] == [["mem_a", "mem_b", "mem_c"]]

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

    @pytest.mark.asyncio
    async def test_detected_clusters_reports_fully_connected_groups(
        self, store: MemoryStore
    ) -> None:
        m1 = await store.save(content="cluster alpha", tags=["shared"])
        m2 = await store.save(content="cluster beta", tags=["shared"])
        m3 = await store.save(content="cluster gamma", tags=["shared"])

        await store.link_memories(m1.id, m2.id)
        await store.link_memories(m1.id, m3.id)
        await store.link_memories(m2.id, m3.id)

        engine = ConsolidationEngine()
        stats = await engine.run(store, window_hours=24)

        assert any(set(cluster) == {m1.id, m2.id, m3.id} for cluster in stats.detected_clusters)

    @pytest.mark.asyncio
    async def test_run_prunes_low_confidence_links(self, store: MemoryStore) -> None:
        left = await store.save(content="fragile left")
        right = await store.save(content="fragile right")
        collection = store._ensure_connected()
        collection.update(
            ids=[left.id, right.id],
            metadatas=[
                {
                    "linked_ids": links_to_json(
                        [
                            MemoryLink(
                                target_id=right.id,
                                link_type=LinkType.RELATED,
                                confidence=0.05,
                            )
                        ]
                    )
                },
                {
                    "linked_ids": links_to_json(
                        [
                            MemoryLink(
                                target_id=left.id,
                                link_type=LinkType.RELATED,
                                confidence=0.05,
                            )
                        ]
                    )
                },
            ],
        )

        engine = ConsolidationEngine()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            ConsolidationEngine,
            "_collect_replay_targets",
            staticmethod(lambda _memories, _cutoff: []),
        )
        try:
            stats = await engine.run(store, window_hours=24)
        finally:
            monkeypatch.undo()
        left_after = await store.get_by_id(left.id)
        right_after = await store.get_by_id(right.id)

        assert stats.pruned_links == 2
        assert left_after is not None and left_after.linked_ids == []
        assert right_after is not None and right_after.linked_ids == []

    @pytest.mark.asyncio
    async def test_run_adds_emotional_thematic_and_cross_category_links(
        self,
        store: MemoryStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        emotion_a = await store.save(
            content="emotion anchor",
            emotion="curious",
            intensity=0.6,
        )
        theme_a = await store.save(
            content="theme anchor",
            emotion="sad",
            tags=["pattern", "signal"],
        )
        cross_a = await store.save(
            content="cross anchor",
            category="daily",
            emotion="neutral",
        )
        emotion_b = await store.save(
            content="emotion pair",
            emotion="curious",
            intensity=0.67,
        )
        theme_b = await store.save(
            content="theme pair",
            emotion="happy",
            tags=["pattern", "signal"],
        )
        cross_b = await store.save(
            content="cross pair",
            category="technical",
            emotion="happy",
        )

        ordered_recent = [emotion_a, theme_a, cross_a, emotion_b, theme_b, cross_b]
        monkeypatch.setattr(
            ConsolidationEngine,
            "_collect_replay_targets",
            staticmethod(lambda _memories, _cutoff: ordered_recent),
        )

        mapping: dict[str, list[MemorySearchResult]] = {
            cross_a.content: [self._result(cross_a, 0.0), self._result(cross_b, 0.20)],
            cross_b.content: [self._result(cross_b, 0.0), self._result(cross_a, 0.20)],
        }

        async def fake_search(query: str, **_kwargs: object) -> list[MemorySearchResult]:
            memory_map = {
                emotion_a.content: emotion_a,
                theme_a.content: theme_a,
                cross_a.content: cross_a,
                emotion_b.content: emotion_b,
                theme_b.content: theme_b,
                cross_b.content: cross_b,
            }
            current = memory_map[query]
            return list(mapping.get(query, [self._result(current, 0.0)]))

        monkeypatch.setattr(store, "search", fake_search)

        stats = await ConsolidationEngine().run(store, window_hours=24)
        emotion_loaded = await store.get_by_id(emotion_a.id)
        theme_loaded = await store.get_by_id(theme_a.id)
        cross_loaded = await store.get_by_id(cross_a.id)

        assert stats.emotion_links == 1
        assert stats.theme_links == 1
        assert stats.cross_category_links == 1
        assert emotion_loaded is not None and any(
            link.target_id == emotion_b.id for link in emotion_loaded.linked_ids
        )
        assert theme_loaded is not None and any(
            link.target_id == theme_b.id for link in theme_loaded.linked_ids
        )
        assert cross_loaded is not None and any(
            link.target_id == cross_b.id for link in cross_loaded.linked_ids
        )

    @pytest.mark.asyncio
    async def test_handle_consolidate_creates_notion_from_detected_cluster(
        self,
        config: EgoConfig,
        store: MemoryStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        notion_store = NotionStore(config.data_dir / "notions.json")
        monkeypatch.setattr(
            backend_handlers_mod,
            "get_notion_store",
            lambda: notion_store,
        )

        m1 = await store.save(
            content="cluster alpha signal",
            emotion=Emotion.CURIOUS.value,
            valence=0.4,
            tags=["pattern", "signal"],
        )
        m2 = await store.save(
            content="cluster beta signal",
            emotion=Emotion.CURIOUS.value,
            valence=0.2,
            tags=["pattern", "signal"],
        )
        m3 = await store.save(
            content="cluster gamma signal",
            emotion=Emotion.CURIOUS.value,
            valence=0.3,
            tags=["pattern", "signal"],
        )
        await store.link_memories(m1.id, m2.id)
        await store.link_memories(m1.id, m3.id)
        await store.link_memories(m2.id, m3.id)

        result = await backend_handlers_mod._handle_consolidate(
            store,
            ConsolidationEngine(),
        )
        notions = notion_store.list_all()

        assert "Created 1 notion(s)." in result
        assert len(notions) == 1
        assert set(notions[0].source_memory_ids) == {m1.id, m2.id, m3.id}
        assert notions[0].tags == ["pattern", "signal"]
