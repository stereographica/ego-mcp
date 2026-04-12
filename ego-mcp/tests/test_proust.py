"""Tests for Proust involuntary recall at wake_up."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from ego_mcp.proust import find_proust_memory
from ego_mcp.types import Emotion, EmotionalTrace, Memory, MemorySearchResult


def _old_memory(
    *,
    days_ago: int = 45,
    access_count: int = 1,
    content: str = "a distant afternoon",
    memory_id: str = "m-old-1",
) -> Memory:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return Memory(
        id=memory_id,
        content=content,
        timestamp=ts,
        emotional_trace=EmotionalTrace(primary=Emotion.NOSTALGIC, intensity=0.6),
        access_count=access_count,
    )


def _recent_memory(*, days_ago: int = 5) -> Memory:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return Memory(
        id="m-recent",
        content="recent event",
        timestamp=ts,
        access_count=0,
    )


def _search_result(mem: Memory, distance: float = 0.3) -> MemorySearchResult:
    return MemorySearchResult(memory=mem, distance=distance)


class TestFindProustMemory:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_candidates(self) -> None:
        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        result = await find_proust_memory(
            seed_query="the morning light",
            memory_store=store,
            random_source=random.Random(42),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_old_low_access_memory(self) -> None:
        old = _old_memory(days_ago=45, access_count=1)
        store = AsyncMock()
        store.search = AsyncMock(return_value=[_search_result(old)])
        # probability=1.0 to guarantee selection
        result = await find_proust_memory(
            seed_query="something nostalgic",
            memory_store=store,
            probability=1.0,
            random_source=random.Random(42),
        )
        assert result is not None
        assert result.id == "m-old-1"

    @pytest.mark.asyncio
    async def test_date_to_excludes_recent_memories(self) -> None:
        """The store is called with date_to ~30 days ago, so recent memories
        never appear in results.  We verify the filter parameter here."""
        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        await find_proust_memory(
            seed_query="anything",
            memory_store=store,
            probability=1.0,
            random_source=random.Random(42),
        )
        call_kwargs = store.search.call_args.kwargs
        date_to_str = call_kwargs["date_to"]
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # date_to should be approximately 30 days before now
        diff = (now - date_to).days
        assert 29 <= diff <= 31

    @pytest.mark.asyncio
    async def test_filters_out_high_access_count(self) -> None:
        old = _old_memory(days_ago=60, access_count=5)
        store = AsyncMock()
        store.search = AsyncMock(return_value=[_search_result(old)])
        result = await find_proust_memory(
            seed_query="anything",
            memory_store=store,
            probability=1.0,
            random_source=random.Random(42),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_probability_zero_never_returns(self) -> None:
        old = _old_memory()
        store = AsyncMock()
        store.search = AsyncMock(return_value=[_search_result(old)])
        result = await find_proust_memory(
            seed_query="anything",
            memory_store=store,
            probability=0.0,
            random_source=random.Random(42),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_probability_controls_selection(self) -> None:
        old = _old_memory()
        store = AsyncMock()
        store.search = AsyncMock(return_value=[_search_result(old)])
        # Use a fixed seed; test both outcomes
        rng = random.Random(0)
        # With probability=0.25, the first random() from seed 0 is ~0.844
        # which is > 0.25, so it should return None
        result = await find_proust_memory(
            seed_query="anything",
            memory_store=store,
            probability=0.25,
            random_source=rng,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_picks_closest_semantic_match(self) -> None:
        old_close = _old_memory(memory_id="m-close", content="close match")
        old_far = _old_memory(memory_id="m-far", content="far match")
        store = AsyncMock()
        store.search = AsyncMock(
            return_value=[
                _search_result(old_far, distance=0.7),
                _search_result(old_close, distance=0.2),
            ]
        )
        result = await find_proust_memory(
            seed_query="anything",
            memory_store=store,
            probability=1.0,
            random_source=random.Random(42),
        )
        assert result is not None
        assert result.id == "m-close"

    @pytest.mark.asyncio
    async def test_search_uses_date_to_filter(self) -> None:
        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        await find_proust_memory(
            seed_query="test",
            memory_store=store,
            probability=1.0,
        )
        call_kwargs = store.search.call_args.kwargs
        assert "date_to" in call_kwargs
        # date_to should be roughly 30 days ago
        date_to = call_kwargs["date_to"]
        assert date_to is not None
