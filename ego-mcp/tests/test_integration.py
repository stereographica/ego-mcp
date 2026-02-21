"""Tests for surface tools and backend tools via MCP client boundary."""

from __future__ import annotations

from collections.abc import Iterator
import logging
from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

import ego_mcp.server as server_mod
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.desire import DesireEngine
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore
from ego_mcp.self_model import SelfModelStore
from ego_mcp.workspace_sync import WorkspaceMemorySync

chromadb = load_chromadb()


# --- Fake embedding provider ---


class FakeEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hash(text) % 10000
            vec = [(h + i) % 100 / 100.0 for i in range(64)]
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
            results.append(vec)
        return results


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EgoConfig:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
    monkeypatch.setenv("EGO_MCP_COMPANION_NAME", "Master")
    return EgoConfig.from_env()


@pytest.fixture
def embedding_fn() -> EgoEmbeddingFunction:
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    return EgoEmbeddingFunction(provider)


@pytest.fixture
def memory(
    config: EgoConfig, embedding_fn: EgoEmbeddingFunction
) -> Iterator[MemoryStore]:
    s = MemoryStore(config, embedding_fn)
    s.connect()
    yield s
    s.close()


@pytest.fixture
def desire(config: EgoConfig) -> DesireEngine:
    return DesireEngine(config.data_dir / "desires.json")


@pytest.fixture
def episodes(
    config: EgoConfig, memory: MemoryStore, embedding_fn: EgoEmbeddingFunction
) -> EpisodeStore:
    client = chromadb.PersistentClient(path=str(config.data_dir / "chroma"))
    col = client.get_or_create_collection(
        name="ego_episodes",
        embedding_function=embedding_fn,
    )
    return EpisodeStore(memory, col)


@pytest.fixture
def consolidation() -> ConsolidationEngine:
    return ConsolidationEngine()


@pytest.fixture(autouse=True)
def bind_server_state(
    config: EgoConfig,
    memory: MemoryStore,
    desire: DesireEngine,
    episodes: EpisodeStore,
    consolidation: ConsolidationEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_mod, "_config", config)
    monkeypatch.setattr(server_mod, "_memory", memory)
    monkeypatch.setattr(server_mod, "_desire", desire)
    monkeypatch.setattr(server_mod, "_episodes", episodes)
    monkeypatch.setattr(server_mod, "_consolidation", consolidation)
    monkeypatch.setattr(
        server_mod,
        "_workspace_sync",
        WorkspaceMemorySync.from_optional_path(config.workspace_dir),
    )


async def _call(
    name: str,
    args: dict[str, Any],
    config: EgoConfig,
    memory: MemoryStore,
    desire: DesireEngine,
    episodes: EpisodeStore,
    consolidation: ConsolidationEngine,
) -> str:
    del config, memory, desire, episodes, consolidation
    contents = await server_mod.call_tool(name, args)
    assert len(contents) == 1
    content = contents[0]
    assert isinstance(content, TextContent)
    assert content.type == "text"
    return content.text


EXPECTED_TOOL_NAMES = {
    "wake_up",
    "feel_desires",
    "introspect",
    "consider_them",
    "remember",
    "recall",
    "am_i_being_genuine",
    "satisfy_desire",
    "consolidate",
    "link_memories",
    "update_relationship",
    "update_self",
    "search_memories",
    "get_episode",
    "create_episode",
}


class TestMcpBoundary:
    @pytest.mark.asyncio
    async def test_list_tools_exposes_all_names(self) -> None:
        tools = await server_mod.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOL_NAMES

    @pytest.mark.asyncio
    async def test_call_tool_logs_output(
        self,
        caplog: pytest.LogCaptureFixture,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        caplog.set_level(logging.INFO, logger=server_mod.logger.name)

        result = await _call(
            "am_i_being_genuine",
            {},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        assert "Self-check triggered." in result
        completion_logs = [
            record
            for record in caplog.records
            if record.getMessage() == "Tool execution completed"
        ]
        assert completion_logs
        completion = completion_logs[-1]
        tool_name = getattr(completion, "tool_name", None)
        tool_output = getattr(completion, "tool_output", None)
        tool_output_chars = getattr(completion, "tool_output_chars", None)
        tool_output_truncated = getattr(completion, "tool_output_truncated", None)

        assert tool_name == "am_i_being_genuine"
        assert isinstance(tool_output, str)
        assert "Self-check triggered." in tool_output
        assert tool_output_chars == len(result)
        assert tool_output_truncated is False


# === Surface Tools ===


class TestWakeUp:
    @pytest.mark.asyncio
    async def test_returns_scaffold(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "wake_up", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in result

    @pytest.mark.asyncio
    async def test_no_introspection(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "wake_up", {}, config, memory, desire, episodes, consolidation
        )
        assert "No introspection yet" in result

    @pytest.mark.asyncio
    async def test_reflects_relationship_summary(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await _call(
            "update_relationship",
            {"person": "Master", "field": "trust_level", "value": 0.82},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        result = await _call(
            "wake_up", {}, config, memory, desire, episodes, consolidation
        )
        assert "trust=0.82" in result

    @pytest.mark.asyncio
    async def test_prefers_workspace_latest_introspection(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sync = WorkspaceMemorySync(tmp_path / "workspace")
        sync.write_latest_monologue(
            "Workspace latest introspection text", "2026-02-20T09:00:00+00:00"
        )
        monkeypatch.setattr(server_mod, "_workspace_sync", sync)

        result = await _call(
            "wake_up", {}, config, memory, desire, episodes, consolidation
        )
        assert "Workspace latest introspection text" in result


class TestFeelDesires:
    @pytest.mark.asyncio
    async def test_returns_levels(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "feel_desires", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in result
        assert any(tag in result for tag in ["high", "mid", "low"])

    @pytest.mark.asyncio
    async def test_applies_interoception_adjustments(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            desire,
            "compute_levels_with_modulation",
            lambda **_kwargs: {
                "curiosity": 1.0,
                "social_thirst": 0.5,
                "cognitive_coherence": 0.5,
            },
        )
        monkeypatch.setattr(
            server_mod,
            "get_body_state",
            lambda: {
                "time_phase": "late_night",
                "system_load": "high",
                "uptime_hours": "1.0",
            },
        )
        result = await _call(
            "feel_desires", {}, config, memory, desire, episodes, consolidation
        )
        assert "curiosity[0.9/high]" in result
        assert "social_thirst[0.4/low]" in result
        assert "cognitive_coherence[0.5/mid]" in result


class TestIntrospect:
    @pytest.mark.asyncio
    async def test_returns_scaffold(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in result

    @pytest.mark.asyncio
    async def test_with_memories(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await memory.save(content="Test memory", emotion="happy")
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "Test memory" in result

    @pytest.mark.asyncio
    async def test_includes_unresolved_question_and_trend(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        self_store = SelfModelStore(config.data_dir / "self_model.json")
        self_store.add_question("What is my next focus?")
        await memory.save(
            content="Thinking about architecture",
            category="technical",
            emotion="curious",
        )
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "Unresolved questions" in result
        assert "What is my next focus?" in result
        assert "Recent tendency:" in result

    @pytest.mark.asyncio
    async def test_includes_self_and_relationship_summary(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await _call(
            "update_self",
            {"field": "current_goals", "value": ["ship the patch"]},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "Self model:" in result
        assert "Master: trust=" in result


class TestConsiderThem:
    @pytest.mark.asyncio
    async def test_default_person(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "consider_them", {}, config, memory, desire, episodes, consolidation
        )
        assert "Master" in result
        assert "---" in result

    @pytest.mark.asyncio
    async def test_reflects_relationship_data(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await _call(
            "update_relationship",
            {"person": "Master", "field": "trust_level", "value": 0.91},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        await memory.save(
            content="Master asked a technical question",
            category="conversation",
            emotion="curious",
        )
        result = await _call(
            "consider_them", {}, config, memory, desire, episodes, consolidation
        )
        assert "trust=0.91" in result
        assert "Recent dialog tendency" in result

    @pytest.mark.asyncio
    async def test_updates_recent_interaction_and_topics(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await memory.save(
            content="Master asked for code review and test planning",
            category="conversation",
            emotion="curious",
        )
        await _call(
            "consider_them", {}, config, memory, desire, episodes, consolidation
        )

        store = server_mod._relationship_store(config)
        rel = store.get("Master")
        assert rel.total_interactions >= 1
        assert len(rel.recent_mood_trajectory) >= 1
        assert "technical" in rel.preferred_topics or "planning" in rel.preferred_topics


class TestRemember:
    @pytest.mark.asyncio
    async def test_save_returns_id(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "remember",
            {"content": "A great day", "emotion": "happy"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Saved (id:" in result
        assert "Linked to" in result

    @pytest.mark.asyncio
    async def test_auto_body_state_when_missing(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "remember",
            {"content": "Body state should be auto captured"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        prefix = "Saved (id: "
        assert prefix in result
        memory_id = result.split(prefix, 1)[1].split(")", 1)[0]
        saved = await memory.get_by_id(memory_id)
        assert saved is not None
        assert saved.emotional_trace.body_state is not None

    @pytest.mark.asyncio
    async def test_syncs_workspace_files_for_introspection(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sync = WorkspaceMemorySync(tmp_path / "workspace")
        monkeypatch.setattr(server_mod, "_workspace_sync", sync)

        await _call(
            "remember",
            {
                "content": "I should preserve this introspection.",
                "category": "introspection",
                "importance": 5,
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        assert (sync.workspace_dir / "memory" / "inner-monologue-latest.md").exists()
        assert (sync.workspace_dir / "MEMORY.md").exists()


class TestRecall:
    @pytest.mark.asyncio
    async def test_recall_empty(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "recall",
            {"context": "anything"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "No related memories" in result

    @pytest.mark.asyncio
    async def test_recall_after_save(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await _call(
            "remember",
            {"content": "Sunset was beautiful"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        result = await _call(
            "recall",
            {"context": "sunset"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "---" in result

    @pytest.mark.asyncio
    async def test_recall_with_emotional_ranges(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        await _call(
            "remember",
            {
                "content": "Felt drained by the delay",
                "emotion": "sad",
                "valence": -0.8,
                "arousal": 0.7,
                "secondary": ["curious"],
                "intensity": 0.9,
                "body_state": {
                    "time_phase": "night",
                    "system_load": "medium",
                    "uptime_hours": 2.0,
                },
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        await _call(
            "remember",
            {
                "content": "Calmly solved the issue",
                "emotion": "happy",
                "valence": 0.6,
                "arousal": 0.2,
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        result = await _call(
            "recall",
            {
                "context": "issue",
                "valence_range": [-1.0, -0.4],
                "arousal_range": [0.5, 1.0],
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "drained" in result.lower()


class TestAmIBeingGenuine:
    @pytest.mark.asyncio
    async def test_returns_data_and_scaffold(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "am_i_being_genuine",
            {},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        # Must have data + --- + scaffold format
        assert "---" in result
        assert "Self-check triggered" in result
        assert "truly your own words" in result


# === Backend Tools ===


class TestSatisfyDesire:
    @pytest.mark.asyncio
    async def test_satisfy(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "satisfy_desire",
            {"name": "curiosity", "quality": 0.8},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "satisfied" in result
        assert "curiosity" in result


class TestConsolidate:
    @pytest.mark.asyncio
    async def test_consolidate_runs(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """consolidate actually runs and returns stats."""
        result = await _call(
            "consolidate",
            {},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Consolidation complete" in result
        assert "Replayed" in result
        assert "co-activations" in result

    @pytest.mark.asyncio
    async def test_consolidate_with_memories(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """consolidate with memories creates links."""
        await memory.save(content="Memory A")
        await memory.save(content="Memory B")
        result = await _call(
            "consolidate",
            {},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Consolidation complete" in result


class TestLinkMemories:
    @pytest.mark.asyncio
    async def test_link_creates_bidirectional(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """link_memories creates bidirectional links."""
        m1 = await memory.save(content="Memory Alpha")
        m2 = await memory.save(content="Memory Beta")
        result = await _call(
            "link_memories",
            {"source_id": m1.id, "target_id": m2.id, "link_type": "related"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Linked" in result
        assert "↔" in result

        # Verify bidirectional
        src = await memory.get_by_id(m1.id)
        tgt = await memory.get_by_id(m2.id)
        assert src is not None and tgt is not None
        assert any(link.target_id == m2.id for link in src.linked_ids)
        assert any(link.target_id == m1.id for link in tgt.linked_ids)

    @pytest.mark.asyncio
    async def test_link_nonexistent(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "link_memories",
            {"source_id": "fake_a", "target_id": "fake_b"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "not found" in result or "already exists" in result


class TestSearchMemories:
    @pytest.mark.asyncio
    async def test_search_empty(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "search_memories",
            {"query": "anything"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_search_with_date_params(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """search_memories accepts date_from and date_to."""
        await memory.save(content="Daily entry")
        result = await _call(
            "search_memories",
            {"query": "daily", "date_from": "2020-01-01", "date_to": "2030-12-31"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Found" in result or "No memories found" in result


class TestUpdateRelationship:
    @pytest.mark.asyncio
    async def test_update(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "update_relationship",
            {"person": "Master", "field": "trust", "value": 0.9},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Updated Master.trust" in result


class TestUpdateSelf:
    @pytest.mark.asyncio
    async def test_update(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "update_self",
            {"field": "confidence", "value": 0.8},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Updated self.confidence" in result


class TestGetEpisode:
    @pytest.mark.asyncio
    async def test_get_nonexistent(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "get_episode",
            {"episode_id": "ep_nonexistent"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_get_episode_after_create(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """get_episode returns details after creation."""
        m1 = await memory.save(content="First thing")
        m2 = await memory.save(content="Second thing")
        create_result = await _call(
            "create_episode",
            {"memory_ids": [m1.id, m2.id], "summary": "Two things happened"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Created episode" in create_result
        # Extract episode ID
        ep_id = create_result.split("Created episode ")[1].split(" ")[0]

        get_result = await _call(
            "get_episode",
            {"episode_id": ep_id},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Two things happened" in get_result
        assert "Memories: 2" in get_result


class TestCreateEpisode:
    @pytest.mark.asyncio
    async def test_create(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        m1 = await memory.save(content="Morning walk")
        result = await _call(
            "create_episode",
            {"memory_ids": [m1.id], "summary": "Morning routine"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Created episode" in result
        assert "1 memories" in result


# === Integration: Flow tests ===


class TestSessionFlow:
    @pytest.mark.asyncio
    async def test_full_session(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        wake = await _call(
            "wake_up", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in wake

        intro = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in intro

        rem = await _call(
            "remember",
            {
                "content": "I feel curious.",
                "category": "introspection",
                "emotion": "curious",
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Saved" in rem


class TestHeartbeatFlow:
    @pytest.mark.asyncio
    async def test_full_heartbeat(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        """Heartbeat flow: feel_desires → introspect → remember."""
        feel = await _call(
            "feel_desires", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in feel
        assert any(tag in feel for tag in ["high", "mid", "low"])

        intro = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "---" in intro

        rem = await _call(
            "remember",
            {
                "content": "Heartbeat reflection: feeling restless.",
                "category": "introspection",
                "emotion": "curious",
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Saved" in rem


class TestToolDefinitionSize:
    @pytest.mark.asyncio
    async def test_list_tools_response_size(self) -> None:
        import json

        tools = await server_mod.list_tools()
        total_text = json.dumps([t.model_dump() for t in tools], ensure_ascii=False)
        total_chars = len(total_text)
        assert len(tools) == 15
        # Target: 7,000 chars or less
        assert total_chars <= 7000, (
            f"Tool definitions too large: {total_chars} chars (target: ≤7,000)"
        )
