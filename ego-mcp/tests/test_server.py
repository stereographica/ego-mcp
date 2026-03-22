"""Focused tests for server-side tool dispatch behavior."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mcp.types import TextContent

import ego_mcp._server_surface_core as core_surface_mod
import ego_mcp._server_surface_memory as memory_surface_mod
import ego_mcp.server as server_mod
from ego_mcp._server_runtime import (
    get_tool_metadata,
    reset_tool_metadata,
    update_tool_metadata,
)
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationStats, MergeCandidate
from ego_mcp.desire import DesireEngine
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import MemoryStore
from ego_mcp.types import (
    Category,
    Emotion,
    EmotionalTrace,
    Memory,
    MemorySearchResult,
    Notion,
)


def _seed_high_desire(desire: DesireEngine, name: str) -> float:
    desire._state[name]["last_satisfied"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()
    return float(desire.compute_levels()[name])


@pytest.fixture
def desire(tmp_path: Path) -> DesireEngine:
    return DesireEngine(tmp_path / "desires.json")


@pytest.fixture(autouse=True)
def bind_minimal_server_state(
    monkeypatch: pytest.MonkeyPatch, desire: DesireEngine
) -> Iterator[None]:
    reset_tool_metadata()
    monkeypatch.setattr(server_mod, "_config", SimpleNamespace(companion_name="Master"))
    monkeypatch.setattr(server_mod, "_memory", object())
    monkeypatch.setattr(server_mod, "_desire", desire)
    monkeypatch.setattr(server_mod, "_episodes", object())
    monkeypatch.setattr(server_mod, "_consolidation", object())
    monkeypatch.setattr(server_mod, "_tool_log_context", lambda: {})
    yield
    reset_tool_metadata()


class TestImplicitSatisfactionFromServer:
    @pytest.mark.asyncio
    async def test_remember_lowers_expression_after_tool_call(
        self,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        before = _seed_high_desire(desire, "expression")

        async def fake_handle_remember(
            _config: object, _memory: object, _args: dict[str, object]
        ) -> str:
            return "saved"

        monkeypatch.setattr(server_mod, "_handle_remember", fake_handle_remember)

        result = await server_mod.call_tool(
            "remember",
            {"content": "note", "category": "daily"},
        )

        after = desire.compute_levels()["expression"]
        assert isinstance(result[0], TextContent)
        assert result[0].text == "saved"
        assert after < before

    @pytest.mark.asyncio
    async def test_consider_them_lowers_social_thirst_after_tool_call(
        self,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        before = _seed_high_desire(desire, "social_thirst")

        async def fake_handle_consider_them(
            _config: object,
            _memory: object,
            _args: dict[str, object],
        ) -> str:
            return "considered"

        monkeypatch.setattr(server_mod, "_handle_consider_them", fake_handle_consider_them)

        result = await server_mod.call_tool(
            "consider_them",
            {"person": "Master"},
        )

        after = desire.compute_levels()["social_thirst"]
        assert isinstance(result[0], TextContent)
        assert result[0].text == "considered"
        assert after < before

    @pytest.mark.asyncio
    async def test_remember_duplicate_does_not_lower_expression(
        self,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        before = _seed_high_desire(desire, "expression")

        async def fake_handle_remember(
            _config: object, _memory: object, _args: dict[str, object]
        ) -> str:
            return "Not saved — very similar memory already exists."

        monkeypatch.setattr(server_mod, "_handle_remember", fake_handle_remember)

        result = await server_mod.call_tool(
            "remember",
            {"content": "duplicate note", "category": "daily"},
        )

        after = desire.compute_levels()["expression"]
        assert isinstance(result[0], TextContent)
        assert "Not saved" in result[0].text
        assert after == pytest.approx(before)

    @pytest.mark.asyncio
    async def test_handle_recall_includes_related_notions(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            def collection_count(self) -> int:
                return 3

            async def recall(
                self,
                _context: str,
                **_kwargs: object,
            ) -> list[MemorySearchResult]:
                return [
                    MemorySearchResult(
                        memory=Memory(
                            id="mem_1",
                            content="I keep circling the same feeling.",
                            timestamp="2026-02-26T00:00:00+00:00",
                            tags=["safety", "home"],
                            emotional_trace=EmotionalTrace(
                                primary=Emotion.ANXIOUS,
                                intensity=0.7,
                            ),
                        ),
                        distance=0.1,
                        score=0.2,
                        decay=0.8,
                    )
                ]

        class FakeNotionStore:
            def search_by_tags(self, tags: list[str], min_match: int = 1) -> list[Notion]:
                assert tags == ["home", "safety"]
                assert min_match == 1
                return [
                    Notion(
                        id="notion_1",
                        label="home & safety (anxious)",
                        emotion_tone=Emotion.ANXIOUS,
                        confidence=0.9,
                        tags=["home", "safety"],
                    )
                ]

        monkeypatch.setattr(
            memory_surface_mod,
            "get_notion_store",
            lambda: FakeNotionStore(),
        )

        text = await memory_surface_mod._handle_recall(
            cast(Any, SimpleNamespace()),
            cast(Any, FakeMemoryStore()),
            {"context": "home", "n_results": 1},
        )

        assert "--- notions ---" in text
        assert '"home & safety (anxious)" anxious confidence: 0.9' in text

    @pytest.mark.asyncio
    async def test_completion_log_context_emits_snapshot_for_non_feel_desires(
        self, desire: DesireEngine
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 1) -> list[Memory]:
                assert n == 1
                return [
                    Memory(
                        id="mem_1",
                        content="latest",
                        timestamp="2026-02-26T00:00:00+00:00",
                        emotional_trace=EmotionalTrace(
                            primary=Emotion.CURIOUS,
                            intensity=0.8,
                            valence=0.2,
                            arousal=0.7,
                        ),
                    )
                ]

        extra = await server_mod._completion_log_context(
            "remember",
            cast(Any, FakeMemoryStore()),
            cast(Any, SimpleNamespace(companion_name="Master")),
            desire,
        )

        assert extra["emotion_primary"] == "curious"
        assert extra["emotion_intensity"] == 0.8
        assert extra["valence"] == 0.2
        assert extra["arousal"] == 0.7

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name", ["consider_them", "wake_up"])
    async def test_completion_log_context_includes_relationship_metrics_for_social_tools(
        self, tool_name: str, desire: DesireEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 1) -> list[Memory]:
                assert n == 1
                return [
                    Memory(
                        id="mem_1",
                        content="latest",
                        timestamp="2026-02-26T00:00:00+00:00",
                        emotional_trace=EmotionalTrace(
                            primary=Emotion.CURIOUS,
                            intensity=0.8,
                            valence=0.2,
                            arousal=0.7,
                        ),
                    )
                ]

        class FakeRelationshipStore:
            def get(self, person_id: str) -> Any:
                assert person_id == "Master"
                return SimpleNamespace(
                    trust_level=0.82,
                    total_interactions=15,
                    shared_episode_ids=["ep1", "ep2", "ep3"],
                )

        monkeypatch.setattr(
            server_mod, "_relationship_store", lambda _config: FakeRelationshipStore()
        )

        extra = await server_mod._completion_log_context(
            tool_name,
            cast(Any, FakeMemoryStore()),
            cast(Any, SimpleNamespace(companion_name="Master")),
            desire,
        )

        assert extra["trust_level"] == 0.82
        assert extra["total_interactions"] == 15
        assert extra["shared_episodes_count"] == 3

    @pytest.mark.asyncio
    async def test_completion_log_context_skips_relationship_for_other_tools(
        self, desire: DesireEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 1) -> list[Memory]:
                assert n == 1
                return [
                    Memory(
                        id="mem_1",
                        content="latest",
                        timestamp="2026-02-26T00:00:00+00:00",
                        emotional_trace=EmotionalTrace(
                            primary=Emotion.CURIOUS,
                            intensity=0.8,
                            valence=0.2,
                            arousal=0.7,
                        ),
                    )
                ]

        relationship_store_called = False

        def _fake_relationship_store(_config: Any) -> Any:
            nonlocal relationship_store_called
            relationship_store_called = True
            return object()

        monkeypatch.setattr(server_mod, "_relationship_store", _fake_relationship_store)

        extra = await server_mod._completion_log_context(
            "introspect",
            cast(Any, FakeMemoryStore()),
            cast(Any, SimpleNamespace(companion_name="Master")),
            desire,
        )

        assert "trust_level" not in extra
        assert "total_interactions" not in extra
        assert "shared_episodes_count" not in extra
        assert relationship_store_called is False

    @pytest.mark.asyncio
    async def test_completion_log_context_ignores_relationship_errors(
        self, desire: DesireEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 1) -> list[Memory]:
                assert n == 1
                return [
                    Memory(
                        id="mem_1",
                        content="latest",
                        timestamp="2026-02-26T00:00:00+00:00",
                        emotional_trace=EmotionalTrace(
                            primary=Emotion.CURIOUS,
                            intensity=0.8,
                            valence=0.2,
                            arousal=0.7,
                        ),
                    )
                ]

        def _raising_relationship_store(_config: Any) -> Any:
            raise RuntimeError("boom")

        monkeypatch.setattr(server_mod, "_relationship_store", _raising_relationship_store)

        extra = await server_mod._completion_log_context(
            "consider_them",
            cast(Any, FakeMemoryStore()),
            cast(Any, SimpleNamespace(companion_name="Master")),
            desire,
        )

        assert extra["emotion_primary"] == "curious"
        assert extra["emotion_intensity"] == 0.8
        assert extra["valence"] == 0.2
        assert extra["arousal"] == 0.7
        assert "trust_level" not in extra
        assert "total_interactions" not in extra
        assert "shared_episodes_count" not in extra

    @pytest.mark.asyncio
    async def test_completion_log_context_returns_latest_emotion(
        self,
        tmp_path: Path,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeEmbeddingProvider:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                vectors: list[list[float]] = []
                for text in texts:
                    seed = hash(text) % 1000
                    vec = [((seed + i) % 100) / 100.0 for i in range(64)]
                    norm = sum(x * x for x in vec) ** 0.5
                    vectors.append([x / norm for x in vec])
                return vectors

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
        config = EgoConfig.from_env()
        embedding = EgoEmbeddingFunction(cast(EmbeddingProvider, FakeEmbeddingProvider()))
        memory = MemoryStore(config, embedding)
        memory.connect()
        try:
            for index in range(5):
                await memory.save(content=f"older memory {index}", emotion="neutral")
            await memory.save(
                content="latest memory with explicit trace",
                emotion="contentment",
                intensity=0.7,
                valence=0.5,
                arousal=0.2,
            )

            extra = await server_mod._completion_log_context(
                "remember",
                memory,
                config,
                desire,
            )
        finally:
            memory.close()

        assert extra["emotion_primary"] == "contentment"
        assert extra["emotion_intensity"] == 0.7
        assert extra["valence"] == 0.5
        assert extra["arousal"] == 0.2

    @pytest.mark.asyncio
    async def test_handle_feel_desires_records_telemetry_and_blends_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ego_mcp.types import Notion

        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="notion_1",
                        label="safety",
                        emotion_tone=Emotion.ANXIOUS,
                        valence=-0.7,
                        confidence=0.9,
                        tags=["safety", "home"],
                    )
                ]

        class FakeImpulseManager:
            def consume_event(self) -> dict[str, object]:
                return {
                    "impulse_boost_triggered": True,
                    "impulse_source_memory_id": "mem_proust",
                    "impulse_boosted_desire": "curiosity",
                    "impulse_boost_amount": 0.15,
                }

            def consume_boosts(self) -> dict[str, float]:
                return {"curiosity": 0.15}

        class FakeDesire:
            def generate_emergent_desires(self, notions: list[Notion]) -> list[str]:
                assert len(notions) == 1
                return ["You want to feel safe."]

            def expire_emergent_desires(self) -> list[str]:
                return ["old emergent desire"]

            def compute_levels_with_modulation(
                self,
                *,
                context_boosts: dict[str, float] | None = None,
                emotional_modulation: dict[str, float] | None = None,
                prediction_error: dict[str, float] | None = None,
            ) -> dict[str, float]:
                assert context_boosts is not None
                assert emotional_modulation is not None
                assert prediction_error is not None
                return {
                    "curiosity": 0.6,
                    "social_thirst": 0.45,
                    "expression": 0.4,
                    "cognitive_coherence": 0.3,
                }

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())
        monkeypatch.setattr(
            core_surface_mod, "get_impulse_manager", lambda: FakeImpulseManager()
        )
        async def fake_derive_desire_modulation(
            _memory: object,
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        monkeypatch.setattr(server_mod, "_derive_desire_modulation", fake_derive_desire_modulation)
        monkeypatch.setattr(
            server_mod, "get_body_state", lambda: {"time_phase": "morning", "system_load": "low"}
        )

        config = SimpleNamespace(companion_name="Master", data_dir=tmp_path)
        text = await server_mod._handle_feel_desires(
            cast(Any, config),
            cast(Any, object()),
            cast(Any, FakeDesire()),
        )

        metadata = get_tool_metadata()
        assert "You need to know something." in text
        assert metadata["emergent_desire_created"] == "You want to feel safe."
        assert metadata["emergent_desire_expired"] == "old emergent desire"
        assert metadata["impulse_boost_triggered"] is True
        assert metadata["impulse_source_memory_id"] == "mem_proust"
        assert metadata["impulse_boosted_desire"] == "curiosity"
        assert metadata["impulse_boost_amount"] == 0.15
        desire_levels = cast(dict[str, float], metadata["desire_levels"])
        assert desire_levels["curiosity"] == 0.8

    @pytest.mark.asyncio
    async def test_call_tool_registers_proust_impulse_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeMemoryStore:
            async def get_by_id(self, memory_id: str) -> Memory | None:
                assert memory_id == "mem_proust"
                return Memory(
                    id="mem_proust",
                    content="dormant signal",
                    timestamp="2024-02-20T12:00:00+00:00",
                    emotional_trace=EmotionalTrace(
                        primary=Emotion.NOSTALGIC,
                        intensity=0.7,
                    ),
                )

        class FakeImpulseManager:
            def __init__(self) -> None:
                self.called_with: list[str] = []

            def register_proust_event(self, memory: Memory) -> dict[str, float]:
                self.called_with.append(memory.id)
                return {"resonance": 0.15}

        async def fake_handle_recall(
            _config: object, _memory: object, _args: dict[str, object]
        ) -> str:
            update_tool_metadata(
                proust_triggered=True,
                proust_memory_id="mem_proust",
                fuzzy_recall_count=1,
            )
            return "recall text"

        fake_impulse = FakeImpulseManager()
        monkeypatch.setattr(server_mod, "_memory", FakeMemoryStore())
        monkeypatch.setattr(server_mod, "_impulse", fake_impulse)
        monkeypatch.setattr(server_mod, "_handle_recall", fake_handle_recall)

        result = await server_mod.call_tool("recall", {"context": "signal"})

        assert isinstance(result[0], TextContent)
        assert result[0].text == "recall text"
        assert fake_impulse.called_with == ["mem_proust"]
        assert get_tool_metadata()["proust_triggered"] is True


class TestWakeUpServerHandler:
    @pytest.mark.asyncio
    async def test_handle_wake_up_prefers_workspace_monologue(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeSync:
            def read_latest_monologue(self) -> tuple[str | None, str | None]:
                return ("A synced introspection note", "workspace-note")

        class FakeMemoryStore:
            async def list_recent(self, **_kwargs: Any) -> list[Memory]:
                pytest.fail("list_recent should not be used when workspace monologue exists")

        class FakeDesire:
            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"curiosity": 0.8}

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        monkeypatch.setattr(server_mod, "_workspace_sync", FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Last introspection (workspace-note)" in text
        assert "A synced introspection note" in text
        assert "Desires: You need to know something." in text
        assert "[high]" not in text
        assert "relationship snapshot" in text

    @pytest.mark.asyncio
    async def test_handle_wake_up_falls_back_to_recent_introspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeSync:
            def read_latest_monologue(self) -> tuple[str | None, str | None]:
                return (None, None)

        introspection = Memory(
            id="mem_intro",
            content="Remember this introspection fallback",
            timestamp="2026-02-20T12:34:56+00:00",
            category=Category.INTROSPECTION,
        )

        class FakeMemoryStore:
            async def list_recent(
                self, n: int = 1, category_filter: str | None = None
            ) -> list[Memory]:
                assert n == 1
                assert category_filter == "introspection"
                return [introspection]

        class FakeDesire:
            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"cognitive_coherence": 0.75}

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        monkeypatch.setattr(server_mod, "_workspace_sync", FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Last introspection (2026-02-20T12:34)" in text
        assert "Remember this introspection fallback" in text
        assert "Desires: You need things to make sense." in text
        assert "[mid]" not in text

    @pytest.mark.asyncio
    async def test_handle_wake_up_without_any_introspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeSync:
            def read_latest_monologue(self) -> tuple[str | None, str | None]:
                return (None, None)

        class FakeMemoryStore:
            async def list_recent(
                self, n: int = 1, category_filter: str | None = None
            ) -> list[Memory]:
                assert n == 1
                assert category_filter == "introspection"
                return []

        class FakeDesire:
            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"expression": 0.45}

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        monkeypatch.setattr(server_mod, "_workspace_sync", FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "No introspection yet." in text
        assert "Desires: Something wants to come out." in text
        assert "[low]" not in text

    @pytest.mark.asyncio
    async def test_handle_introspect_uses_blended_desire_language(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 10) -> list[Memory]:
                assert n == 30
                return []

        class FakeDesire:
            def compute_levels_with_modulation(
                self,
                *,
                context_boosts: dict[str, float] | None = None,
                emotional_modulation: dict[str, float] | None = None,
                prediction_error: dict[str, float] | None = None,
            ) -> dict[str, float]:
                assert context_boosts is not None
                assert emotional_modulation is not None
                assert prediction_error is not None
                return {"social_thirst": 0.52}

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        async def fake_derive_desire_modulation(
            _memory: object,
            *_args: Any,
            **_kwargs: Any,
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)
        monkeypatch.setattr(server_mod, "_derive_desire_modulation", fake_derive_desire_modulation)

        text = await server_mod._handle_introspect(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Desires: You want some company." in text
        assert "[high]" not in text
        assert "[mid]" not in text
        assert "[low]" not in text


class TestForgetToolServerHandlers:
    @pytest.mark.asyncio
    async def test_handle_forget_existing_memory_returns_summary_and_syncs_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        deleted_memory = Memory(
            id="mem_forget_1",
            content="This memory should be forgotten after consolidation review.",
            timestamp="2026-02-20T12:34:56+00:00",
            emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS, intensity=0.8),
            importance=4,
        )

        class FakeMemoryStore:
            async def delete(self, memory_id: str) -> Memory | None:
                assert memory_id == "mem_forget_1"
                return deleted_memory

        class FakeSync:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove_memory(self, memory_id: str) -> bool:
                self.calls.append(memory_id)
                return True

        fake_sync = FakeSync()
        monkeypatch.setattr(server_mod, "_workspace_sync", fake_sync)

        text = await server_mod._handle_forget(
            cast(Any, FakeMemoryStore()),
            {"memory_id": "mem_forget_1"},
        )

        assert "Forgot" in text
        assert "mem_forget_1" in text
        assert "emotion: curious" in text
        assert "importance: 4" in text
        assert fake_sync.calls == ["mem_forget_1"]

    @pytest.mark.asyncio
    async def test_handle_forget_missing_memory_returns_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            async def delete(self, memory_id: str) -> Memory | None:
                assert memory_id == "mem_missing"
                return None

        monkeypatch.setattr(server_mod, "_workspace_sync", None)

        text = await server_mod._handle_forget(
            cast(Any, FakeMemoryStore()),
            {"memory_id": "mem_missing"},
        )

        assert "Memory not found: mem_missing" in text
        assert "Double-check the ID." in text

    @pytest.mark.asyncio
    async def test_dispatch_forget_does_not_satisfy_implicit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[tuple[str, dict[str, Any] | None]] = []

        class FakeDesire:
            def satisfy_implicit(self, name: str, category: str | None = None) -> None:
                calls.append((name, {"category": category} if category else None))

        async def fake_handle_forget(_memory: object, _args: dict[str, object]) -> str:
            return "forgot"

        monkeypatch.setattr(server_mod, "_handle_forget", fake_handle_forget)

        text = await server_mod._dispatch(
            "forget",
            {"memory_id": "mem_abc"},
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, object()),
            cast(Any, FakeDesire()),
            cast(Any, object()),
            cast(Any, object()),
        )

        assert text == "forgot"
        assert calls == []

    @pytest.mark.asyncio
    async def test_handle_consolidate_merge_candidates_scaffold_mentions_forget(self) -> None:
        class FakeConsolidation:
            async def run(self, _memory: object) -> ConsolidationStats:
                return ConsolidationStats(
                    replay_events=1,
                    coactivation_updates=1,
                    link_updates=0,
                    refreshed_memories=1,
                    merge_candidates=(
                        MergeCandidate(
                            memory_a_id="mem_a",
                            memory_b_id="mem_b",
                            distance=0.08,
                            snippet_a="A side",
                            snippet_b="B side",
                        ),
                    ),
                )

        text = await server_mod._handle_consolidate(
            cast(Any, object()),
            cast(Any, FakeConsolidation()),
        )

        assert "use forget to remove it" in text
        assert "If both have value, consider which perspective to keep." in text

    @pytest.mark.asyncio
    async def test_handle_get_episode_filters_deleted_memory_ids_and_adds_note(self) -> None:
        episode = SimpleNamespace(
            id="ep_1",
            summary="Test episode",
            memory_ids=["mem_keep", "mem_gone"],
            start_time="2026-02-20T12:00:00+00:00",
            end_time="2026-02-20T13:00:00+00:00",
            importance=4,
        )

        class FakeEpisodeStore:
            async def get_by_id(self, episode_id: str) -> object | None:
                assert episode_id == "ep_1"
                return episode

        class FakeMemoryStore:
            async def get_by_id(self, memory_id: str) -> Memory | None:
                if memory_id == "mem_keep":
                    return Memory(
                        id="mem_keep",
                        content="still exists",
                        timestamp="2026-02-20T12:05:00+00:00",
                    )
                return None

        text = await server_mod._handle_get_episode(
            cast(Any, FakeEpisodeStore()),
            cast(Any, FakeMemoryStore()),
            {"episode_id": "ep_1"},
        )

        assert "Episode: ep_1" in text
        assert "Memories: 1" in text
        assert "Note: 1 memory(ies) no longer exist." in text
