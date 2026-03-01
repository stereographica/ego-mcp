"""Focused tests for query helpers in ``_memory_queries``."""

from __future__ import annotations

from typing import Any, cast

import pytest

from ego_mcp import _memory_queries


def _metadata(timestamp: str, *, category: str = "daily") -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "category": category,
        "emotion": "neutral",
        "intensity": 0.5,
        "valence": 0.0,
        "arousal": 0.5,
    }


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
