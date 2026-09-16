"""Co-retrieval wiring in the consolidate handler (P1 D3 / S3).

The batch counts the pairs; consolidate strengthens the ones already linked and
offers the unlinked ones. Whether to connect them stays with the persona, so the
closing line must keep saying that leaving them apart is fine.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import ego_mcp._server_backend_handlers as backend_handlers_mod
from ego_mcp import timezone_utils
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationStats, MergeCandidate
from ego_mcp.derived.contract import DerivedFile, DerivedReader, write_lens_file
from ego_mcp.memory import MemoryStore
from ego_mcp.types import LinkType, Memory, MemoryLink

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


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
def _isolate_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence the parts of consolidate that are not under test here."""

    def _no_notion_store() -> Any:
        raise RuntimeError("notion store not configured")

    monkeypatch.setattr(backend_handlers_mod, "get_notion_store", _no_notion_store)

    async def _no_ripening(*_args: Any, **_kwargs: Any) -> Any:
        return type("Stats", (), {"fed_questions": 0, "deposits": 0})()

    monkeypatch.setattr(
        backend_handlers_mod, "feed_ripening_questions", _no_ripening
    )
    monkeypatch.setattr(timezone_utils, "now", lambda: NOW)
    reset_tool_metadata()


class _FakeConsolidation:
    """Stand-in for ConsolidationEngine with a fixed result."""

    def __init__(self, merge_candidates: tuple[MergeCandidate, ...] = ()) -> None:
        self._stats = ConsolidationStats(
            replay_events=0,
            coactivation_updates=0,
            link_updates=0,
            refreshed_memories=0,
            merge_candidates=merge_candidates,
        )

    async def run(self, _store: Any) -> ConsolidationStats:
        return self._stats


def _memory(memory_id: str, content: str, *, links: list[str] | None = None) -> Memory:
    return Memory(
        id=memory_id,
        content=content,
        timestamp=NOW.isoformat(),
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED)
            for target in (links or [])
        ],
    )


def _linked_memories(pairs: list[tuple[str, str]]) -> dict[str, Memory]:
    """Memories that really hold the links the derived file calls ``linked``."""
    links: dict[str, list[str]] = {}
    for first, second in pairs:
        links.setdefault(first, []).append(second)
        links.setdefault(second, []).append(first)
    return {
        memory_id: _memory(memory_id, f"content of {memory_id}", links=targets)
        for memory_id, targets in links.items()
    }


def _fake_memory_store(
    memories: dict[str, Memory], *, bumped: set[tuple[str, str]] | None = None
) -> MagicMock:
    store = MagicMock()
    store.data_dir = None  # skips the person backfill scan
    store.get_by_id = AsyncMock(side_effect=lambda mid: memories.get(mid))

    async def _bump(source_id: str, target_id: str, delta: float = 0.1) -> bool:
        if bumped is not None:
            bumped.add((source_id, target_id))
        return source_id in memories and target_id in memories

    store.bump_link_confidence = AsyncMock(side_effect=_bump)
    return store


def _write_items(data_dir: Path, items: list[dict[str, Any]]) -> None:
    write_lens_file(
        data_dir,
        DerivedFile(
            lens="coretrieval",
            generated_at=NOW.isoformat(),
            valid_until=(NOW + timedelta(hours=48)).isoformat(),
            source={"memory_count": 4, "notion_count": 0, "embedding_count": 4},
            items=items,
        ),
    )


def _unlinked(a: str, b: str, weight: float = 3.0) -> dict[str, Any]:
    return {
        "key": f"coretrieval:{a}:{b}",
        "memory_ids": [a, b],
        "weight": weight,
        "distance": 0.4,
        "kind": "unlinked",
    }


def _linked(a: str, b: str, weight: float = 3.0) -> dict[str, Any]:
    return {**_unlinked(a, b, weight), "kind": "linked"}


async def _run(
    config: EgoConfig,
    store: MagicMock,
    merge_candidates: tuple[MergeCandidate, ...] = (),
) -> str:
    return await backend_handlers_mod._handle_consolidate(
        cast(MemoryStore, store),
        cast(Any, _FakeConsolidation(merge_candidates)),
        config,
    )


# --- presenting unlinked pairs ----------------------------------------------


@pytest.mark.asyncio
async def test_unlinked_pairs_are_presented_verbatim(config: EgoConfig) -> None:
    memories = {
        "mem_a": _memory("mem_a", "the harbour at dusk"),
        "mem_b": _memory("mem_b", "the smell of diesel"),
    }
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_b")])

    text = await _run(config, _fake_memory_store(memories))

    assert "Some memories keep surfacing together, unlinked:" in text
    assert '- [mem_a] "the harbour at dusk" <-> [mem_b] "the smell of diesel"' in text
    assert (
        "If they belong together, link_memories can say how."
        " If not, leaving them apart is fine." in text
    )


@pytest.mark.asyncio
async def test_presented_snippets_are_truncated_to_sixty_characters(
    config: EgoConfig,
) -> None:
    long_content = "x" * 200
    memories = {
        "mem_a": _memory("mem_a", long_content),
        "mem_b": _memory("mem_b", "short"),
    }
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_b")])

    text = await _run(config, _fake_memory_store(memories))

    assert f'- [mem_a] "{"x" * 57}..." <-> [mem_b] "short"' in text


@pytest.mark.asyncio
async def test_at_most_three_unlinked_pairs_are_presented(config: EgoConfig) -> None:
    memories = {f"mem_{i}": _memory(f"mem_{i}", f"content {i}") for i in range(8)}
    _write_items(
        config.data_dir,
        [_unlinked(f"mem_{i}", f"mem_{i + 1}") for i in range(0, 8, 2)],
    )

    text = await _run(config, _fake_memory_store(memories))

    assert text.count(" <-> ") == 3


@pytest.mark.asyncio
async def test_block_sits_before_the_merge_candidates_block(
    config: EgoConfig,
) -> None:
    memories = {
        "mem_a": _memory("mem_a", "the harbour at dusk"),
        "mem_b": _memory("mem_b", "the smell of diesel"),
    }
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_b")])
    candidates = (
        MergeCandidate(
            memory_a_id="mem_c",
            memory_b_id="mem_d",
            distance=0.05,
            snippet_a="A snippet",
            snippet_b="B snippet",
        ),
    )

    text = await _run(config, _fake_memory_store(memories), candidates)

    assert text.index("Some memories keep surfacing together, unlinked:") < text.index(
        "Found 1 near-duplicate pair(s):"
    )


@pytest.mark.asyncio
async def test_block_is_emitted_without_any_merge_candidates(
    config: EgoConfig,
) -> None:
    memories = {
        "mem_a": _memory("mem_a", "the harbour at dusk"),
        "mem_b": _memory("mem_b", "the smell of diesel"),
    }
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_b")])

    text = await _run(config, _fake_memory_store(memories))

    assert "near-duplicate" not in text
    assert "Some memories keep surfacing together, unlinked:" in text


@pytest.mark.asyncio
async def test_pair_with_a_deleted_memory_is_skipped_but_still_marked(
    config: EgoConfig,
) -> None:
    memories = {"mem_a": _memory("mem_a", "the harbour at dusk")}
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_gone")])

    text = await _run(config, _fake_memory_store(memories))

    assert "Some memories keep surfacing together, unlinked:" not in text
    reader = DerivedReader(config.data_dir)
    assert reader.is_surfaced("coretrieval:mem_a:mem_gone")


@pytest.mark.asyncio
async def test_presented_pairs_are_not_offered_again(config: EgoConfig) -> None:
    memories = {
        "mem_a": _memory("mem_a", "the harbour at dusk"),
        "mem_b": _memory("mem_b", "the smell of diesel"),
    }
    _write_items(config.data_dir, [_unlinked("mem_a", "mem_b")])
    store = _fake_memory_store(memories)

    first = await _run(config, store)
    second = await _run(config, store)

    assert "Some memories keep surfacing together, unlinked:" in first
    assert "Some memories keep surfacing together, unlinked:" not in second


# --- bumping linked pairs ---------------------------------------------------


@pytest.mark.asyncio
async def test_linked_pairs_are_bumped_and_marked(config: EgoConfig) -> None:
    memories = _linked_memories([("mem_a", "mem_b")])
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])
    bumped: set[tuple[str, str]] = set()

    text = await _run(config, _fake_memory_store(memories, bumped=bumped))

    assert bumped == {("mem_a", "mem_b")}
    assert "Some memories keep surfacing together, unlinked:" not in text
    assert DerivedReader(config.data_dir).is_surfaced("coretrieval:mem_a:mem_b")


@pytest.mark.asyncio
async def test_linked_bump_uses_the_replay_delta(config: EgoConfig) -> None:
    memories = _linked_memories([("mem_a", "mem_b")])
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])
    store = _fake_memory_store(memories)

    await _run(config, store)

    assert store.bump_link_confidence.await_args.kwargs["delta"] == 0.1


@pytest.mark.asyncio
async def test_linked_bumps_are_capped(config: EgoConfig) -> None:
    from ego_mcp.derived.co_retrieval import CO_RETRIEVAL_MAX_LINKED

    count = CO_RETRIEVAL_MAX_LINKED + 5
    pairs = [(f"mem_{i}", f"mem_{i + count}") for i in range(count)]
    memories = _linked_memories(pairs)
    _write_items(config.data_dir, [_linked(first, second) for first, second in pairs])
    bumped: set[tuple[str, str]] = set()

    await _run(config, _fake_memory_store(memories, bumped=bumped))

    assert len(bumped) == CO_RETRIEVAL_MAX_LINKED


@pytest.mark.asyncio
async def test_bump_of_a_vanished_link_is_not_counted(config: EgoConfig) -> None:
    memories = {"mem_a": _memory("mem_a", "a")}
    _write_items(config.data_dir, [_linked("mem_a", "mem_gone")])

    await _run(config, _fake_memory_store(memories))

    assert get_tool_metadata()["coretrieval_bumped"] == 0


@pytest.mark.asyncio
async def test_pair_unlinked_since_the_batch_is_not_bumped(
    config: EgoConfig,
) -> None:
    # consolidation.run() prunes links below 0.1 confidence earlier in this
    # same handler, so a pair the batch called "linked" may have none left.
    # bump_link_confidence would re-create it at 0.6.
    memories = {"mem_a": _memory("mem_a", "a"), "mem_b": _memory("mem_b", "b")}
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])
    store = _fake_memory_store(memories)

    await _run(config, store)

    store.bump_link_confidence.assert_not_awaited()
    assert get_tool_metadata()["coretrieval_bumped"] == 0


@pytest.mark.asyncio
async def test_pair_unlinked_since_the_batch_is_not_marked(
    config: EgoConfig,
) -> None:
    # Not marking is deliberate: the next batch reclassifies the pair as
    # unlinked and it can then be offered instead of silently re-linked.
    memories = {"mem_a": _memory("mem_a", "a"), "mem_b": _memory("mem_b", "b")}
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])

    await _run(config, _fake_memory_store(memories))

    assert not DerivedReader(config.data_dir).is_surfaced("coretrieval:mem_a:mem_b")


@pytest.mark.asyncio
async def test_a_one_sided_link_still_counts_as_linked(config: EgoConfig) -> None:
    memories = {
        "mem_a": _memory("mem_a", "a", links=["mem_b"]),
        "mem_b": _memory("mem_b", "b"),
    }
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])
    bumped: set[tuple[str, str]] = set()

    await _run(config, _fake_memory_store(memories, bumped=bumped))

    assert bumped == {("mem_a", "mem_b")}


@pytest.mark.asyncio
async def test_skipped_unlinked_pairs_are_reported(config: EgoConfig) -> None:
    memories = {
        **_linked_memories([("mem_c", "mem_d")]),
        "mem_a": _memory("mem_a", "a"),
        "mem_b": _memory("mem_b", "b"),
    }
    _write_items(
        config.data_dir,
        [_linked("mem_a", "mem_b"), _linked("mem_c", "mem_d")],
    )

    await _run(config, _fake_memory_store(memories))

    metadata = get_tool_metadata()
    assert metadata["coretrieval_skipped_unlinked"] == 1
    assert metadata["coretrieval_bumped"] == 1


@pytest.mark.asyncio
async def test_skipped_unlinked_is_omitted_when_none_were_skipped(
    config: EgoConfig,
) -> None:
    memories = _linked_memories([("mem_a", "mem_b")])
    _write_items(config.data_dir, [_linked("mem_a", "mem_b")])

    await _run(config, _fake_memory_store(memories))

    assert "coretrieval_skipped_unlinked" not in get_tool_metadata()


# --- telemetry and the quiet path -------------------------------------------


@pytest.mark.asyncio
async def test_telemetry_reports_bumped_count_and_presented_keys(
    config: EgoConfig,
) -> None:
    memories = {
        "mem_a": _memory("mem_a", "a"),
        "mem_b": _memory("mem_b", "b"),
        **_linked_memories([("mem_c", "mem_d")]),
    }
    _write_items(
        config.data_dir,
        [_unlinked("mem_a", "mem_b"), _linked("mem_c", "mem_d")],
    )

    await _run(config, _fake_memory_store(memories))

    metadata = get_tool_metadata()
    assert metadata["coretrieval_bumped"] == 1
    assert json.loads(cast(str, metadata["coretrieval_presented"])) == [
        "coretrieval:mem_a:mem_b"
    ]


@pytest.mark.asyncio
async def test_no_derived_file_leaves_the_response_unchanged(
    config: EgoConfig,
) -> None:
    store = _fake_memory_store({})

    text = await _run(config, store)

    assert text.startswith("Consolidation complete.")
    assert "surfacing together" not in text
    metadata = get_tool_metadata()
    assert metadata["coretrieval_bumped"] == 0
    assert "coretrieval_presented" not in metadata
    store.bump_link_confidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_derived_file_is_ignored(config: EgoConfig) -> None:
    write_lens_file(
        config.data_dir,
        DerivedFile(
            lens="coretrieval",
            generated_at=(NOW - timedelta(hours=72)).isoformat(),
            valid_until=(NOW - timedelta(hours=24)).isoformat(),
            source={"memory_count": 2, "notion_count": 0, "embedding_count": 2},
            items=[_unlinked("mem_a", "mem_b")],
        ),
    )
    memories = {"mem_a": _memory("mem_a", "a"), "mem_b": _memory("mem_b", "b")}

    text = await _run(config, _fake_memory_store(memories))

    assert "surfacing together" not in text


@pytest.mark.asyncio
async def test_malformed_items_are_skipped(config: EgoConfig) -> None:
    _write_items(
        config.data_dir,
        [
            {"key": "coretrieval:bad", "memory_ids": ["only_one"], "kind": "unlinked"},
            {"key": "coretrieval:worse", "memory_ids": "nope", "kind": "linked"},
        ],
    )
    store = _fake_memory_store({})

    text = await _run(config, store)

    assert "surfacing together" not in text
    store.bump_link_confidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_reader_failure_does_not_break_consolidate(
    config: EgoConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_config: EgoConfig) -> DerivedReader:
        raise RuntimeError("derived directory is on fire")

    monkeypatch.setattr(backend_handlers_mod, "_derived_reader", _boom)

    text = await _run(config, _fake_memory_store({}))

    assert text.startswith("Consolidation complete.")
