"""Focused tests for server-side tool dispatch behavior."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mcp.types import TextContent

import ego_mcp._server_backend_handlers as backend_handlers_mod
import ego_mcp._server_surface_attune as attune_surface_mod
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
from ego_mcp.desire_catalog import default_desire_catalog, desire_catalog_settings_path
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.memory import MemoryStore
from ego_mcp.notion import NotionStore
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
    return DesireEngine.from_data_dir(tmp_path)


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
            _config: object, _memory: object, _args: dict[str, object], **kwargs: object
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
    async def test_remember_succeeds_when_catalog_is_invalid(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        catalog_path = desire_catalog_settings_path(tmp_path)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text('{"version": 1, "fixed_desires": {}}', encoding="utf-8")
        invalid_desire = DesireEngine.from_data_dir(tmp_path)

        async def fake_handle_remember(
            _config: object,
            _memory: object,
            _args: dict[str, object],
            **kwargs: object,
        ) -> str:
            return "saved despite invalid desires"

        monkeypatch.setattr(server_mod, "_handle_remember", fake_handle_remember)

        result = await server_mod._dispatch(
            "remember",
            {"content": "note", "category": "daily"},
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, object()),
            invalid_desire,
            cast(Any, object()),
            cast(Any, object()),
        )

        assert result == "saved despite invalid desires"

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
            _desire: object | None = None,
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
            _config: object, _memory: object, _args: dict[str, object], **kwargs: object
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
            def __init__(self) -> None:
                self._notions = {
                    "notion_1": Notion(
                        id="notion_1",
                        label="home & safety (anxious)",
                        emotion_tone=Emotion.ANXIOUS,
                        confidence=0.9,
                        tags=["home", "safety"],
                        related_notion_ids=["notion_2"],
                    ),
                    "notion_2": Notion(
                        id="notion_2",
                        label="steady shelter",
                        emotion_tone=Emotion.NEUTRAL,
                        confidence=0.7,
                    ),
                }

            def search_related(
                self,
                *,
                source_memory_ids: list[str],
                tags: list[str],
                min_tag_match: int = 1,
            ) -> list[Notion]:
                assert source_memory_ids == ["mem_1"]
                assert tags == ["home", "safety"]
                assert min_tag_match == 1
                return [self._notions["notion_1"]]

            def get_by_id(self, notion_id: str) -> Notion | None:
                return self._notions.get(notion_id)

            def get_associated(self, notion_id: str, depth: int = 1) -> list[Notion]:
                assert notion_id == "notion_1"
                assert depth == 1
                return [self._notions["notion_2"]]

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
        assert '  → "steady shelter" confidence: 0.7' in text

    @pytest.mark.asyncio
    async def test_handle_recall_includes_source_memory_related_notions(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            def collection_count(self) -> int:
                return 1

            async def recall(
                self,
                _context: str,
                **_kwargs: object,
            ) -> list[MemorySearchResult]:
                return [
                    MemorySearchResult(
                        memory=Memory(
                            id="mem_shared",
                            content="This memory has no tags.",
                            timestamp="2026-02-26T00:00:00+00:00",
                            tags=[],
                            emotional_trace=EmotionalTrace(
                                primary=Emotion.CURIOUS,
                                intensity=0.4,
                            ),
                        ),
                        distance=0.1,
                        score=0.2,
                        decay=0.8,
                    )
                ]

        class FakeNotionStore:
            def __init__(self) -> None:
                self._notions = {
                    "notion_2": Notion(
                        id="notion_2",
                        label="shared thread (curious)",
                        emotion_tone=Emotion.CURIOUS,
                        confidence=0.8,
                        source_memory_ids=["mem_shared"],
                    )
                }

            def search_related(
                self,
                *,
                source_memory_ids: list[str],
                tags: list[str],
                min_tag_match: int = 1,
            ) -> list[Notion]:
                assert source_memory_ids == ["mem_shared"]
                assert tags == []
                assert min_tag_match == 1
                return list(self._notions.values())

            def get_by_id(self, notion_id: str) -> Notion | None:
                return self._notions.get(notion_id)

            def get_associated(self, notion_id: str, depth: int = 1) -> list[Notion]:
                assert notion_id == "notion_2"
                assert depth == 1
                return []

        monkeypatch.setattr(
            memory_surface_mod,
            "get_notion_store",
            lambda: FakeNotionStore(),
        )

        text = await memory_surface_mod._handle_recall(
            cast(Any, SimpleNamespace()),
            cast(Any, FakeMemoryStore()),
            {"context": "shared", "n_results": 1},
        )

        assert "--- notions ---" in text
        assert '"shared thread (curious)" curious confidence: 0.8' in text

    @pytest.mark.asyncio
    async def test_handle_consider_them_does_not_mutate_relationship_interactions(
        self,
        tmp_path: Path,
    ) -> None:
        config = EgoConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            api_key="test-key",
            data_dir=tmp_path,
            companion_name="Master",
            workspace_dir=None,
            timezone="UTC",
        )

        class FakeMemoryStore:
            async def list_recent(
                self,
                n: int = 200,
                category_filter: str | None = None,
            ) -> list[Memory]:
                assert n == 200
                assert category_filter == "conversation"
                return [
                    Memory(
                        id="mem_1",
                        content="Master asked about config and code review",
                        timestamp="2026-03-28T00:00:00+00:00",
                        category=Category.CONVERSATION,
                        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS),
                    )
                ]

        first = await core_surface_mod._handle_consider_them(
            config,
            cast(Any, FakeMemoryStore()),
            {"person": "Master"},
        )
        second = await core_surface_mod._handle_consider_them(
            config,
            cast(Any, FakeMemoryStore()),
            {"person": "Master"},
        )
        store = server_mod._relationship_store(config)
        rel = store.get("Master")

        assert "interactions=0" in first
        assert "interactions=0" in second
        assert rel.total_interactions == 0

    @pytest.mark.asyncio
    async def test_handle_consider_them_includes_person_impressions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = EgoConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            api_key="test-key",
            data_dir=tmp_path,
            companion_name="Master",
            workspace_dir=None,
            timezone="UTC",
        )

        class FakeMemoryStore:
            async def list_recent(
                self,
                n: int = 200,
                category_filter: str | None = None,
            ) -> list[Memory]:
                return []

        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="n1",
                        label="Working together feels easy",
                        emotion_tone=Emotion.HAPPY,
                        confidence=0.8,
                        person_id="Master",
                    )
                ]

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())

        text = await core_surface_mod._handle_consider_them(
            config,
            cast(Any, FakeMemoryStore()),
            {"person": "Master"},
        )

        assert "Impressions of Master:" in text
        assert "Working together feels easy" in text

    @pytest.mark.asyncio
    async def test_handle_consider_them_hides_predictability_scaffold_when_removed(
        self,
        tmp_path: Path,
    ) -> None:
        config = EgoConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            api_key="test-key",
            data_dir=tmp_path,
            companion_name="Master",
            workspace_dir=None,
            timezone="UTC",
        )
        settings_path = tmp_path / "settings" / "desires.json"
        payload = default_desire_catalog().model_dump(mode="json")
        del payload["fixed_desires"]["predictability"]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        desire = DesireEngine.from_data_dir(tmp_path)

        class FakeMemoryStore:
            async def list_recent(
                self,
                n: int = 200,
                category_filter: str | None = None,
            ) -> list[Memory]:
                return []

        text = await core_surface_mod._handle_consider_them(
            config,
            cast(Any, FakeMemoryStore()),
            {"person": "Master"},
            desire,
        )

        assert "predictability" not in text

    @pytest.mark.asyncio
    async def test_handle_consider_them_omits_impressions_without_matching_notions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = EgoConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            api_key="test-key",
            data_dir=tmp_path,
            companion_name="Master",
            workspace_dir=None,
            timezone="UTC",
        )

        class FakeMemoryStore:
            async def list_recent(
                self,
                n: int = 200,
                category_filter: str | None = None,
            ) -> list[Memory]:
                return []

        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="n1",
                        label="Unrelated notion",
                        emotion_tone=Emotion.HAPPY,
                        confidence=0.8,
                        person_id="SomeoneElse",
                    )
                ]

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())

        text = await core_surface_mod._handle_consider_them(
            config,
            cast(Any, FakeMemoryStore()),
            {"person": "Master"},
        )

        assert "Impressions of Master:" not in text

    @pytest.mark.asyncio
    async def test_completion_log_context_emits_snapshot_for_non_attune(
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
    async def test_handle_attune_records_telemetry_and_blends_output(
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
            _state: dict[str, Any] = {}

            def generate_emergent_desires(self, notions: list[Notion]) -> list[str]:
                assert len(notions) == 1
                return ["feel_safe"]

            def expire_emergent_desires(self) -> list[str]:
                return ["old emergent desire"]

            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            @property
            def catalog(self) -> None:
                return None

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

        class FakeMemoryStore:
            async def list_recent(self, n: int = 30) -> list[Memory]:
                return []

        monkeypatch.setattr(attune_surface_mod, "get_notion_store", lambda: FakeNotionStore())
        monkeypatch.setattr(
            attune_surface_mod, "get_impulse_manager", lambda: FakeImpulseManager()
        )

        async def fake_derive_desire_modulation(
            _memory: object,
            *_args: Any,
            **_kwargs: Any,
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        monkeypatch.setattr(
            attune_surface_mod,
            "_derive_desire_modulation_override",
            fake_derive_desire_modulation,
        )
        monkeypatch.setattr(
            attune_surface_mod,
            "_get_body_state_override",
            lambda: {"time_phase": "morning"},
        )

        config = SimpleNamespace(companion_name="Master", data_dir=tmp_path)
        text = await attune_surface_mod._handle_attune(
            cast(Any, config),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        metadata = get_tool_metadata()
        assert "---" in text
        assert "Desire currents:" in text
        assert "Recent" in text
        assert metadata["emergent_desire_created"] == "feel_safe"
        assert metadata["emergent_desire_expired"] == "old emergent desire"
        desire_levels = cast(dict[str, float], metadata["desire_levels"])
        assert desire_levels["curiosity"] == 0.8

    @pytest.mark.asyncio
    async def test_handle_attune_does_not_reintroduce_removed_fixed_desires(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings_path = tmp_path / "settings" / "desires.json"
        payload = default_desire_catalog().model_dump(mode="json")
        del payload["fixed_desires"]["curiosity"]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        desire = DesireEngine.from_data_dir(tmp_path)

        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return []

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

        async def fake_derive_desire_modulation(
            _memory: object,
            *_args: Any,
            **_kwargs: Any,
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        class FakeMemoryStore:
            async def list_recent(self, n: int = 30) -> list[Memory]:
                return []

        monkeypatch.setattr(attune_surface_mod, "get_notion_store", lambda: FakeNotionStore())
        monkeypatch.setattr(
            attune_surface_mod,
            "get_impulse_manager",
            lambda: FakeImpulseManager(),
        )
        monkeypatch.setattr(
            attune_surface_mod,
            "_derive_desire_modulation_override",
            fake_derive_desire_modulation,
        )
        monkeypatch.setattr(
            attune_surface_mod,
            "_get_body_state_override",
            lambda: {"time_phase": "morning"},
        )

        text = await attune_surface_mod._handle_attune(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            desire,
        )

        metadata = get_tool_metadata()
        desire_levels = cast(dict[str, float], metadata["desire_levels"])
        assert "curiosity" not in desire_levels
        assert "You need to know something." not in text

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
    """Tests for the rewritten _handle_wake_up() which outputs emotional texture,
    embers, Proust recall, introspection, desire currents, emergent pull, and
    relationship snapshot."""

    @staticmethod
    def _patch_wake_up_deps(monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatch heavy dependencies that _handle_wake_up calls so the
        tests stay focused on structure and output text."""
        # generate_embers -> no embers
        monkeypatch.setattr(core_surface_mod, "generate_embers", lambda *_a, **_k: [])
        # find_proust_memory -> no involuntary recall
        async def _no_proust(*_a: Any, **_k: Any) -> None:
            return None

        monkeypatch.setattr(core_surface_mod, "find_proust_memory", _no_proust)
        # get_notion_store -> empty (used by _list_notions_safe)
        class _EmptyNotionStore:
            def list_all(self) -> list[Notion]:
                return []

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: _EmptyNotionStore())

    @pytest.mark.asyncio
    async def test_handle_wake_up_prefers_workspace_monologue(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        class FakeSync:
            def read_latest_monologue(self) -> tuple[str | None, str | None]:
                return ("A synced introspection note", "workspace-note")

        call_log: list[dict[str, Any]] = []

        class FakeMemoryStore:
            async def list_recent(
                self, n: int = 10, category_filter: str | None = None
            ) -> list[Memory]:
                call_log.append({"n": n, "category_filter": category_filter})
                return []

        class FakeDesire:
            _state: dict[str, Any] = {}
            ema_levels: dict[str, float] = {}
            catalog = None

            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"curiosity": 0.8}

            def expire_emergent_desires(self) -> list[str]:
                return []

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        self._patch_wake_up_deps(monkeypatch)
        monkeypatch.setattr(core_surface_mod, "get_workspace_sync", lambda: FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Last introspection (workspace-note)" in text
        assert "A synced introspection note" in text
        assert "Desire currents:" in text
        assert "[high]" not in text
        assert "relationship snapshot" in text
        # First call should be n=30 for emotional texture
        assert call_log[0]["n"] == 30
        # No second list_recent call for introspection (workspace provided it)
        assert all(c.get("category_filter") != "introspection" for c in call_log)

    @pytest.mark.asyncio
    async def test_handle_wake_up_falls_back_to_recent_introspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
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
                self, n: int = 10, category_filter: str | None = None
            ) -> list[Memory]:
                if n == 30 and category_filter is None:
                    return []  # emotional texture query
                if n == 1 and category_filter == "introspection":
                    return [introspection]
                return []

        class FakeDesire:
            _state: dict[str, Any] = {}
            ema_levels: dict[str, float] = {}
            catalog = None

            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"cognitive_coherence": 0.75}

            def expire_emergent_desires(self) -> list[str]:
                return []

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        self._patch_wake_up_deps(monkeypatch)
        monkeypatch.setattr(core_surface_mod, "get_workspace_sync", lambda: FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Last introspection (2026-02-20T12:34)" in text
        assert "Remember this introspection fallback" in text
        assert "Desire currents:" in text
        assert "[mid]" not in text

    @pytest.mark.asyncio
    async def test_handle_wake_up_without_any_introspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        class FakeSync:
            def read_latest_monologue(self) -> tuple[str | None, str | None]:
                return (None, None)

        class FakeMemoryStore:
            async def list_recent(
                self, n: int = 10, category_filter: str | None = None
            ) -> list[Memory]:
                return []

        class FakeDesire:
            _state: dict[str, Any] = {}
            ema_levels: dict[str, float] = {}
            catalog = None

            def compute_levels_with_modulation(self) -> dict[str, float]:
                return {"expression": 0.45}

            def expire_emergent_desires(self) -> list[str]:
                return []

        async def fake_relationship_snapshot(
            _config: object, _memory: object, _person: str
        ) -> str:
            return "relationship snapshot"

        self._patch_wake_up_deps(monkeypatch)
        monkeypatch.setattr(core_surface_mod, "get_workspace_sync", lambda: FakeSync())
        monkeypatch.setattr(server_mod, "_relationship_snapshot", fake_relationship_snapshot)

        text = await server_mod._handle_wake_up(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "No introspection yet." in text
        assert "Desire currents:" in text
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
            @property
            def ema_levels(self) -> dict[str, float]:
                return {"social_thirst": 0.5}

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

        assert "Desire currents: That quiet wish for company." in text
        assert "[high]" not in text
        assert "[mid]" not in text
        assert "[low]" not in text

    @pytest.mark.asyncio
    async def test_handle_introspect_hides_predictability_scaffold_when_removed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings_path = tmp_path / "settings" / "desires.json"
        payload = default_desire_catalog().model_dump(mode="json")
        del payload["fixed_desires"]["predictability"]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        desire = DesireEngine.from_data_dir(tmp_path)

        class FakeMemoryStore:
            async def list_recent(self, n: int = 10) -> list[Memory]:
                return []

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
            desire,
        )

        assert "consider satisfying predictability" not in text

    @pytest.mark.asyncio
    async def test_handle_introspect_includes_conceptual_framework(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 10) -> list[Memory]:
                assert n == 30
                return []

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {"social_thirst": 0.5}

            def compute_levels_with_modulation(
                self,
                *,
                context_boosts: dict[str, float] | None = None,
                emotional_modulation: dict[str, float] | None = None,
                prediction_error: dict[str, float] | None = None,
            ) -> dict[str, float]:
                return {"social_thirst": 0.52}

        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="n1",
                        label="Pattern seeking",
                        emotion_tone=Emotion.CURIOUS,
                        confidence=0.82,
                        related_notion_ids=["n2"],
                    ),
                    Notion(
                        id="n2",
                        label="Continuity",
                        emotion_tone=Emotion.CURIOUS,
                        confidence=0.75,
                        related_notion_ids=["n1"],
                    ),
                ]

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
        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())

        text = await server_mod._handle_introspect(
            cast(Any, SimpleNamespace(companion_name="Master", data_dir=tmp_path)),
            cast(Any, FakeMemoryStore()),
            cast(Any, FakeDesire()),
        )

        assert "Notion landscape:" in text
        assert '- "Pattern seeking" confidence: 0.8 → "Continuity"' in text
        assert '- "Continuity" confidence: 0.8 → "Pattern seeking"' in text


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

    def test_handle_pause_includes_convictions(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="n1",
                        label="Continuity matters",
                        confidence=0.9,
                        reinforcement_count=5,
                    )
                ]

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())

        text = core_surface_mod._handle_pause()

        assert "Your convictions:" in text
        assert "Continuity matters" in text

    def test_handle_pause_falls_back_without_convictions(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeNotionStore:
            def list_all(self) -> list[Notion]:
                return [
                    Notion(
                        id="n1",
                        label="Tentative pattern",
                        confidence=0.69,
                        reinforcement_count=5,
                    )
                ]

        monkeypatch.setattr(core_surface_mod, "get_notion_store", lambda: FakeNotionStore())

        text = core_surface_mod._handle_pause()

        assert "Self-check triggered." in text
        assert "Your convictions:" not in text

    def test_handle_curate_notions_list_and_delete(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = NotionStore(tmp_path / "notions.json")
        store.save(
            Notion(
                id="notion_1",
                label="Pattern seeking",
                confidence=0.8,
                reinforcement_count=3,
                person_id="Master",
                related_notion_ids=["notion_2"],
                created="2026-02-24T00:00:00+00:00",
            )
        )
        monkeypatch.setattr(
            backend_handlers_mod,
            "_call_relative_time",
            lambda _timestamp, now=None: "2d ago",
        )
        text = server_mod._handle_curate_notions({"action": "list"}, store)
        assert get_tool_metadata()["curate_action"] == "list"
        deleted = server_mod._handle_curate_notions(
            {"action": "delete", "notion_id": "notion_1"},
            store,
        )

        assert "Pattern seeking" in text
        assert "reinf=3" in text
        assert "person=Master" in text
        assert "age=2d ago" in text
        assert "---" in text
        assert "Which of these still ring true?" in text
        assert "Deleted notion_1" in deleted
        assert store.get_by_id("notion_1") is None

    def test_handle_curate_notions_merge_and_relabel(self, tmp_path: Path) -> None:
        store = NotionStore(tmp_path / "notions.json")
        store.save(
            Notion(
                id="keep",
                label="Pattern seeking",
                source_memory_ids=["m1", "m2"],
                confidence=0.8,
                reinforcement_count=2,
            )
        )
        store.save(
            Notion(
                id="absorb",
                label="Signal seeking",
                source_memory_ids=["m2", "m3"],
                confidence=0.7,
                reinforcement_count=1,
            )
        )

        merged = server_mod._handle_curate_notions(
            {"action": "merge", "notion_id": "absorb", "merge_into": "keep", "person": "Master"},
            store,
        )
        relabeled = server_mod._handle_curate_notions(
            {"action": "relabel", "notion_id": "keep", "new_label": "Merged pattern", "person": ""},
            store,
        )
        notion = store.get_by_id("keep")

        assert "Merged absorb into keep" in merged
        assert "Renamed keep to Merged pattern" in relabeled
        assert notion is not None
        assert notion.label == "Merged pattern"
        assert notion.person_id == ""

    def test_handle_curate_notions_error_paths(self, tmp_path: Path) -> None:
        store = NotionStore(tmp_path / "notions.json")

        missing_id = server_mod._handle_curate_notions({"action": "delete"}, store)
        missing_merge_into = server_mod._handle_curate_notions(
            {"action": "merge", "notion_id": "missing"},
            store,
        )
        missing_new_label = server_mod._handle_curate_notions(
            {"action": "relabel", "notion_id": "missing"},
            store,
        )
        missing_target = server_mod._handle_curate_notions(
            {"action": "delete", "notion_id": "missing"},
            store,
        )

        assert "notion_id is required." in missing_id
        assert "merge_into is required for merge." in missing_merge_into
        assert "new_label is required for relabel." in missing_new_label
        assert "Notion not found: missing" in missing_target

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


class TestParameterFormatValidation:
    @pytest.mark.asyncio
    async def test_call_tool_returns_error_text_for_xml_arguments(
        self,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        before = _seed_high_desire(desire, "expression")

        handler_calls: list[dict[str, object]] = []

        async def spy_handle_remember(
            _config: object,
            _memory: object,
            args: dict[str, object],
            **_kwargs: object,
        ) -> str:
            handler_calls.append(args)
            return "should not be reached"

        monkeypatch.setattr(server_mod, "_handle_remember", spy_handle_remember)

        result = await server_mod.call_tool(
            "remember",
            {"content": "<content>hello</content>"},
        )

        assert isinstance(result[0], TextContent)
        assert "[parameter_format_error]" in result[0].text
        assert "`remember`" in result[0].text
        assert "`content`" in result[0].text
        # Downstream handler must not be invoked and desire must not shift.
        assert handler_calls == []
        assert desire.compute_levels()["expression"] == pytest.approx(before)
