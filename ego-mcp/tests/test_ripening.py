"""Tests for question ripening lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

import ego_mcp._server_backend_handlers as backend_mod
import ego_mcp._server_surface_attune as attune_mod
import ego_mcp._server_surface_core as core_mod
from ego_mcp import timezone_utils
from ego_mcp._server_backend_handlers import _handle_update_self
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_attune import _handle_attune
from ego_mcp._server_surface_core import (
    _handle_consider_them,
    _handle_introspect,
    _handle_wake_up,
)
from ego_mcp._server_surface_memory import _handle_remember
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationStats
from ego_mcp.desire import DesireEngine
from ego_mcp.notion import NotionStore
from ego_mcp.relationship import RelationshipStore
from ego_mcp.ripening import (
    build_ripened_question_block,
    feed_ripening_questions,
    pick_ripened_question,
)
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Emotion, EmotionalTrace, Memory, MemorySearchResult, Notion


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
def _surface_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_relationship_snapshot(
        _config: object, _memory: object, _person: str
    ) -> str:
        return "relationship snapshot"

    async def fake_derive(
        *_args: Any, **_kwargs: Any
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(core_mod, "_relationship_snapshot_override", fake_relationship_snapshot)
    monkeypatch.setattr(core_mod, "_derive_desire_modulation_override", fake_derive)
    monkeypatch.setattr(attune_mod, "_derive_desire_modulation_override", fake_derive)
    monkeypatch.setattr(core_mod, "get_notion_store", lambda: NotionStore(Path("/tmp/no-notions.json")))
    monkeypatch.setattr(attune_mod, "get_notion_store", lambda: MagicMock(list_all=lambda: []))


class FakeMemoryStore:
    def __init__(
        self,
        *,
        by_query: dict[str, list[MemorySearchResult]] | None = None,
        by_id: dict[str, Memory] | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.by_query = by_query or {}
        self.by_id = by_id or {}
        self.data_dir = data_dir or Path("/tmp")
        self.search_calls: list[tuple[str, int]] = []

    async def search(
        self,
        query: str,
        n_results: int = 5,
        **_kwargs: Any,
    ) -> list[MemorySearchResult]:
        self.search_calls.append((query, n_results))
        return list(self.by_query.get(query, []))

    async def get_by_id(self, memory_id: str) -> Memory | None:
        return self.by_id.get(memory_id)

    async def list_recent(
        self,
        n: int = 30,
        category_filter: str | None = None,
    ) -> list[Memory]:
        del n, category_filter
        return []

    def list_anticipations(self, include_surfaced: bool = False) -> list[Memory]:
        del include_surfaced
        return []

    def mark_anticipation_surfaced(self, memory_id: str) -> None:
        del memory_id


class FakeDesire:
    _state: dict[str, Any] = {}

    @property
    def ema_levels(self) -> dict[str, float]:
        return {}

    def expire_emergent_desires(self) -> list[str]:
        return []

    def compute_levels_with_modulation(self, **_kwargs: Any) -> dict[str, float]:
        return {"cognitive_coherence": 0.7}

    def emergent_directions(self) -> dict[str, str]:
        return {}


def _memory(
    memory_id: str,
    *,
    content: str | None = None,
    tags: Sequence[str] = (),
    valence: float = 0.0,
    timestamp: str = "2026-06-01T12:00:00+00:00",
    private: bool = False,
) -> Memory:
    return Memory(
        id=memory_id,
        content=content or f"memory {memory_id}",
        timestamp=timestamp,
        tags=list(tags),
        emotional_trace=EmotionalTrace(primary=Emotion.CALM, valence=valence),
        is_private=private,
    )


def _result(memory: Memory, distance: float) -> MemorySearchResult:
    return MemorySearchResult(memory=memory, distance=distance, score=distance)


def _age_question(
    store: SelfModelStore,
    question_id: str,
    now: datetime,
    days: float,
    *,
    last_fed_at: str = "",
    companions: list[dict[str, Any]] | None = None,
) -> None:
    store.update_question_fields(
        question_id,
        {
            "created_at": (now - timedelta(days=days)).isoformat(),
            "last_fed_at": last_fed_at,
            "companions": companions or [],
        },
    )


@pytest.mark.asyncio
async def test_feed_gates_targets_and_updates_last_fed_at(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    q_importance_one = store.add_question("importance one", importance=1)
    q_active = store.add_question("active question", importance=2)
    q_fading = store.add_question("fading question", importance=2)
    _age_question(store, q_importance_one, now, 5)
    _age_question(store, q_active, now, 0)
    _age_question(store, q_fading, now, 10)
    companion = _memory("m-companion")
    memory = FakeMemoryStore(
        by_query={"fading question": [_result(companion, 0.5)]},
        by_id={companion.id: companion},
    )

    stats = await feed_ripening_questions(store, memory, now=now)
    entries = {entry["id"]: entry for entry in store.get_question_log()}

    assert stats.fed_questions == 1
    assert stats.deposits == 1
    assert memory.search_calls == [("fading question", 15)]
    assert entries[q_importance_one]["last_fed_at"] == ""
    assert entries[q_active]["last_fed_at"] == ""
    assert entries[q_fading]["last_fed_at"] == now.isoformat()


@pytest.mark.asyncio
async def test_feed_rotation_limit_boundary_and_duplicate_filter(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    question_ids: list[str] = []
    for index in range(6):
        qid = store.add_question(f"q{index}", importance=2)
        last_fed = "" if index == 0 else f"2026-07-01T0{index}:00:00+00:00"
        _age_question(store, qid, now, 10, last_fed_at=last_fed)
        question_ids.append(qid)
    existing = {"memory_id": "m_existing", "distance": 0.4, "added_at": "old", "kind": "companion"}
    store.update_question_fields(question_ids[0], {"companions": [existing]})
    results = [
        _result(_memory("m_existing"), 0.35),
        _result(_memory("m_low"), 0.349),
        _result(_memory("m_min"), 0.35),
        _result(_memory("m_max"), 0.65),
        _result(_memory("m_high"), 0.651),
    ]
    memory = FakeMemoryStore(by_query={"q0": results})

    stats = await feed_ripening_questions(store, memory, now=now)
    q0 = next(entry for entry in store.get_question_log() if entry["id"] == question_ids[0])
    deposited_ids = [
        companion.get("memory_id")
        for companion in q0["companions"]
        if companion.get("kind") == "companion"
    ]

    assert stats.fed_questions == 5
    assert [query for query, _n in memory.search_calls] == ["q0", "q1", "q2", "q3", "q4"]
    assert deposited_ids == ["m_existing", "m_min", "m_max"]
    assert q0["companions"][1]["distance"] == 0.35
    assert q0["companions"][2]["distance"] == 0.65
    q5 = next(entry for entry in store.get_question_log() if entry["id"] == question_ids[5])
    assert q5["last_fed_at"] == "2026-07-01T05:00:00+00:00"


@pytest.mark.asyncio
async def test_feed_no_candidates_only_rotates_last_fed_at(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("no candidates", importance=2)
    _age_question(store, qid, now, 10)
    memory = FakeMemoryStore(
        by_query={
            "no candidates": [
                _result(_memory("too-close"), 0.2),
                _result(_memory("too-far"), 0.8),
            ]
        }
    )

    stats = await feed_ripening_questions(store, memory, now=now)
    entry = store.get_question_log()[0]

    assert stats.deposits == 0
    assert entry["companions"] == []
    assert entry["last_fed_at"] == now.isoformat()


@pytest.mark.asyncio
async def test_feed_records_memory_tension_and_prefers_it_over_notion_tension(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("tension question", importance=2)
    _age_question(store, qid, now, 10)
    left = _memory("m-left", tags=("shared", "topic"), valence=0.3)
    right = _memory("m-right", tags=("shared", "topic"), valence=-0.3)
    notion_store = NotionStore(config.data_dir / "notions.json")
    notion_store.save(Notion(id="n-left", label="left notion", tags=["x", "y"], valence=0.5))
    notion_store.save(Notion(id="n-right", label="right notion", tags=["x", "y"], valence=-0.5))
    memory = FakeMemoryStore(
        by_query={"tension question": [_result(left, 0.2), _result(right, 0.3)]}
    )

    await feed_ripening_questions(store, memory, notion_store, now=now)
    companions = store.get_question_log()[0]["companions"]

    assert len(companions) == 1
    assert companions[0]["kind"] == "tension"
    assert companions[0]["memory_id"] == "m-left"
    assert companions[0]["paired_memory_id"] == "m-right"


@pytest.mark.asyncio
async def test_feed_records_notion_tension_when_no_memory_pair(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("notion tension question", importance=2)
    _age_question(store, qid, now, 10)
    near = _memory("near", tags=("near",))
    notion_store = NotionStore(config.data_dir / "notions.json")
    notion_store.save(Notion(id="n-left", label="left notion", tags=["near", "shared"], valence=0.5))
    notion_store.save(Notion(id="n-right", label="right notion", tags=["near", "shared"], valence=-0.5))
    memory = FakeMemoryStore(by_query={"notion tension question": [_result(near, 0.2)]})

    await feed_ripening_questions(store, memory, notion_store, now=now)
    companion = store.get_question_log()[0]["companions"][0]

    assert companion == {
        "notion_id": "n-left",
        "paired_notion_id": "n-right",
        "added_at": now.isoformat(),
        "kind": "tension_notion",
    }


@pytest.mark.asyncio
async def test_consolidate_feeds_questions_and_reports_verbatim_line(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_tool_metadata()
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("consolidate question", importance=2)
    _age_question(store, qid, now, 10)
    companion = _memory("m1")
    memory = FakeMemoryStore(
        by_query={"consolidate question": [_result(companion, 0.5)]},
        by_id={companion.id: companion},
        data_dir=config.data_dir,
    )
    monkeypatch.setattr(backend_mod, "get_notion_store", lambda: NotionStore(config.data_dir / "notions.json"))

    class FakeConsolidation:
        async def run(self, _memory: object) -> ConsolidationStats:
            return ConsolidationStats(
                replay_events=0,
                coactivation_updates=0,
                link_updates=0,
                refreshed_memories=0,
            )

    result = await backend_mod._handle_consolidate(
        cast(Any, memory),
        cast(Any, FakeConsolidation()),
        config,
    )

    assert "A few resting questions gathered company." in result
    assert "consolidate question" not in result
    assert get_tool_metadata()["ripening_fed_questions"] == 1
    assert get_tool_metadata()["ripening_deposits"] == 1


@pytest.mark.asyncio
async def test_pick_and_build_resurfacing_block_clears_once_and_keeps_lineage(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_tool_metadata()
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    relationship = RelationshipStore(config.data_dir / "relationships" / "models.json")
    relationship.update("alice", {"name": "Alice"})
    qid = store.add_question(
        "What should return?",
        importance=2,
        person_id="alice",
        lineage=["q_root"],
    )
    companions: list[dict[str, Any]] = [
        {"memory_id": "m1", "distance": 0.4, "added_at": "2026-07-01T10:00:00+00:00", "kind": "companion"},
        {"memory_id": "m2", "distance": 0.5, "added_at": "2026-07-01T11:00:00+00:00", "kind": "companion"},
        {"memory_id": "m3", "distance": 0.6, "added_at": "2026-07-01T12:00:00+00:00", "kind": "companion"},
    ]
    _age_question(store, qid, now, 10, last_fed_at="2026-07-01T12:00:00+00:00", companions=companions)
    memories = {
        "m1": _memory("m1", content="private companion text", private=True),
        "m2": _memory("m2", content="second companion text"),
        "m3": _memory("m3", content="third companion text"),
    }
    memory = FakeMemoryStore(by_id=memories)

    picked = pick_ripened_question(store.get_question_log())
    block = await build_ripened_question_block(
        store,
        memory,
        picked or {},
        relationship_store=relationship,
        now=now,
    )

    assert picked is not None
    assert block is not None
    assert "A question you'd set aside has gathered strange companions:" in block
    assert f'"[{qid}] What should return?"' in block
    assert 'update_self(field="new_question", value={"question": ..., "supersedes": "' in block
    assert "This one is held with Alice — it may be wanting to go back to them." in block
    assert "private companion text" in block
    reloaded = SelfModelStore(config.data_dir / "self_model.json").get_question_log()[0]
    assert reloaded["companions"] == []
    assert reloaded["lineage"] == ["q_root"]
    assert reloaded["person_id"] == "alice"
    assert get_tool_metadata() == {"ripening_resurfaced": qid}
    assert "private companion text" not in str(get_tool_metadata())


@pytest.mark.asyncio
async def test_deleted_deposits_clear_without_presentation(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_tool_metadata()
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("missing deposits", importance=2)
    companions: list[dict[str, Any]] = [
        {"memory_id": "gone1", "distance": 0.4, "added_at": "a", "kind": "companion"},
        {"memory_id": "gone2", "distance": 0.4, "added_at": "b", "kind": "companion"},
        {"notion_id": "n1", "paired_notion_id": "n2", "added_at": "c", "kind": "tension_notion"},
    ]
    _age_question(store, qid, now, 10, companions=companions)

    block = await build_ripened_question_block(
        store,
        FakeMemoryStore(),
        store.get_question_log()[0],
        notion_store=NotionStore(config.data_dir / "notions.json"),
        now=now,
    )

    assert block is None
    assert SelfModelStore(config.data_dir / "self_model.json").get_question_log()[0]["companions"] == []
    assert get_tool_metadata() == {}


@pytest.mark.asyncio
async def test_wake_up_ripening_occupies_open_edges_and_introspect_then_falls_back(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    active_id = store.add_question("Active top should wait", importance=5)
    ripened_id = store.add_question("Ripened edge", importance=2)
    _age_question(store, active_id, now, 0)
    companions = [
        {"memory_id": "m1", "distance": 0.4, "added_at": "a", "kind": "companion"},
        {"memory_id": "m2", "distance": 0.5, "added_at": "b", "kind": "companion"},
        {"memory_id": "m3", "distance": 0.6, "added_at": "c", "kind": "companion"},
    ]
    _age_question(store, ripened_id, now, 10, companions=companions)
    memory = FakeMemoryStore(
        by_id={
            "m1": _memory("m1", content="first companion"),
            "m2": _memory("m2", content="second companion"),
            "m3": _memory("m3", content="third companion"),
        }
    )

    first = await _handle_wake_up(config, cast(Any, memory), cast(Any, FakeDesire()))
    second = await _handle_introspect(config, cast(Any, memory), cast(Any, FakeDesire()))

    assert "Open edges:\nA question you'd set aside has gathered strange companions:" in first
    assert "Ripened edge" in first
    assert "Active top should wait" not in first
    assert "A question you'd set aside has gathered strange companions:" not in second
    assert f"[{active_id}] Active top should wait" in second


@pytest.mark.asyncio
async def test_introspect_ripening_replaces_resurfacing_but_second_path_remains(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    store = SelfModelStore(config.data_dir / "self_model.json")
    qid = store.add_question("Ripened introspect edge", importance=2)
    _age_question(
        store,
        qid,
        now,
        10,
        companions=[
            {"memory_id": "m1", "distance": 0.4, "added_at": "a", "kind": "companion"},
            {"memory_id": "m2", "distance": 0.5, "added_at": "b", "kind": "companion"},
            {"memory_id": "m3", "distance": 0.6, "added_at": "c", "kind": "companion"},
        ],
    )
    memory = FakeMemoryStore(
        by_id={
            "m1": _memory("m1"),
            "m2": _memory("m2"),
            "m3": _memory("m3"),
        }
    )

    ripened = await _handle_introspect(config, cast(Any, memory), cast(Any, FakeDesire()))
    assert "A question you'd set aside has gathered strange companions:" in ripened
    assert "Resurfacing (you'd almost forgotten):" not in ripened

    reloaded_store = SelfModelStore(config.data_dir / "self_model.json")
    q2 = reloaded_store.add_question("Ordinary forgotten edge", importance=2)
    _age_question(reloaded_store, q2, now, 10)
    triggered = await _handle_introspect(config, cast(Any, memory), cast(Any, FakeDesire()))
    assert "Resurfacing (you'd almost forgotten):" in triggered
    assert f"[{q2}] Ordinary forgotten edge" in triggered


@pytest.mark.asyncio
async def test_new_question_with_and_supersedes_lifecycle(
    config: EgoConfig,
) -> None:
    relationships = RelationshipStore(config.data_dir / "relationships" / "models.json")
    relationships.update("alice", {"name": "Alice", "aliases": ["Al"]})
    store = SelfModelStore(config.data_dir / "self_model.json")
    old_id = store.add_question(
        "Old wording",
        importance=3,
        person_id="alice",
        lineage=["q_root"],
    )
    store.update_question_fields(
        old_id,
        {"companions": [{"memory_id": "m1", "kind": "companion"}]},
    )
    store.resolve_question(old_id)

    result = _handle_update_self(
        config,
        {
            "field": "new_question",
            "value": {
                "question": "New wording",
                "importance": 4,
                "supersedes": old_id,
            },
        },
    )
    unknown = _handle_update_self(
        config,
        {
            "field": "new_question",
            "value": {"question": "Shared raw", "with": "Mystery"},
        },
    )
    aliased = _handle_update_self(
        config,
        {
            "field": "new_question",
            "value": {"question": "Shared alias", "with": "Al"},
        },
    )
    bad_supersedes = _handle_update_self(
        config,
        {
            "field": "new_question",
            "value": {"question": "Fresh despite bad id", "supersedes": "q_missing"},
        },
    )
    entries = SelfModelStore(config.data_dir / "self_model.json").get_question_log()
    new_entry = next(entry for entry in entries if entry["question"] == "New wording")
    unknown_entry = next(entry for entry in entries if entry["question"] == "Shared raw")
    alias_entry = next(entry for entry in entries if entry["question"] == "Shared alias")

    assert f"It carries forward {old_id}." in result
    assert new_entry["lineage"] == ["q_root", old_id]
    assert new_entry["person_id"] == "alice"
    assert new_entry["companions"] == []
    assert unknown_entry["person_id"] == "Mystery"
    assert "Held with Mystery." in unknown
    assert alias_entry["person_id"] == "alice"
    assert "Held with Alice." in aliased
    assert "(supersedes q_missing not found — held as a fresh question.)" in bad_supersedes


@pytest.mark.asyncio
async def test_consider_them_and_introspect_show_person_questions(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    relationships = RelationshipStore(config.data_dir / "relationships" / "models.json")
    relationships.update("alice", {"name": "Alice", "aliases": ["Al"]})
    store = SelfModelStore(config.data_dir / "self_model.json")
    q1 = store.add_question("First shared", importance=5, person_id="alice")
    q2 = store.add_question("Second shared", importance=4, person_id="alice")
    q3 = store.add_question("Third shared", importance=3, person_id="alice")
    _age_question(store, q1, now, 0)
    _age_question(store, q2, now, 0)
    _age_question(store, q3, now, 0)

    async def fake_tendency(
        _memory: object, _person: str
    ) -> tuple[str, str, list[str], list[str]]:
        return "occasional", "neutral", [], []

    monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
    memory = FakeMemoryStore()
    consider = await _handle_consider_them(config, cast(Any, memory), {"person": "Al"})
    introspect = await _handle_introspect(config, cast(Any, memory), cast(Any, FakeDesire()))

    assert "Held together with Alice:\n- " in consider
    assert f"- [{q1}] First shared" in consider
    assert f"- [{q2}] Second shared" in consider
    assert f"- [{q3}] Third shared" not in consider
    assert f"- [{q1}] First shared (importance: 5, with Alice)" in introspect


@pytest.mark.asyncio
async def test_reunion_frames_attach_one_shared_question(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    relationships = RelationshipStore(config.data_dir / "relationships" / "models.json")
    relationships.update("alice", {"name": "Alice"})
    relationships.set_reunion_note("alice", gap_days=14.0, noted_at=now.isoformat())
    qid = SelfModelStore(config.data_dir / "self_model.json").add_question(
        "Shared reunion question",
        importance=5,
        person_id="alice",
    )
    memory = FakeMemoryStore()

    wake = await _handle_wake_up(config, cast(Any, memory), cast(Any, FakeDesire()))
    assert "Reunited with Alice recently" in wake
    assert f'There\'s something you two left open: "[{qid}] Shared reunion question"' in wake

    relationships.add_interaction("alice", "2026-06-01T12:00:00+00:00", "calm")
    saved = _memory("saved", content="returning shared moment", timestamp=now.isoformat())

    class SavingMemory(FakeMemoryStore):
        async def save_with_auto_link(self, **_kwargs: Any) -> tuple[Memory, int, list[Any], None]:
            return saved, 0, [], None

        def _ensure_connected(self) -> Any:
            return MagicMock(update=MagicMock())

    remember = await _handle_remember(
        config,
        cast(Any, SavingMemory(by_id={saved.id: saved}, data_dir=config.data_dir)),
        {"content": saved.content, "emotion": "calm", "shared_with": "alice"},
    )

    assert "A shared moment after a while" in remember
    assert f'There\'s something you two left open: "[{qid}] Shared reunion question"' in remember


@pytest.mark.asyncio
async def test_attune_ripening_presence_probability_and_non_disclosure(
    config: EgoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_tool_metadata()
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(timezone_utils, "now", lambda: now)
    qid = SelfModelStore(config.data_dir / "self_model.json").add_question(
        "Hidden ripening question",
        importance=2,
    )
    store = SelfModelStore(config.data_dir / "self_model.json")
    _age_question(
        store,
        qid,
        now,
        10,
        companions=[{"memory_id": "m1", "distance": 0.4, "added_at": "a", "kind": "companion"}],
    )
    monkeypatch.setattr("ego_mcp._server_surface_attune.random.random", lambda: 0.0)
    memory = FakeMemoryStore()

    shown = await _handle_attune(
        config,
        cast(Any, memory),
        {},
        DesireEngine.from_data_dir(config.data_dir),
    )
    assert shown.count("Something is ripening where you're not looking.") == 1
    assert "Hidden ripening question" not in shown
    assert qid not in shown
    assert get_tool_metadata()["ripening_presence_shown"] is True

    reset_tool_metadata()
    monkeypatch.setattr("ego_mcp._server_surface_attune.random.random", lambda: 0.99)
    hidden = await _handle_attune(
        config,
        cast(Any, memory),
        {},
        DesireEngine.from_data_dir(config.data_dir),
    )
    assert "Something is ripening where you're not looking." not in hidden
    assert "ripening_presence_shown" not in get_tool_metadata()
