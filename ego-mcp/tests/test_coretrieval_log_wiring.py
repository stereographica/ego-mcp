"""Recall-side wiring of the co-retrieval append log (P1 S1).

What came back together is written to ``derived/co_retrieval.jsonl`` and nowhere
else: the recall response itself is unchanged, and a failed append must never
cost the caller their recall.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import ego_mcp._server_surface_memory as mem_mod
from ego_mcp.config import EgoConfig
from ego_mcp.derived.co_retrieval_log import (
    _reset_counter_for_tests,
    co_retrieval_path,
)
from ego_mcp.memory import MemoryStore
from ego_mcp.types import Memory, MemorySearchResult


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


@pytest.fixture(autouse=True)
def _quiet_surroundings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the notion and relationship stores the recall handler reaches for."""
    _reset_counter_for_tests()
    notion_store = MagicMock()
    notion_store.search_related.return_value = []
    notion_store.get_associated.return_value = []
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: notion_store)

    relationship_store = MagicMock()
    relationship_store.get.return_value = None
    relationship_store.resolve_person.side_effect = lambda pid: pid
    monkeypatch.setattr(
        mem_mod, "_relationship_store", lambda _config: relationship_store
    )


def _result(memory_id: str, *, is_proust: bool = False) -> MemorySearchResult:
    result = MemorySearchResult(
        memory=Memory(
            id=memory_id,
            content=f"content of {memory_id}",
            timestamp="2026-09-17T09:00:00+00:00",
        ),
        distance=0.2,
        score=0.5,
        decay=0.8,
    )
    result.is_proust = is_proust
    return result


def _memory_store(results: list[MemorySearchResult]) -> MagicMock:
    store = MagicMock()
    store.collection_count.return_value = 20
    store.recall = AsyncMock(return_value=results)
    store.list_recent = AsyncMock(return_value=[])
    store._last_recall_metadata = {"involuntary_person_ids": []}
    return store


async def _recall(
    config: EgoConfig, store: MagicMock, **extra: Any
) -> str:
    return await mem_mod._handle_recall(
        config,
        cast(MemoryStore, store),
        {"context": "the harbour", "n_results": 3, **extra},
    )


def _lines(config: EgoConfig) -> list[dict[str, Any]]:
    path = co_retrieval_path(config.data_dir)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.asyncio
async def test_recall_appends_one_line_with_the_returned_ids(
    config: EgoConfig,
) -> None:
    store = _memory_store([_result("mem_a"), _result("mem_b"), _result("mem_c")])

    await _recall(config, store)

    entries = _lines(config)
    assert len(entries) == 1
    assert entries[0]["ids"] == ["mem_a", "mem_b", "mem_c"]
    assert datetime.fromisoformat(entries[0]["at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_proust_results_are_left_out_of_the_line(config: EgoConfig) -> None:
    store = _memory_store(
        [
            _result("mem_a"),
            _result("mem_b"),
            _result("mem_proust", is_proust=True),
        ]
    )

    await _recall(config, store)

    assert _lines(config)[0]["ids"] == ["mem_a", "mem_b"]


@pytest.mark.asyncio
async def test_nothing_is_written_for_fewer_than_two_results(
    config: EgoConfig,
) -> None:
    store = _memory_store([_result("mem_a")])

    await _recall(config, store)

    assert _lines(config) == []


@pytest.mark.asyncio
async def test_nothing_is_written_when_only_one_result_is_not_proust(
    config: EgoConfig,
) -> None:
    store = _memory_store([_result("mem_a"), _result("mem_p", is_proust=True)])

    await _recall(config, store)

    assert _lines(config) == []


@pytest.mark.asyncio
async def test_nothing_is_written_when_recall_finds_nothing(
    config: EgoConfig,
) -> None:
    store = _memory_store([])

    text = await _recall(config, store)

    assert "No related memories found." in text
    assert _lines(config) == []


@pytest.mark.asyncio
async def test_explicit_filters_are_still_recorded(config: EgoConfig) -> None:
    store = _memory_store([_result("mem_a"), _result("mem_b")])

    await _recall(config, store, category_filter="introspection", date_from="2026-01-01")

    assert _lines(config)[0]["ids"] == ["mem_a", "mem_b"]


@pytest.mark.asyncio
async def test_each_recall_adds_its_own_line(config: EgoConfig) -> None:
    store = _memory_store([_result("mem_a"), _result("mem_b")])

    await _recall(config, store)
    await _recall(config, store)

    assert len(_lines(config)) == 2


@pytest.mark.asyncio
async def test_append_failure_does_not_break_recall(
    config: EgoConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the derived directory is read-only")

    monkeypatch.setattr(mem_mod, "append_co_retrieval", _boom)
    store = _memory_store([_result("mem_a"), _result("mem_b")])

    text = await _recall(config, store)

    assert "memories (showing top matches)" in text


@pytest.mark.asyncio
async def test_recall_response_gains_no_co_retrieval_text(
    config: EgoConfig,
) -> None:
    store = _memory_store([_result("mem_a"), _result("mem_b")])

    text = await _recall(config, store)

    assert "surfacing together" not in text
    assert "co_retrieval" not in text
