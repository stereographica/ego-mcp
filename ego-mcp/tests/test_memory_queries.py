"""Focused tests for query helpers in ``_memory_queries``."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ego_mcp import _memory_queries
from ego_mcp._memory_serialization import links_to_json
from ego_mcp.types import LinkType, Memory, MemoryLink


class _FakeCollection:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any]]]) -> None:
        self._rows = rows

    def count(self) -> int:
        return len(self._rows)

    def get(
        self,
        *,
        limit: int,
        include: list[str],
        where: dict[str, str] | None = None,
    ) -> dict[str, list[Any]]:
        assert include == ["documents", "metadatas"]
        filtered = self._rows
        if where is not None:
            filtered = [
                row for row in filtered if row[2].get("category") == where.get("category")
            ]
        selected = filtered[:limit]
        ids = [row[0] for row in selected]
        documents = [row[1] for row in selected]
        metadatas = [row[2] for row in selected]
        return {"ids": ids, "documents": documents, "metadatas": metadatas}


class _FakeStore:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any]]]) -> None:
        self._collection = _FakeCollection(rows)

    def _ensure_connected(self) -> _FakeCollection:
        return self._collection


def _metadata(
    timestamp: str,
    *,
    category: str = "daily",
    linked_ids: list[MemoryLink] | None = None,
    access_count: int = 0,
    last_accessed: str = "",
    importance: int = 3,
    emotion: str = "neutral",
    valence: float = 0.0,
    arousal: float = 0.5,
) -> dict[str, Any]:
    payload = {
        "timestamp": timestamp,
        "category": category,
        "emotion": emotion,
        "intensity": 0.5,
        "valence": valence,
        "arousal": arousal,
        "importance": importance,
        "access_count": access_count,
        "last_accessed": last_accessed,
    }
    if linked_ids is not None:
        payload["linked_ids"] = links_to_json(linked_ids)
    return payload


class _AdvancedCollection:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any], float]]) -> None:
        self.rows = rows
        self.updated: list[tuple[list[str], list[dict[str, Any]]]] = []

    def count(self) -> int:
        return len(self.rows)

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        include: list[str],
        where: dict[str, Any] | None = None,
    ) -> dict[str, list[list[Any]]]:
        del query_texts
        assert include == ["documents", "metadatas", "distances"]
        selected = [
            row for row in self.rows if self._matches_where(row[2], where)
        ][:n_results]
        return {
            "ids": [[row[0] for row in selected]],
            "documents": [[row[1] for row in selected]],
            "metadatas": [[row[2] for row in selected]],
            "distances": [[row[3] for row in selected]],
        }

    def _matches_where(
        self,
        metadata: dict[str, Any],
        where: dict[str, Any] | None,
    ) -> bool:
        if where is None:
            return True
        clauses = where.get("$and")
        if isinstance(clauses, list):
            return all(
                self._matches_where(metadata, clause)
                for clause in clauses
                if isinstance(clause, dict)
            )
        return all(metadata.get(key) == value for key, value in where.items())

    def get(
        self,
        *,
        ids: list[str],
        include: list[str],
    ) -> dict[str, list[Any]]:
        assert include in (["documents", "metadatas"], ["embeddings"])
        found = [row for row in self.rows if row[0] in ids]
        payload: dict[str, list[Any]] = {"ids": [row[0] for row in found]}
        if include == ["embeddings"]:
            payload["embeddings"] = [[float(index), 0.0, 0.0] for index, _row in enumerate(found)]
        else:
            payload["documents"] = [row[1] for row in found]
            payload["metadatas"] = [row[2] for row in found]
        return payload

    def update(self, *, ids: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.updated.append((ids, metadatas))
        row_by_id = {row[0]: index for index, row in enumerate(self.rows)}
        for memory_id, metadata in zip(ids, metadatas):
            row_index = row_by_id.get(memory_id)
            if row_index is None:
                continue
            row_id, row_doc, row_meta, row_distance = self.rows[row_index]
            self.rows[row_index] = (
                row_id,
                row_doc,
                {**row_meta, **metadata},
                row_distance,
            )


class _AdvancedStore:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any], float]]) -> None:
        self._collection = _AdvancedCollection(rows)
        self._last_recall_metadata: dict[str, object] = {}
        self._candidate_ids: list[str] = []
        self._hopfield = SimpleNamespace(
            store=self._store_hopfield,
            retrieve=self._retrieve_hopfield,
            recall_results=self._recall_results,
        )
        self._embedding_fn = lambda texts: [[0.0, 0.0, 0.0] for _text in texts]

    def _ensure_connected(self) -> _AdvancedCollection:
        return self._collection

    @property
    def last_recall_metadata(self) -> dict[str, object]:
        return dict(self._last_recall_metadata)

    def _store_hopfield(
        self,
        _embeddings: list[list[float]],
        ids: list[str],
        _contents: list[str],
    ) -> None:
        self._candidate_ids = list(ids)

    def _retrieve_hopfield(self, _query_embedding: list[float]) -> tuple[list[float], list[float]]:
        similarities = [1.0 - index * 0.2 for index, _memory_id in enumerate(self._candidate_ids)]
        return [0.0, 0.0, 0.0], similarities

    def _recall_results(
        self,
        similarities: list[float],
        k: int,
    ) -> list[Any]:
        ranked = sorted(
            enumerate(self._candidate_ids),
            key=lambda item: similarities[item[0]],
            reverse=True,
        )[:k]
        return [
            SimpleNamespace(memory_id=memory_id, hopfield_score=similarities[index])
            for index, memory_id in ranked
        ]


class TestListRecent:
    @pytest.mark.asyncio
    async def test_reads_full_collection_before_sorting(self) -> None:
        rows = [
            (
                f"mem_{index:02d}",
                f"memory {index}",
                _metadata(f"2026-01-{index + 1:02d}T00:00:00+00:00"),
            )
            for index in range(10)
        ]
        store = _FakeStore(rows)

        recent = await _memory_queries.list_recent(cast(Any, store), n=1)

        assert [memory.id for memory in recent] == ["mem_09"]

    @pytest.mark.asyncio
    async def test_reads_full_filtered_collection_before_sorting(self) -> None:
        filtered_rows = [
            (
                f"mem_i_{index:02d}",
                f"introspection {index}",
                _metadata(
                    f"2026-02-{index + 1:02d}T00:00:00+00:00",
                    category="introspection",
                ),
            )
            for index in range(10)
        ]
        unfiltered_rows = [
            (
                f"mem_d_{index:02d}",
                f"daily {index}",
                _metadata(f"2026-01-{index + 1:02d}T00:00:00+00:00"),
            )
            for index in range(10)
        ]
        store = _FakeStore([*filtered_rows, *unfiltered_rows])

        recent = await _memory_queries.list_recent(
            cast(Any, store),
            n=2,
            category_filter="introspection",
        )

        assert [memory.id for memory in recent] == ["mem_i_09", "mem_i_08"]


class TestResurfacingAndRecall:
    @pytest.mark.asyncio
    async def test_find_resurfacing_memories_updates_access_metadata(self) -> None:
        rows = [
            (
                "mem_recent",
                "recent signal",
                _metadata("2026-02-26T00:00:00+00:00"),
                0.12,
            ),
            (
                "mem_dormant",
                "dormant pattern",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    access_count=1,
                ),
                0.08,
            ),
        ]
        store = _AdvancedStore(rows)

        resurfacing = await _memory_queries.find_resurfacing_memories(
            cast(Any, store),
            "dormant pattern",
            exclude_ids={"mem_recent"},
        )

        assert [result.memory.id for result in resurfacing] == ["mem_dormant"]
        assert store._collection.updated == [
            (
                ["mem_dormant"],
                [
                    {
                        "access_count": 2,
                        "last_accessed": resurfacing[0].memory.last_accessed,
                    }
                ],
            )
        ]
        assert resurfacing[0].decay < 0.3

    @pytest.mark.asyncio
    async def test_recall_can_surface_proust_memory_and_expose_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            (
                "mem_anchor",
                "anchor memory",
                _metadata("2026-02-26T00:00:00+00:00"),
                0.04,
            ),
            (
                "mem_proust",
                "dormant resurfacing signal",
                _metadata("2024-02-20T00:00:00+00:00"),
                0.08,
            ),
            (
                "mem_other",
                "other memory",
                _metadata("2026-02-25T00:00:00+00:00"),
                0.18,
            ),
        ]
        store = _AdvancedStore(rows)

        async def fake_get_by_id(_store: Any, memory_id: str) -> Any:
            if memory_id == "mem_proust":
                return Memory(
                    id="mem_proust",
                    content="dormant resurfacing signal",
                    timestamp="2024-02-20T00:00:00+00:00",
                    linked_ids=[],
                    access_count=0,
                )
            return None

        monkeypatch.setattr(_memory_queries, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(random, "random", lambda: 0.0)

        results = await _memory_queries.recall(
            cast(Any, store),
            "dormant resurfacing signal",
            n_results=1,
            proust_probability=1.0,
        )

        assert [result.memory.id for result in results] == ["mem_anchor", "mem_proust"]
        assert results[-1].is_proust is True
        assert store.last_recall_metadata["proust_triggered"] is True
        assert store.last_recall_metadata["proust_memory_id"] == "mem_proust"
        assert cast(int, store.last_recall_metadata["fuzzy_recall_count"]) >= 1
        assert store._collection.updated

    @pytest.mark.asyncio
    async def test_recall_spreading_activation_expands_linked_memories(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            (
                "mem_anchor",
                "anchor memory",
                _metadata(
                    "2026-02-26T00:00:00+00:00",
                    linked_ids=[
                        MemoryLink(
                            target_id="mem_spread",
                            link_type=LinkType.RELATED,
                            confidence=0.9,
                        )
                    ],
                ),
                0.02,
            ),
            (
                "mem_spread",
                "spread target",
                _metadata("2026-02-25T00:00:00+00:00"),
                0.20,
            ),
        ]
        store = _AdvancedStore(rows)

        async def fake_get_by_id(_store: Any, memory_id: str) -> Any:
            if memory_id == "mem_spread":
                return Memory(
                    id="mem_spread",
                    content="spread target",
                    timestamp="2026-02-25T00:00:00+00:00",
                    linked_ids=[],
                )
            return None

        monkeypatch.setattr(_memory_queries, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(random, "random", lambda: 1.0)

        results = await _memory_queries.recall(
            cast(Any, store),
            "anchor memory",
            n_results=2,
            proust_probability=0.0,
        )

        assert [result.memory.id for result in results] == ["mem_anchor", "mem_spread"]

    @pytest.mark.asyncio
    async def test_recall_with_category_filter_skips_spreading_activation(self) -> None:
        rows = [
            (
                "mem_anchor",
                "anchor memory",
                _metadata(
                    "2026-02-26T00:00:00+00:00",
                    category="daily",
                    linked_ids=[
                        MemoryLink(
                            target_id="mem_spread",
                            link_type=LinkType.RELATED,
                            confidence=0.9,
                        )
                    ],
                ),
                0.02,
            ),
            (
                "mem_spread",
                "spread target",
                _metadata("2026-02-25T00:00:00+00:00", category="technical"),
                0.03,
            ),
        ]
        store = _AdvancedStore(rows)

        results = await _memory_queries.recall(
            cast(Any, store),
            "anchor memory",
            n_results=2,
            category_filter="daily",
            proust_probability=0.0,
        )

        assert [result.memory.id for result in results] == ["mem_anchor"]
        assert store.last_recall_metadata["proust_triggered"] is False

    @pytest.mark.asyncio
    async def test_recall_increments_access_count_and_last_accessed(self) -> None:
        rows = [
            (
                "mem_anchor",
                "anchor memory",
                _metadata("2026-02-26T00:00:00+00:00"),
                0.02,
            )
        ]
        store = _AdvancedStore(rows)

        results = await _memory_queries.recall(
            cast(Any, store),
            "anchor memory",
            n_results=1,
            proust_probability=0.0,
        )

        assert [result.memory.id for result in results] == ["mem_anchor"]
        assert store._collection.updated
        ids, metadatas = store._collection.updated[-1]
        assert ids == ["mem_anchor"]
        assert metadatas[0]["access_count"] == 1
        assert isinstance(metadatas[0]["last_accessed"], str)
        assert metadatas[0]["last_accessed"]

    @pytest.mark.asyncio
    async def test_search_does_not_increment_access_count(self) -> None:
        rows = [
            (
                "mem_anchor",
                "anchor memory",
                _metadata("2026-02-26T00:00:00+00:00"),
                0.02,
            )
        ]
        store = _AdvancedStore(rows)

        results = await _memory_queries.search(
            cast(Any, store),
            "anchor memory",
            n_results=1,
        )

        assert [result.memory.id for result in results] == ["mem_anchor"]
        assert store._collection.updated == []

    @pytest.mark.asyncio
    async def test_recall_candidate_pool_includes_dormant_memories_for_hopfield(
        self,
    ) -> None:
        rows = [
            (
                f"mem_recent_{index}",
                f"recent memory {index}",
                _metadata("2026-02-26T00:00:00+00:00"),
                0.01 + index * 0.01,
            )
            for index in range(10)
        ]
        rows.append(
            (
                "mem_dormant",
                "dormant pattern",
                _metadata("2024-02-20T00:00:00+00:00"),
                0.25,
            )
        )
        store = _AdvancedStore(rows)

        await _memory_queries.recall(
            cast(Any, store),
            "dormant pattern",
            n_results=3,
            proust_probability=0.0,
        )

        assert "mem_dormant" in store._candidate_ids

    @pytest.mark.asyncio
    async def test_sample_dormant_memories_ignores_importance_bias(self) -> None:
        rows = [
            (
                "mem_low",
                "low importance but closest",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=1,
                    emotion="neutral",
                ),
                0.10,
            ),
            (
                "mem_hi_1",
                "high importance one",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=5,
                    emotion="excited",
                ),
                0.11,
            ),
            (
                "mem_hi_2",
                "high importance two",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=5,
                    emotion="excited",
                ),
                0.12,
            ),
            (
                "mem_hi_3",
                "high importance three",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=5,
                    emotion="excited",
                ),
                0.13,
            ),
            (
                "mem_hi_4",
                "high importance four",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=5,
                    emotion="excited",
                ),
                0.14,
            ),
            (
                "mem_hi_5",
                "high importance five",
                _metadata(
                    "2024-02-20T00:00:00+00:00",
                    importance=5,
                    emotion="excited",
                ),
                0.15,
            ),
        ]
        store = _AdvancedStore(rows)

        candidates = await _memory_queries._sample_dormant_memories(
            cast(Any, store),
            "closest",
            max_candidates=5,
        )

        assert len(candidates) == 5
        assert "mem_low" in [result.memory.id for result in candidates]
