"""Tests for surface tools and backend tools via MCP client boundary."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

import ego_mcp.server as server_mod
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.config import EgoConfig
from ego_mcp.consolidation import ConsolidationEngine
from ego_mcp.desire import DesireEngine
from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider
from ego_mcp.episode import EpisodeStore
from ego_mcp.memory import MemoryStore
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Emotion, EmotionalTrace, Memory
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
    "emotion_trend",
    "get_episode",
    "create_episode",
}


class TestMcpBoundary:
    @pytest.mark.asyncio
    async def test_list_tools_exposes_all_names(self) -> None:
        tools = await server_mod.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOL_NAMES

    @pytest.mark.asyncio
    async def test_recall_schema_includes_date_filters(self) -> None:
        tools = await server_mod.list_tools()
        recall_tool = next(tool for tool in tools if tool.name == "recall")
        props = recall_tool.inputSchema["properties"]
        assert "date_from" in props
        assert "date_to" in props

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
        assert isinstance(getattr(completion, "time_phase", None), str)
        assert getattr(completion, "time_phase")


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

    @pytest.mark.asyncio
    async def test_mentions_private_memory_option(
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
        assert "remember(private=true)" in result


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

    @pytest.mark.asyncio
    async def test_adds_nagging_scaffold_when_fading_question_exists(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What am I still not seeing?", importance=5)
        for item in store._data.get("question_log", []):
            if isinstance(item, dict) and item.get("id") == qid:
                item["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=90)
                ).isoformat()
        store._save()

        monkeypatch.setattr(
            desire,
            "compute_levels_with_modulation",
            lambda **_kwargs: {
                "cognitive_coherence": 0.7,
                "curiosity": 0.3,
                "social_thirst": 0.3,
            },
        )
        monkeypatch.setattr(
            server_mod,
            "get_body_state",
            lambda: {
                "time_phase": "afternoon",
                "system_load": "low",
                "uptime_hours": 1.0,
            },
        )
        result = await _call(
            "feel_desires", {}, config, memory, desire, episodes, consolidation
        )
        assert "Something feels unresolved." in result
        assert "Consider running introspect" in result


class TestDesireModulationQuestionForgetting:
    @pytest.mark.asyncio
    async def test_fading_important_question_boosts_cognitive_coherence(
        self,
        config: EgoConfig,
        memory: MemoryStore,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("How should I structure heartbeat cadence?", importance=5)
        for item in store._data.get("question_log", []):
            if isinstance(item, dict) and item.get("id") == qid:
                item["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=90)
                ).isoformat()
        store._save()

        context_boosts, _emotional_modulation, _prediction_error = (
            await server_mod._derive_desire_modulation(memory)
        )
        assert context_boosts.get("cognitive_coherence", 0.0) > 0.0


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
    async def test_includes_question_ids_importance_and_resolve_hint(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        self_store = SelfModelStore(config.data_dir / "self_model.json")
        qid = self_store.add_question("How should I express concern clearly?", importance=5)
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert f"[{qid}]" in result
        assert "importance: 5" in result
        assert 'update_self(field="resolve_question", value="' in result

    @pytest.mark.asyncio
    async def test_hides_resurfacing_when_coherence_is_low(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What is the right heartbeat interval?", importance=4)
        for item in store._data.get("question_log", []):
            if isinstance(item, dict) and item.get("id") == qid:
                item["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=60)
                ).isoformat()
        store._save()

        async def fake_modulation(
            _memory: MemoryStore, *_args: Any, **_kwargs: Any
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        monkeypatch.setattr(server_mod, "_derive_desire_modulation", fake_modulation)
        monkeypatch.setattr(
            desire,
            "compute_levels_with_modulation",
            lambda **_kwargs: {
                "cognitive_coherence": 0.2,
                "curiosity": 0.2,
                "social_thirst": 0.2,
            },
        )
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "Resurfacing (you'd almost forgotten):" not in result

    @pytest.mark.asyncio
    async def test_shows_resurfacing_when_coherence_is_high(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What is the right heartbeat interval?", importance=4)
        for item in store._data.get("question_log", []):
            if isinstance(item, dict) and item.get("id") == qid:
                item["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=60)
                ).isoformat()
        store._save()

        async def fake_modulation(
            _memory: MemoryStore, *_args: Any, **_kwargs: Any
        ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
            return {}, {}, {}

        monkeypatch.setattr(server_mod, "_derive_desire_modulation", fake_modulation)
        monkeypatch.setattr(
            desire,
            "compute_levels_with_modulation",
            lambda **_kwargs: {
                "cognitive_coherence": 0.8,
                "curiosity": 0.2,
                "social_thirst": 0.2,
            },
        )
        result = await _call(
            "introspect", {}, config, memory, desire, episodes, consolidation
        )
        assert "Resurfacing (you'd almost forgotten):" in result

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
        assert "No similar memories found yet." in result
        assert "Do any of these connections surprise you?" in result

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

    @pytest.mark.asyncio
    async def test_private_memory_skips_workspace_sync_and_persists_flag(
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

        result = await _call(
            "remember",
            {
                "content": "Private introspection should stay internal.",
                "category": "introspection",
                "importance": 5,
                "private": True,
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "Synced" not in result

        prefix = "Saved (id: "
        assert prefix in result
        memory_id = result.split(prefix, 1)[1].split(")", 1)[0]
        saved = await memory.get_by_id(memory_id)
        assert saved is not None
        assert saved.is_private is True

        assert not (sync.workspace_dir / "memory" / "inner-monologue-latest.md").exists()
        assert not (sync.workspace_dir / "MEMORY.md").exists()

    @pytest.mark.asyncio
    async def test_reports_positive_links_when_related_memories_exist(
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

        content = "I solved a compiler warning by narrowing the generic type."

        await _call(
            "remember",
            {"content": content, "category": "technical"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        result = await _call(
            "remember",
            {"content": content, "category": "technical"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        assert "Most related:" in result
        assert "similarity:" in result
        match = re.search(r"Linked to (\d+) existing memories\.", result)
        assert match is not None, result
        assert int(match.group(1)) >= 1

    @pytest.mark.asyncio
    async def test_remember_surfaces_related_forgotten_question(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What's the optimal heartbeat interval?", importance=4)
        for item in store._data.get("question_log", []):
            if isinstance(item, dict) and item.get("id") == qid:
                item["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=120)
                ).isoformat()
        store._save()

        monkeypatch.setattr(
            server_mod,
            "_find_related_forgotten_questions",
            lambda *_args, **_kwargs: [
                {
                    "id": qid,
                    "question": "What's the optimal heartbeat interval?",
                    "importance": 4,
                    "age_days": 120.0,
                    "band": "dormant",
                    "trigger_similarity": 0.82,
                }
            ],
        )

        result = await _call(
            "remember",
            {"content": "I should revisit the heartbeat interval configuration."},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "triggered a forgotten question" in result.lower()
        assert "optimal heartbeat interval" in result

    @pytest.mark.asyncio
    async def test_remember_does_not_surface_forgotten_question_when_none(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        result = await _call(
            "remember",
            {"content": "A standalone memory with no matching dormant question."},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "triggered a forgotten question" not in result.lower()


class TestRelativeTimeFormatting:
    def test_relative_time_buckets(self) -> None:
        now = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
        assert server_mod._relative_time("2026-02-22T11:30:00+00:00", now=now) == "30m ago"
        assert server_mod._relative_time("2026-02-22T10:00:00+00:00", now=now) == "2h ago"
        assert server_mod._relative_time("2026-02-20T12:00:00+00:00", now=now) == "2d ago"
        assert server_mod._relative_time("2026-02-12T12:00:00+00:00", now=now) == "1w ago"
        assert server_mod._relative_time("2025-11-22T12:00:00+00:00", now=now) == "3mo ago"
        assert server_mod._relative_time("2025-02-22T12:00:00+00:00", now=now) == "1y ago"


class TestRecallScaffold:
    def test_recall_scaffold_without_filters(self) -> None:
        text = server_mod._recall_scaffold(3, 50, [])
        assert "Showing 3 of ~50" in text
        assert "Narrow by:" in text
        assert "Need narrative detail? Use get_episode." in text
        assert "If you found a new relation, use link_memories." in text

    def test_recall_scaffold_with_filters_shows_remaining(self) -> None:
        text = server_mod._recall_scaffold(3, 12, ["emotion_filter", "date_from"])
        assert "Also available:" in text
        assert "emotion_filter" not in text.split("Also available:", 1)[1]
        assert "date_from" not in text.split("Also available:", 1)[1]


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

    @pytest.mark.asyncio
    async def test_recall_after_save_with_expanded_emotion(
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
                "content": "I felt a diffuse worry before the deploy",
                "emotion": "anxious",
                "secondary": ["curious"],
                "intensity": 0.8,
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        result = await _call(
            "recall",
            {"context": "deploy worry", "emotion_filter": "anxious"},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        lowered = result.lower()
        assert "anxious" in lowered
        assert "deploy" in lowered

    @pytest.mark.asyncio
    async def test_recall_includes_private_flag(
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
                "content": "shared token private memory sample",
                "private": True,
                "category": "introspection",
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
                "content": "shared token public memory sample",
                "private": False,
                "category": "daily",
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        result = await _call(
            "recall",
            {"context": "shared token", "n_results": 5},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        lowered = result.lower()
        assert "private" in lowered
        assert "private: false" not in lowered

    @pytest.mark.asyncio
    async def test_recall_accepts_date_from_and_date_to(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        async def fake_search(query: str, **kwargs: Any) -> list[Any]:
            captured["query"] = query
            captured.update(kwargs)
            return []

        monkeypatch.setattr(memory, "search", fake_search)
        result = await _call(
            "recall",
            {
                "context": "heartbeat",
                "date_from": "2026-02-01",
                "date_to": "2026-02-20",
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert "No related memories" in result
        assert captured["query"] == "heartbeat"
        assert captured["date_from"] == "2026-02-01"
        assert captured["date_to"] == "2026-02-20"

    @pytest.mark.asyncio
    async def test_recall_caps_n_results_at_ten(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        async def fake_recall(context: str, **kwargs: Any) -> list[Any]:
            captured["context"] = context
            captured.update(kwargs)
            return []

        monkeypatch.setattr(memory, "recall", fake_recall)
        await _call(
            "recall",
            {"context": "anything", "n_results": 99},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert captured["n_results"] == 10

    @pytest.mark.asyncio
    async def test_recall_result_format_includes_relative_time_and_undercurrent(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = "recall-format-token"
        await _call(
            "remember",
            {
                "content": f"{token} deeply emotional memory",
                "emotion": "moved",
                "secondary": ["anxious"],
                "intensity": 0.9,
                "importance": 4,
                "private": True,
            },
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        monkeypatch.setattr(server_mod, "_relative_time", lambda *_args, **_kwargs: "2d ago")
        result = await _call(
            "recall",
            {"context": token, "emotion_filter": "moved", "n_results": 3},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        lowered = result.lower()
        assert " of ~" in result
        assert "[2d ago]" in result
        assert "emotion: moved(0.9)" in lowered
        assert "undercurrent: anxious" in lowered
        assert "importance: 4" in lowered
        assert "score:" in lowered
        assert "private" in lowered


class TestEmotionTrend:
    @staticmethod
    def _mem(
        content: str,
        days_ago: float,
        *,
        emotion: str = "neutral",
        secondary: list[str] | None = None,
        intensity: float = 0.5,
        valence: float = 0.0,
        arousal: float = 0.5,
        importance: int = 3,
    ) -> Memory:
        now = datetime.now(timezone.utc)
        secondary_emotions = [Emotion(name) for name in (secondary or [])]
        return Memory(
            id=f"mem_{abs(hash((content, days_ago, emotion))) % 999999}",
            content=content,
            timestamp=(now - timedelta(days=days_ago)).isoformat(),
            importance=importance,
            emotional_trace=EmotionalTrace(
                primary=Emotion(emotion),
                secondary=secondary_emotions,
                intensity=intensity,
                valence=valence,
                arousal=arousal,
            ),
        )

    def test_valence_arousal_to_impression_mapping(self) -> None:
        assert (
            server_mod._valence_arousal_to_impression(0.6, 0.8)
            == "an energetic, fulfilling month"
        )
        assert (
            server_mod._valence_arousal_to_impression(0.6, 0.2)
            == "a quietly content month"
        )
        assert (
            server_mod._valence_arousal_to_impression(-0.6, 0.8)
            == "a turbulent, unsettled month"
        )
        assert (
            server_mod._valence_arousal_to_impression(-0.6, 0.2)
            == "a heavy, draining month"
        )
        assert (
            server_mod._valence_arousal_to_impression(0.0, 0.1)
            == "a numb, uneventful month"
        )
        assert (
            server_mod._valence_arousal_to_impression(0.1, 0.8)
            == "a month of mixed feelings"
        )

    @pytest.mark.asyncio
    async def test_emotion_trend_empty_history(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_list_recent(*_args: Any, **_kwargs: Any) -> list[Memory]:
            return []

        monkeypatch.setattr(memory, "list_recent", fake_list_recent)
        result = await _call(
            "emotion_trend", {}, config, memory, desire, episodes, consolidation
        )
        assert "No emotional history yet." in result
        assert "---" in result

    @pytest.mark.asyncio
    async def test_emotion_trend_recent_only_with_five_memories(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        memories = [
            self._mem(
                f"recent {i}",
                days_ago=float(i) * 0.4,
                emotion="curious",
                secondary=["anxious"] if i % 2 == 0 else [],
                intensity=0.5 + (i * 0.05),
                valence=0.2,
                arousal=0.6,
            )
            for i in range(5)
        ]

        async def fake_list_recent(*_args: Any, **_kwargs: Any) -> list[Memory]:
            return memories

        monkeypatch.setattr(memory, "list_recent", fake_list_recent)
        result = await _call(
            "emotion_trend", {}, config, memory, desire, episodes, consolidation
        )
        assert "Recent (past 3 days):" in result
        assert "This week:" not in result
        assert "This month (impressionistic):" not in result

    @pytest.mark.asyncio
    async def test_emotion_trend_full_layers_and_month_signals(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        memories: list[Memory] = []
        # Older month: anxious/frustrated cluster (should become fading)
        for i in range(20):
            memories.append(
                self._mem(
                    f"Peak frustration memory {i}" if i == 5 else f"old anxious {i}",
                    days_ago=22 + i * 0.35,
                    emotion="anxious" if i % 2 == 0 else "frustrated",
                    secondary=["melancholy"],
                    intensity=0.98 if i == 5 else 0.65,
                    valence=-0.7,
                    arousal=0.8,
                )
            )
        # Week: mostly curious/contentment, no anxious to allow fading on anxious cluster
        for i in range(10):
            memories.append(
                self._mem(
                    f"week curious {i}",
                    days_ago=1.5 + i * 0.4,
                    emotion="curious" if i < 7 else "contentment",
                    secondary=["contentment"] if i < 7 else ["curious"],
                    intensity=0.4 + i * 0.03,
                    valence=0.4,
                    arousal=0.45,
                )
            )
        # Recent end memory (latest)
        memories.append(
            self._mem(
                "End calm memory",
                days_ago=0.1,
                emotion="contentment",
                secondary=["curious"],
                intensity=0.55,
                valence=0.5,
                arousal=0.2,
            )
        )
        # Ensure sorted descending as MemoryStore.list_recent would do
        memories.sort(key=lambda m: m.timestamp, reverse=True)

        async def fake_list_recent(*_args: Any, **_kwargs: Any) -> list[Memory]:
            return memories

        monkeypatch.setattr(memory, "list_recent", fake_list_recent)
        old_cluster_timestamps = {
            m.timestamp
            for m in memories
            if m.emotional_trace.primary.value in {"anxious", "frustrated"}
        }
        monkeypatch.setattr(
            server_mod,
            "calculate_time_decay",
            lambda timestamp, **_kwargs: 0.4 if timestamp in old_cluster_timestamps else 0.9,
        )
        result = await _call(
            "emotion_trend", {}, config, memory, desire, episodes, consolidation
        )
        assert "Recent (past 3 days):" in result
        assert "This week:" in result
        assert "This month (impressionistic):" in result
        assert "[fading]" in result
        assert "Peak frustration memory" in result
        assert "End calm memory" in result


class TestToolLoggingPrivacy:
    def test_recall_sanitize_handles_two_line_private_entry(self) -> None:
        raw = (
            "2 of ~10 memories (showing top matches):\n"
            "1. [2d ago] secret private content should be masked\n"
            "   emotion: moved(0.9) | importance: 4 | score: 0.82 | private\n"
            "2. [3d ago] public content remains visible\n"
            "   emotion: curious | importance: 3 | score: 0.40\n"
        )
        sanitized = server_mod._sanitize_tool_output_for_logging("recall", None, raw)
        assert "[REDACTED_PRIVATE_MEMORY]" in sanitized
        assert "secret private content should be masked" not in sanitized
        assert "public content remains visible" in sanitized

    @pytest.mark.asyncio
    async def test_private_remember_masks_content_in_logs(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        secret = "super secret private payload"
        with caplog.at_level(logging.INFO, logger="ego_mcp.server"):
            await _call(
                "remember",
                {"content": secret, "private": True},
                config,
                memory,
                desire,
                episodes,
                consolidation,
            )

        invocation_records = [
            record
            for record in caplog.records
            if record.name == "ego_mcp.server"
            and record.getMessage() == "Tool invocation"
            and getattr(record, "tool_name", "") == "remember"
        ]
        assert invocation_records
        assert all(
            getattr(record, "tool_args", {}).get("content")
            == "[REDACTED_PRIVATE_MEMORY]"
            for record in invocation_records
        )
        assert all(secret not in str(getattr(record, "tool_args", {})) for record in invocation_records)

    @pytest.mark.asyncio
    async def test_recall_masks_private_content_in_logs(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        secret = "super secret private recall payload"
        await _call(
            "remember",
            {"content": secret, "private": True},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )

        with caplog.at_level(logging.INFO, logger="ego_mcp.server"):
            await _call(
                "recall",
                {"context": "super secret private recall payload", "n_results": 5},
                config,
                memory,
                desire,
                episodes,
                consolidation,
            )

        completion_records = [
            record
            for record in caplog.records
            if record.name == "ego_mcp.server"
            and record.getMessage() == "Tool execution completed"
            and getattr(record, "tool_name", "") == "recall"
        ]
        assert completion_records
        logged_output = str(getattr(completion_records[-1], "tool_output", ""))
        assert "[REDACTED_PRIVATE_MEMORY]" in logged_output
        assert secret not in logged_output


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

    @pytest.mark.asyncio
    async def test_resolve_question_via_update_self(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What should be resolved?")

        result = await _call(
            "update_self",
            {"field": "resolve_question", "value": qid},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert f"Resolved question {qid}" in result

    @pytest.mark.asyncio
    async def test_update_question_importance_via_update_self(
        self,
        config: EgoConfig,
        memory: MemoryStore,
        desire: DesireEngine,
        episodes: EpisodeStore,
        consolidation: ConsolidationEngine,
    ) -> None:
        store = SelfModelStore(config.data_dir / "self_model.json")
        qid = store.add_question("What deserves attention?", importance=2)

        result = await _call(
            "update_self",
            {"field": "question_importance", "value": {"id": qid, "importance": 5}},
            config,
            memory,
            desire,
            episodes,
            consolidation,
        )
        assert f"Updated question importance for {qid}" in result


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
