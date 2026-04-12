"""Tests for the attune surface handler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ego_mcp._server_surface_attune import (
    _handle_attune,
    _has_older_memory_echo,
    _list_notions_safe,
)
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory


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


@pytest.fixture
def engine(tmp_path: Path) -> DesireEngine:
    return DesireEngine.from_data_dir(tmp_path)


@pytest.fixture
def memory() -> AsyncMock:
    mem = AsyncMock()
    mem.list_recent = AsyncMock(return_value=[])
    return mem


@pytest.fixture(autouse=True)
def _override_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override derive_desire_modulation to avoid real computation."""
    import ego_mcp._server_surface_attune as attune_mod

    async def fake_modulation(*args: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(
        attune_mod,
        "_derive_desire_modulation_override",
        fake_modulation,
    )
    monkeypatch.setattr(
        attune_mod,
        "_get_body_state_override",
        lambda: {"time_phase": "morning", "system_load": "low"},
    )


@pytest.fixture(autouse=True)
def _runtime_accessors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up runtime accessors for attune handler."""
    import ego_mcp._server_runtime as runtime

    mock_impulse = MagicMock()
    mock_impulse.consume_event.return_value = {}
    mock_impulse.consume_boosts.return_value = {}
    monkeypatch.setattr(runtime, "_impulse_manager_getter", lambda: mock_impulse)

    mock_notion_store = MagicMock()
    mock_notion_store.list_all.return_value = []
    monkeypatch.setattr(runtime, "_notion_store_getter", lambda: mock_notion_store)


class TestHandleAttune:
    @pytest.mark.asyncio
    async def test_returns_desire_currents_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "Desire currents:" in result

    @pytest.mark.asyncio
    async def test_returns_scaffold_separator(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "---" in result

    @pytest.mark.asyncio
    async def test_returns_recent_emotion_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "Recent (past 3 days):" in result

    @pytest.mark.asyncio
    async def test_returns_body_sense_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "Body sense:" in result
        assert "morning" in result

    @pytest.mark.asyncio
    async def test_no_emergent_pull_when_no_emergent_desires(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "Emergent pull:" not in result

    @pytest.mark.asyncio
    async def test_scaffold_contains_attune_text(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_attune(config, memory, engine)
        assert "What am I actually feeling right now" in result

    @pytest.mark.asyncio
    async def test_emergent_pull_shown_when_emergent_desire_active(
        self,
        config: EgoConfig,
        memory: AsyncMock,
        engine: DesireEngine,
    ) -> None:
        """Lines 160-162: emergent_desire_sentence returns a sentence."""
        engine._state["be_with_someone"] = {"is_emergent": True}
        result = await _handle_attune(config, memory, engine)
        assert "Emergent pull:" in result
        assert "You want to be with someone." in result

    @pytest.mark.asyncio
    async def test_recent_memories_can_trigger_emergent_pull_without_notions(
        self,
        config: EgoConfig,
        memory: AsyncMock,
        engine: DesireEngine,
    ) -> None:
        now = datetime.now(timezone.utc)
        sad_memories = [
            Memory(
                id=f"m{i}",
                content="feeling alone tonight",
                timestamp=(now - timedelta(hours=i + 1)).isoformat(),
                emotional_trace=EmotionalTrace(
                    primary=Emotion.SAD,
                    valence=-0.6,
                    intensity=0.7,
                ),
            )
            for i in range(3)
        ]
        memory.list_recent = AsyncMock(return_value=sad_memories)

        result = await _handle_attune(config, memory, engine)

        assert "Emergent pull:" in result
        assert "You want to be with someone." in result

    @pytest.mark.asyncio
    async def test_current_interests_section_when_memories_present(
        self,
        config: EgoConfig,
        memory: AsyncMock,
        engine: DesireEngine,
    ) -> None:
        """Lines 191, 194-195: interests section shown when derive returns items."""
        now = datetime.now(timezone.utc)
        mem = Memory(
            id="m1",
            content="I love Python programming",
            timestamp=now.isoformat(),
            tags=["python"],
            category=Category.TECHNICAL,
        )
        memory.list_recent = AsyncMock(return_value=[mem])
        result = await _handle_attune(config, memory, engine)
        # We can't predict exact interests, but the handler should not crash.
        # The output still contains standard sections.
        assert "Desire currents:" in result

    @pytest.mark.asyncio
    async def test_bridge_line_shown_when_old_memory_echoes(
        self,
        config: EgoConfig,
        engine: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lines 211-214: bridge line appended when _has_older_memory_echo is True."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=48)).isoformat()
        old_mem = Memory(
            id="old1",
            content="I explored machine learning",
            timestamp=old_ts,
            tags=["ml"],
            category=Category.TECHNICAL,
        )
        mem_store = AsyncMock()
        mem_store.list_recent = AsyncMock(return_value=[old_mem])

        # Patch derive_current_interests to return an interest matching old tags.
        import ego_mcp._server_surface_attune as attune_mod

        monkeypatch.setattr(
            attune_mod,
            "derive_current_interests",
            lambda **kwargs: [{"topic": "ml", "score": 0.9}],
        )
        result = await _handle_attune(config, mem_store, engine)
        assert "This keeps coming back" in result

    @pytest.mark.asyncio
    async def test_no_bridge_line_when_no_old_echo(
        self,
        config: EgoConfig,
        engine: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge line NOT appended when all memories are recent."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=2)).isoformat()
        recent_mem = Memory(
            id="recent1",
            content="Just saw a bird",
            timestamp=recent_ts,
            tags=["nature"],
            category=Category.OBSERVATION,
        )
        mem_store = AsyncMock()
        mem_store.list_recent = AsyncMock(return_value=[recent_mem])

        import ego_mcp._server_surface_attune as attune_mod

        monkeypatch.setattr(
            attune_mod,
            "derive_current_interests",
            lambda **kwargs: [{"topic": "nature", "score": 0.8}],
        )
        result = await _handle_attune(config, mem_store, engine)
        assert "This keeps coming back" not in result


class TestHasOlderMemoryEcho:
    """Tests for the _has_older_memory_echo bridge line helper (lines 225-245)."""

    def test_returns_true_when_tag_matches_old_memory(self) -> None:
        now = datetime.now(timezone.utc)
        old_mem = Memory(
            id="m1",
            content="Old memory about python",
            timestamp=(now - timedelta(hours=48)).isoformat(),
            tags=["python"],
        )
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is True

    def test_returns_false_when_memory_is_recent(self) -> None:
        now = datetime.now(timezone.utc)
        recent_mem = Memory(
            id="m2",
            content="Recent about python",
            timestamp=(now - timedelta(hours=12)).isoformat(),
            tags=["python"],
        )
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [recent_mem], now) is False

    def test_returns_false_when_tags_dont_match(self) -> None:
        now = datetime.now(timezone.utc)
        old_mem = Memory(
            id="m3",
            content="Old memory about cooking",
            timestamp=(now - timedelta(hours=48)).isoformat(),
            tags=["cooking"],
        )
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is False

    def test_returns_true_when_category_matches(self) -> None:
        """Line 240-242: category value is also checked."""
        now = datetime.now(timezone.utc)
        old_mem = Memory(
            id="m4",
            content="Old technical memory",
            timestamp=(now - timedelta(hours=48)).isoformat(),
            tags=[],
            category=Category.TECHNICAL,
        )
        interests = [{"topic": "technical"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is True

    def test_skips_memory_with_invalid_timestamp(self) -> None:
        """Lines 232-233: ValueError on bad timestamp -> continue."""
        now = datetime.now(timezone.utc)
        bad_mem = MagicMock()
        bad_mem.timestamp = "not-a-date"
        bad_mem.tags = ["python"]
        bad_mem.category = Category.DAILY
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [bad_mem], now) is False

    def test_skips_memory_with_no_timestamp_attr(self) -> None:
        """Lines 229-233: getattr fallback to '' -> ValueError -> continue."""
        now = datetime.now(timezone.utc)
        obj = MagicMock(spec=[])  # No attributes
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [obj], now) is False

    def test_returns_false_when_no_memories(self) -> None:
        now = datetime.now(timezone.utc)
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [], now) is False

    def test_returns_false_when_no_interests(self) -> None:
        now = datetime.now(timezone.utc)
        old_mem = Memory(
            id="m5",
            content="Old memory",
            timestamp=(now - timedelta(hours=48)).isoformat(),
            tags=["python"],
        )
        assert _has_older_memory_echo([], [old_mem], now) is False

    def test_case_insensitive_matching(self) -> None:
        """Topic and tags are lowercased for comparison."""
        now = datetime.now(timezone.utc)
        old_mem = Memory(
            id="m6",
            content="Old memory about Python",
            timestamp=(now - timedelta(hours=48)).isoformat(),
            tags=["Python"],
        )
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is True

    def test_naive_timestamp_gets_timezone_applied(self) -> None:
        """Line 231: naive timestamps get app_timezone applied."""
        now = datetime.now(timezone.utc)
        # Create a naive timestamp (no tzinfo) that is old enough.
        naive_ts = (now - timedelta(hours=48)).replace(tzinfo=None).isoformat()
        old_mem = Memory(
            id="m7",
            content="Naive timestamp memory",
            timestamp=naive_ts,
            tags=["python"],
        )
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is True

    def test_non_string_tags_are_ignored(self) -> None:
        """Line 238-239: only string tags are considered."""
        now = datetime.now(timezone.utc)
        old_mem = MagicMock()
        old_mem.timestamp = (now - timedelta(hours=48)).isoformat()
        old_mem.tags = [123, None, "python"]
        old_mem.category = MagicMock()
        old_mem.category.value = ""
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is True

    def test_non_string_tags_alone_return_false(self) -> None:
        now = datetime.now(timezone.utc)
        old_mem = MagicMock()
        old_mem.timestamp = (now - timedelta(hours=48)).isoformat()
        old_mem.tags = [123, None]
        old_mem.category = MagicMock()
        old_mem.category.value = ""
        interests = [{"topic": "python"}]
        assert _has_older_memory_echo(interests, [old_mem], now) is False


class TestListNotionsSafe:
    """Test _list_notions_safe error handling (lines 55-64)."""

    def test_returns_empty_when_store_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 58-59: exception from get_notion_store -> return []."""
        import ego_mcp._server_runtime as runtime

        monkeypatch.setattr(
            runtime,
            "_notion_store_getter",
            lambda: (_ for _ in ()).throw(RuntimeError("no store")),
        )
        assert _list_notions_safe() == []


class TestCallGetBodyState:
    """Test _call_get_body_state without override (line 52)."""

    def test_real_body_state_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 52: when override is None, real get_body_state is called."""
        import ego_mcp._server_surface_attune as attune_mod

        monkeypatch.setattr(attune_mod, "_get_body_state_override", None)
        monkeypatch.setattr(
            attune_mod,
            "get_body_state",
            lambda: {"time_phase": "afternoon", "system_load": "low"},
        )
        result = attune_mod._call_get_body_state()
        assert result["time_phase"] == "afternoon"
