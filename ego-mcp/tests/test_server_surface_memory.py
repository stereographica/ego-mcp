"""Unit tests for remember surface handler."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ego_mcp._server_surface_memory import (
    EMOTION_DEFAULTS,
    _call_get_body_state,
    _call_relative_time,
    _float_or_default,
    _handle_remember,
    _normalize_tags,
    configure_overrides,
)
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.types import (
    Category,
    Emotion,
    EmotionalTrace,
    Memory,
    MemorySearchResult,
    Notion,
)


def test_emotion_defaults_cover_all_enum_members() -> None:
    expected = {emotion.value for emotion in Emotion}
    missing = expected - set(EMOTION_DEFAULTS)
    assert not missing


def test_emotion_defaults_include_contentment_and_melancholy_values() -> None:
    assert EMOTION_DEFAULTS["contentment"] == pytest.approx((0.5, 0.5, 0.2))
    assert EMOTION_DEFAULTS["melancholy"] == pytest.approx((0.5, -0.4, 0.2))


# --- Helpers and override tests ---


class TestCallRelativeTime:
    """Test _call_relative_time override path (line 90)."""

    def test_uses_real_function_when_no_override(self) -> None:
        configure_overrides(relative_time=None)
        # Should not crash; real implementation will return a string.
        result = _call_relative_time("2024-01-01T00:00:00Z")
        assert isinstance(result, str)

    def test_uses_override_when_set(self) -> None:
        def fake_rel(ts: str, now: object = None) -> str:
            return "mocked-time"

        configure_overrides(relative_time=fake_rel)
        result = _call_relative_time("2024-01-01T00:00:00Z")
        assert result == "mocked-time"
        configure_overrides(relative_time=None)


class TestCallGetBodyState:
    """Test _call_get_body_state override path (line 96)."""

    def test_uses_real_function_when_no_override(self) -> None:
        configure_overrides(get_body_state_fn=None)
        result = _call_get_body_state()
        assert isinstance(result, dict)

    def test_uses_override_when_set(self) -> None:
        configure_overrides(
            get_body_state_fn=lambda: {"time_phase": "test"}
        )
        result = _call_get_body_state()
        assert result["time_phase"] == "test"
        configure_overrides(get_body_state_fn=None)


class TestFloatOrDefault:
    """Test _float_or_default edge cases (line 110)."""

    def test_returns_float_from_int(self) -> None:
        assert _float_or_default(5, 0.0) == 5.0

    def test_returns_default_for_string(self) -> None:
        assert _float_or_default("bad", 0.5) == 0.5

    def test_returns_default_for_none(self) -> None:
        assert _float_or_default(None, 0.3) == 0.3


class TestNormalizeTags:
    """Test _normalize_tags edge cases (line 115)."""

    def test_string_input(self) -> None:
        assert _normalize_tags("hello") == ["hello"]

    def test_non_string_non_list_input(self) -> None:
        assert _normalize_tags(123) == []

    def test_deduplication(self) -> None:
        assert _normalize_tags(["a", "b", "a"]) == ["a", "b"]

    def test_strips_whitespace(self) -> None:
        assert _normalize_tags(["  foo  "]) == ["foo"]


# --- _handle_remember tests ---


@pytest.fixture
def remember_config(tmp_path: Path) -> EgoConfig:
    return EgoConfig(
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        api_key="test-key",
        data_dir=tmp_path,
        companion_name="TestUser",
        workspace_dir=None,
        timezone="UTC",
    )


@pytest.fixture
def mock_memory() -> AsyncMock:
    """A mock MemoryStore that returns a saved memory."""
    mem = AsyncMock()
    saved = Memory(
        id="test-mem-1",
        content="test content",
        timestamp="2024-01-01T12:00:00+00:00",
        emotional_trace=EmotionalTrace(
            primary=Emotion.HAPPY,
            intensity=0.6,
            valence=0.6,
            arousal=0.5,
        ),
        importance=3,
        category=Category.DAILY,
        tags=["test"],
        is_private=False,
    )
    mem.save_with_auto_link = AsyncMock(return_value=(saved, 0, [], None))
    mem.get_by_id = AsyncMock(return_value=saved)
    return mem


@pytest.fixture(autouse=True)
def _mock_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock runtime accessors for _handle_remember tests."""
    import ego_mcp._server_runtime as runtime
    import ego_mcp._server_surface_memory as mem_mod

    mock_notion_store = MagicMock()
    mock_notion_store.list_all.return_value = []
    mock_notion_store.search_by_tags.return_value = []
    monkeypatch.setattr(runtime, "_notion_store_getter", lambda: mock_notion_store)

    monkeypatch.setattr(runtime, "_workspace_sync_getter", lambda: None)

    mock_episodes = AsyncMock()
    monkeypatch.setattr(runtime, "_episodes_getter", lambda: mock_episodes)

    monkeypatch.setattr(
        mem_mod,
        "_call_relative_time",
        lambda ts, now=None: "moments ago",
    )
    monkeypatch.setattr(
        mem_mod,
        "_call_get_body_state",
        lambda: {"time_phase": "morning"},
    )

    # Patch find_resurfacing_memories to return empty
    monkeypatch.setattr(
        mem_mod,
        "find_resurfacing_memories",
        AsyncMock(return_value=[]),
    )
    # Patch _find_related_forgotten_questions to return empty
    monkeypatch.setattr(
        mem_mod,
        "_find_related_forgotten_questions",
        lambda memory, content: [],
    )
    # Patch update_notion_from_memory to return empty
    monkeypatch.setattr(
        mem_mod,
        "update_notion_from_memory",
        lambda store, mem: [],
    )


class TestHandleRememberDesireSatisfaction:
    """Test desire satisfaction integration (lines 296-326)."""

    @pytest.mark.asyncio
    async def test_explicit_satisfies_parameter(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
    ) -> None:
        """Lines 300-309: explicit satisfies list satisfies desires."""
        engine = DesireEngine.from_data_dir(remember_config.data_dir)
        # Get a known desire ID from the catalog.
        catalog = engine.require_valid_catalog()
        desire_ids = list(catalog.fixed_desires.keys())
        assert desire_ids, "Catalog must have at least one desire"
        target_desire = desire_ids[0]

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "A moment of deep understanding",
                "emotion": "happy",
                "satisfies": [target_desire],
            },
            desire_engine=engine,
        )
        assert "Saved (" in result
        assert "Putting this into words eased something." in result

    @pytest.mark.asyncio
    async def test_explicit_satisfies_unknown_desire_logs_warning(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Lines 307-308: unknown desire ID in satisfies logs a warning."""
        engine = DesireEngine.from_data_dir(remember_config.data_dir)
        with caplog.at_level(logging.WARNING):
            result = await _handle_remember(
                remember_config,
                mock_memory,
                {
                    "content": "Something happened",
                    "emotion": "neutral",
                    "satisfies": ["nonexistent_desire_xyz"],
                },
                desire_engine=engine,
            )
        assert "Saved (" in result
        assert "Unknown desire in satisfies" in caplog.text
        assert "Putting this into words eased something." not in result

    @pytest.mark.asyncio
    async def test_failed_explicit_satisfies_falls_through_to_auto_inference(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When all explicit satisfies IDs are invalid, fall back to auto-inference."""
        engine = DesireEngine.from_data_dir(remember_config.data_dir)
        catalog = engine.require_valid_catalog()
        target_desire = next(iter(catalog.fixed_desires.keys()))

        import ego_mcp._server_surface_memory as mem_mod

        monkeypatch.setattr(
            mem_mod,
            "infer_desire_satisfaction",
            lambda content, valence, intensity, cat, fn, **kw: [(target_desire, 0.4)],
        )

        def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 64 for _ in texts]

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "A wonderful moment",
                "emotion": "happy",
                "satisfies": ["nonexistent_desire_xyz"],
            },
            desire_engine=engine,
            embed_fn=fake_embed,
        )
        assert "Saved (" in result
        # Explicit failed → fell through to auto-inference → success message
        assert "Something quieted" in result
        assert "Putting this into words eased something." not in result

    @pytest.mark.asyncio
    async def test_auto_infer_satisfaction_with_embed_fn(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 310-326: auto-infer desire satisfaction when embed_fn provided."""
        engine = DesireEngine.from_data_dir(remember_config.data_dir)
        catalog = engine.require_valid_catalog()
        desire_ids = list(catalog.fixed_desires.keys())
        assert desire_ids, "Catalog must have at least one desire"
        target_desire = desire_ids[0]

        import ego_mcp._server_surface_memory as mem_mod

        monkeypatch.setattr(
            mem_mod,
            "infer_desire_satisfaction",
            lambda content, valence, intensity, cat, fn, **kw: [(target_desire, 0.4)],
        )

        def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 64 for _ in texts]

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "A wonderful moment",
                "emotion": "happy",
            },
            desire_engine=engine,
            embed_fn=fake_embed,
        )
        assert "Saved (" in result
        assert "Something quieted" in result

    @pytest.mark.asyncio
    async def test_auto_infer_no_match_no_section(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When infer returns empty, no desire settling section."""
        engine = DesireEngine.from_data_dir(remember_config.data_dir)

        import ego_mcp._server_surface_memory as mem_mod

        monkeypatch.setattr(
            mem_mod,
            "infer_desire_satisfaction",
            lambda content, valence, intensity, cat, fn, **kw: [],
        )

        def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 64 for _ in texts]

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Nothing special", "emotion": "neutral"},
            desire_engine=engine,
            embed_fn=fake_embed,
        )
        assert "Something quieted" not in result
        assert "Putting this into words" not in result

    @pytest.mark.asyncio
    async def test_no_desire_engine_no_satisfaction_section(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
    ) -> None:
        """When desire_engine is None, no desire settling section."""
        result = await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Just a note", "emotion": "neutral"},
            desire_engine=None,
        )
        assert "Something quieted" not in result
        assert "Putting this into words" not in result


class TestHandleRememberWorkspaceSync:
    """Test workspace sync paths (lines 206-216)."""

    @pytest.mark.asyncio
    async def test_sync_daily_updated(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Line 214: daily_updated sync note."""
        import ego_mcp._server_runtime as runtime

        mock_sync = MagicMock()
        mock_sync.sync_memory.return_value = MagicMock(
            latest_monologue_updated=False,
            daily_updated=True,
        )
        monkeypatch.setattr(runtime, "_workspace_sync_getter", lambda: mock_sync)

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Synced daily", "emotion": "neutral"},
        )
        assert "Synced to workspace memory logs." in result

    @pytest.mark.asyncio
    async def test_sync_latest_monologue_updated(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Line 212: latest_monologue_updated sync note."""
        import ego_mcp._server_runtime as runtime

        mock_sync = MagicMock()
        mock_sync.sync_memory.return_value = MagicMock(
            latest_monologue_updated=True,
            daily_updated=True,
        )
        monkeypatch.setattr(runtime, "_workspace_sync_getter", lambda: mock_sync)

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Introspective moment", "emotion": "calm"},
        )
        assert "Synced latest introspection to workspace." in result

    @pytest.mark.asyncio
    async def test_sync_oserror_handled(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Lines 215-216: OSError from workspace sync is caught and logged."""
        import ego_mcp._server_runtime as runtime

        mock_sync = MagicMock()
        mock_sync.sync_memory.side_effect = OSError("disk full")
        monkeypatch.setattr(runtime, "_workspace_sync_getter", lambda: mock_sync)

        with caplog.at_level(logging.WARNING):
            result = await _handle_remember(
                remember_config,
                mock_memory,
                {"content": "Sync will fail", "emotion": "neutral"},
            )
        assert "Saved (" in result
        assert "Workspace sync failed" in caplog.text

    @pytest.mark.asyncio
    async def test_private_memory_skips_sync(
        self,
        remember_config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Line 208: private memories skip workspace sync."""
        import ego_mcp._server_runtime as runtime

        private_mem = Memory(
            id="priv-1",
            content="secret",
            timestamp="2024-01-01T12:00:00+00:00",
            is_private=True,
        )
        mem_store = AsyncMock()
        mem_store.save_with_auto_link = AsyncMock(
            return_value=(private_mem, 0, [], None)
        )

        mock_sync = MagicMock()
        monkeypatch.setattr(runtime, "_workspace_sync_getter", lambda: mock_sync)

        await _handle_remember(
            remember_config,
            mem_store,
            {"content": "secret", "emotion": "neutral", "private": True},
        )
        mock_sync.sync_memory.assert_not_called()


class TestHandleRememberNotionUpdates:
    """Test notion update output in remember context (lines 348-368)."""

    @pytest.mark.asyncio
    async def test_notion_reinforced_tracked(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 352-368: notion updates populate remember context."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        notion = Notion(
            id="n1",
            label="test pattern",
            confidence=0.8,
            tags=["test"],
        )
        mock_notion_store = MagicMock()
        mock_notion_store.list_all.return_value = []
        mock_notion_store.search_by_tags.return_value = []
        mock_notion_store.get_by_id.return_value = notion
        monkeypatch.setattr(
            runtime, "_notion_store_getter", lambda: mock_notion_store
        )

        monkeypatch.setattr(
            mem_mod,
            "update_notion_from_memory",
            lambda store, mem: [("n1", "reinforced")],
        )

        await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Reinforced a notion", "emotion": "happy", "tags": ["test"]},
        )

        from ego_mcp._server_surface_memory import pop_tool_context

        ctx = pop_tool_context("remember")
        assert ctx.get("notion_reinforced") == "n1"
        assert ctx.get("notion_confidence") == 0.8

    @pytest.mark.asyncio
    async def test_notion_weakened_tracked(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Notion weakened state is tracked in context."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        notion = Notion(
            id="n2",
            label="fragile pattern",
            confidence=0.3,
            tags=["test"],
        )
        mock_notion_store = MagicMock()
        mock_notion_store.list_all.return_value = []
        mock_notion_store.search_by_tags.return_value = []
        mock_notion_store.get_by_id.return_value = notion
        monkeypatch.setattr(
            runtime, "_notion_store_getter", lambda: mock_notion_store
        )

        monkeypatch.setattr(
            mem_mod,
            "update_notion_from_memory",
            lambda store, mem: [("n2", "weakened")],
        )

        await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Weakened notion", "emotion": "sad", "tags": ["test"]},
        )

        from ego_mcp._server_surface_memory import pop_tool_context

        ctx = pop_tool_context("remember")
        assert ctx.get("notion_weakened") == "n2"

    @pytest.mark.asyncio
    async def test_notion_dormant_tracked(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Notion dormant state is tracked in context."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        notion = Notion(
            id="n3",
            label="fading pattern",
            confidence=0.1,
            tags=["test"],
        )
        mock_notion_store = MagicMock()
        mock_notion_store.list_all.return_value = []
        mock_notion_store.search_by_tags.return_value = []
        mock_notion_store.get_by_id.return_value = notion
        monkeypatch.setattr(
            runtime, "_notion_store_getter", lambda: mock_notion_store
        )

        monkeypatch.setattr(
            mem_mod,
            "update_notion_from_memory",
            lambda store, mem: [("n3", "dormant")],
        )

        await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Dormant notion", "emotion": "neutral", "tags": ["test"]},
        )

        from ego_mcp._server_surface_memory import pop_tool_context

        ctx = pop_tool_context("remember")
        assert ctx.get("notion_dormant") == "n3"


class TestHandleRememberImportanceEdge:
    """Test importance clamping (lines 154-155)."""

    @pytest.mark.asyncio
    async def test_invalid_importance_falls_back_to_3(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
    ) -> None:
        """Line 154-155: TypeError/ValueError -> importance=3."""
        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "Bad importance",
                "emotion": "neutral",
                "importance": "not-a-number",
            },
        )
        assert "Saved (" in result


class TestHandleRememberDuplicate:
    """Test duplicate memory handling (lines 187-198)."""

    @pytest.mark.asyncio
    async def test_duplicate_returns_not_saved_message(
        self,
        remember_config: EgoConfig,
    ) -> None:
        """Line 187-198: when mem is None and duplicate_of exists."""
        dup_mem = Memory(
            id="existing-1",
            content="Already stored this thought",
            timestamp="2024-01-01T12:00:00+00:00",
        )
        dup_result = MemorySearchResult(memory=dup_mem, distance=0.05)
        mem_store = AsyncMock()
        mem_store.save_with_auto_link = AsyncMock(
            return_value=(None, 0, [], dup_result)
        )
        result = await _handle_remember(
            remember_config,
            mem_store,
            {"content": "Already stored this thought", "emotion": "neutral"},
        )
        assert "Not saved" in result
        assert "existing-1" in result

    @pytest.mark.asyncio
    async def test_none_memory_without_duplicate_raises(
        self,
        remember_config: EgoConfig,
    ) -> None:
        """Line 200-203: mem is None and no duplicate -> RuntimeError."""
        mem_store = AsyncMock()
        mem_store.save_with_auto_link = AsyncMock(
            return_value=(None, 0, [], None)
        )
        with pytest.raises(RuntimeError, match="no memory without duplicate"):
            await _handle_remember(
                remember_config,
                mem_store,
                {"content": "Broken save", "emotion": "neutral"},
            )


class TestHandleRememberSharedWith:
    """Test shared_with parsing (lines 251-261, 270, 273)."""

    @pytest.mark.asyncio
    async def test_shared_with_string(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 252-255: single string person."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        mock_episodes = AsyncMock()
        episode = MagicMock()
        episode.id = "ep-1"
        episode.memory_ids = ["test-mem-1"]
        mock_episodes.create = AsyncMock(return_value=episode)
        monkeypatch.setattr(runtime, "_episodes_getter", lambda: mock_episodes)

        mock_rel_store = MagicMock()
        monkeypatch.setattr(
            mem_mod,
            "_relationship_store",
            lambda config: mock_rel_store,
        )

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "A shared moment",
                "emotion": "happy",
                "shared_with": "Alice",
            },
        )
        assert "Shared episode created" in result
        assert "Alice" in result

    @pytest.mark.asyncio
    async def test_shared_with_list_with_non_string(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 257-261: list with mixed types filters non-strings."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        mock_episodes = AsyncMock()
        episode = MagicMock()
        episode.id = "ep-2"
        episode.memory_ids = ["test-mem-1"]
        mock_episodes.create = AsyncMock(return_value=episode)
        monkeypatch.setattr(runtime, "_episodes_getter", lambda: mock_episodes)

        mock_rel_store = MagicMock()
        monkeypatch.setattr(
            mem_mod,
            "_relationship_store",
            lambda config: mock_rel_store,
        )

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "Mixed shared_with",
                "emotion": "happy",
                "shared_with": ["Bob", 123, "", "  "],
            },
        )
        assert "Shared episode created" in result
        assert "Bob" in result

    @pytest.mark.asyncio
    async def test_related_memories_non_string_skipped(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 270, 273: non-string and empty related_memories are skipped."""
        import ego_mcp._server_runtime as runtime
        import ego_mcp._server_surface_memory as mem_mod

        mock_episodes = AsyncMock()
        episode = MagicMock()
        episode.id = "ep-3"
        episode.memory_ids = ["test-mem-1"]
        mock_episodes.create = AsyncMock(return_value=episode)
        monkeypatch.setattr(runtime, "_episodes_getter", lambda: mock_episodes)

        mock_rel_store = MagicMock()
        monkeypatch.setattr(
            mem_mod,
            "_relationship_store",
            lambda config: mock_rel_store,
        )

        result = await _handle_remember(
            remember_config,
            mock_memory,
            {
                "content": "With invalid related",
                "emotion": "happy",
                "shared_with": "Carol",
                "related_memories": [123, "", "  ", None],
            },
        )
        assert "Shared episode created" in result

    @pytest.mark.asyncio
    async def test_episode_creation_failure_logged(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Lines 293-294: episode creation exception is caught and logged."""
        import ego_mcp._server_runtime as runtime

        mock_episodes = AsyncMock()
        mock_episodes.create = AsyncMock(side_effect=RuntimeError("episode fail"))
        monkeypatch.setattr(runtime, "_episodes_getter", lambda: mock_episodes)

        with caplog.at_level(logging.WARNING):
            result = await _handle_remember(
                remember_config,
                mock_memory,
                {
                    "content": "Episode will fail",
                    "emotion": "neutral",
                    "shared_with": "Dan",
                },
            )
        assert "Saved (" in result
        assert "Shared episode creation failed" in caplog.text


class TestHandleRememberResurfaced:
    """Test resurfaced memory context (line 348)."""

    @pytest.mark.asyncio
    async def test_resurfaced_memory_id_in_context(
        self,
        remember_config: EgoConfig,
        mock_memory: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Line 348: resurfaced memory IDs saved in tool context."""
        import ego_mcp._server_surface_memory as mem_mod

        resurfaced = MemorySearchResult(
            memory=Memory(id="resurf-1", content="Old echo", timestamp="2024-01-01T00:00:00Z"),
            distance=0.3,
            decay=0.2,
        )
        monkeypatch.setattr(
            mem_mod,
            "find_resurfacing_memories",
            AsyncMock(return_value=[resurfaced]),
        )

        await _handle_remember(
            remember_config,
            mock_memory,
            {"content": "Triggering an echo", "emotion": "happy"},
        )

        from ego_mcp._server_surface_memory import pop_tool_context

        ctx = pop_tool_context("remember")
        assert ctx.get("resurfaced_memory_id") == "resurf-1"
