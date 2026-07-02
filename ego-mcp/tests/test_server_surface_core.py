"""Tests for _server_surface_core to improve coverage."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import ego_mcp._server_surface_core as core_mod
from ego_mcp import timezone_utils
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_core import (
    _filter_desire_scaffold,
    _format_associated_from_map,
    _handle_consider_them,
    _handle_introspect,
    _handle_pause,
    _handle_wake_up,
    _merge_topic_hints,
    _parse_episode_time,
    _sanitize_impulse_event,
)
from ego_mcp.config import EgoConfig
from ego_mcp.relationship import RelationshipStore
from ego_mcp.self_model import SelfModelStore
from ego_mcp.types import Emotion, Memory, Notion


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
def _override_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_relationship_snapshot(
        _config: object, _memory: object, _person: str
    ) -> str:
        return "relationship snapshot"

    async def fake_derive(
        _memory: object, *_a: Any, **_kw: Any
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(core_mod, "_relationship_snapshot_override", fake_relationship_snapshot)
    monkeypatch.setattr(core_mod, "_derive_desire_modulation_override", fake_derive)
    monkeypatch.setattr(core_mod, "_get_body_state_override", lambda: {"time_phase": "morning"})


class TestSanitizeImpulseEvent:
    def test_empty_event_returns_false(self) -> None:
        result = _sanitize_impulse_event({}, visible_boosts={"a": 0.1})
        assert result == {"impulse_boost_triggered": False}

    def test_empty_boosts_returns_false(self) -> None:
        result = _sanitize_impulse_event({"x": 1}, visible_boosts={})
        assert result == {"impulse_boost_triggered": False}

    def test_visible_boosted_desire_returned(self) -> None:
        result = _sanitize_impulse_event(
            {"impulse_boosted_desire": "curiosity", "impulse_boost_triggered": True},
            visible_boosts={"curiosity": 0.15},
        )
        assert result["impulse_boosted_desire"] == "curiosity"
        assert result["impulse_boost_amount"] == 0.15

    def test_filtered_desires_list(self) -> None:
        result = _sanitize_impulse_event(
            {"impulse_boosted_desires": "curiosity,expression"},
            visible_boosts={"curiosity": 0.1, "expression": 0.2},
        )
        assert result.get("impulse_event_count") == 2
        assert "curiosity" in str(result.get("impulse_boosted_desires", ""))

    def test_invisible_desire_excluded(self) -> None:
        result = _sanitize_impulse_event(
            {"impulse_boosted_desires": "hidden_one"},
            visible_boosts={"curiosity": 0.1},
        )
        assert result == {"impulse_boost_triggered": False}

    def test_fallback_to_first_filtered_desire(self) -> None:
        result = _sanitize_impulse_event(
            {"impulse_boosted_desires": "curiosity"},
            visible_boosts={"curiosity": 0.1},
        )
        assert result["impulse_boosted_desire"] == "curiosity"


class TestParseEpisodeTime:
    def test_valid_iso_timestamp(self) -> None:
        result = _parse_episode_time("2026-01-15T10:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_naive_timestamp_gets_timezone(self) -> None:
        result = _parse_episode_time("2026-01-15T10:00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_invalid_returns_none(self) -> None:
        assert _parse_episode_time("not-a-date") is None

    def test_empty_returns_none(self) -> None:
        assert _parse_episode_time("") is None


class TestMergeTopicHints:
    def test_merge_deduplicates(self) -> None:
        result = _merge_topic_hints(["a", "b"], ["b", "c"])
        assert result == ["a", "b", "c"]

    def test_empty_inputs(self) -> None:
        assert _merge_topic_hints([], []) == []


class TestFormatAssociatedFromMap:
    def test_with_related_notions(self) -> None:
        n1 = Notion(id="n1", label="A", emotion_tone=Emotion.CURIOUS, confidence=0.8, related_notion_ids=["n2"])
        n2 = Notion(id="n2", label="B", emotion_tone=Emotion.CURIOUS, confidence=0.7)
        result = _format_associated_from_map(n1, {"n1": n1, "n2": n2}, limit=2)
        assert '"B"' in result

    def test_no_related_returns_empty(self) -> None:
        n1 = Notion(id="n1", label="A", emotion_tone=Emotion.CURIOUS, confidence=0.8)
        result = _format_associated_from_map(n1, {"n1": n1}, limit=2)
        assert result == ""


class TestFilterDesireScaffold:
    def test_none_desire_returns_scaffold_unchanged(self) -> None:
        scaffold = "some text"
        assert _filter_desire_scaffold(scaffold, None) == scaffold

    def test_with_predictability_keeps_scaffold(self) -> None:
        from ego_mcp.desire import DesireEngine

        engine = MagicMock(spec=DesireEngine)
        engine.catalog.fixed_desires = {"predictability": MagicMock()}
        result = _filter_desire_scaffold("scaffold", engine)
        assert result == "scaffold"


class TestHandlePause:
    def test_returns_scaffold_separator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)
        result = _handle_pause()
        assert "---" in result
        assert "Self-check triggered." in result

    def test_includes_convictions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        conviction = Notion(
            id="n1", label="Honesty matters", emotion_tone=Emotion.CALM,
            confidence=0.95, reinforcement_count=10,
        )
        mock_store = MagicMock()
        mock_store.list_all.return_value = [conviction]
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)
        monkeypatch.setattr(core_mod, "is_conviction", lambda n: True)
        result = _handle_pause()
        assert "Honesty matters" in result
        assert "Your convictions:" in result


class TestHandleConsiderThem:
    @pytest.mark.asyncio
    async def test_sensitive_topics_shown(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ego_mcp.relationship import RelationshipStore

        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update("TestUser", {"sensitive_topics": ["family"]})

        async def fake_tendency(_mem: object, _person: str) -> tuple[str, str, list[str], list[str]]:
            return "frequent", "warm", [], ["health"]

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {})
        assert "sensitive_topics=" in result

    @pytest.mark.asyncio
    async def test_emotional_baseline_shown(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ego_mcp.relationship import RelationshipStore

        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update("TestUser", {"emotional_baseline": {"warm": 0.7, "curious": 0.3}})

        async def fake_tendency(_mem: object, _person: str) -> tuple[str, str, list[str], list[str]]:
            return "occasional", "neutral", [], []

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {})
        assert "baseline_tone=warm" in result

    @pytest.mark.asyncio
    async def test_person_notions_shown(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_tendency(_mem: object, _person: str) -> tuple[str, str, list[str], list[str]]:
            return "frequent", "warm", [], []

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        notion = Notion(
            id="n1", label="Always curious", emotion_tone=Emotion.CURIOUS,
            confidence=0.8, person_id="TestUser",
        )
        mock_store = MagicMock()
        mock_store.list_all.return_value = [notion]
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {})
        assert "Always curious" in result
        assert "Impressions of TestUser:" in result

    @pytest.mark.asyncio
    async def test_quiet_absence_frame_is_shown_without_counting_interaction(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update("TestUser", {"name": "TestUser"})
        store.add_interaction("TestUser", "2026-06-18T12:00:00+00:00", "calm")
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])
        result = await _handle_consider_them(config, mem, {})

        assert "last shared moment about two weeks ago" in result
        assert (
            "It's been about about two weeks since you last shared something "
            "with TestUser."
            in result
        )
        assert (
            "They may have changed in that time. What would you want to ask first?"
            in result
        )
        reloaded = RelationshipStore(config.data_dir / "relationships" / "models.json")
        assert reloaded.get("TestUser").total_interactions == 1

    @pytest.mark.asyncio
    async def test_summary_words_relationship_numbers_and_preserves_topic_fields(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update(
            "TestUser",
            {
                "trust_level": 0.85,
                "first_interaction": "2026-01-01T12:00:00+00:00",
                "last_interaction": "2026-06-11T12:00:00+00:00",
                "total_interactions": 42,
                "shared_episode_ids": ["ep-a", "ep-b", "ep-c", "ep-d"],
                "emotional_baseline": {"warm": 0.7},
            },
        )

        async def fake_tendency(
            _mem: object,
            _person: str,
        ) -> tuple[str, str, list[str], list[str]]:
            return "they've come up once or twice this week", "curious", [
                "technical",
            ], ["health"]

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {})
        summary = result.splitlines()[0]

        assert summary == (
            "TestUser: the kind of trust you don't need to name; "
            "a long history together, many shared chapters, "
            "preferred_topics=technical, sensitive_topics=health, "
            "last shared moment about three weeks ago, baseline_tone=warm"
        )
        assert "trust=" not in summary
        assert "interactions=" not in summary
        assert "shared_episodes=" not in summary
        assert "last_interaction=" not in summary
        assert re.search(r"\d", summary) is None

    @pytest.mark.asyncio
    async def test_usual_absence_frame_is_not_shown(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.add_interaction("TestUser", "2026-06-25T12:00:00+00:00", "calm")
        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])
        result = await _handle_consider_them(config, mem, {})

        assert "They may have changed in that time" not in result
        reloaded = RelationshipStore(config.data_dir / "relationships" / "models.json")
        assert reloaded.get("TestUser").total_interactions == 1


class TestHandleIntrospect:
    @pytest.mark.asyncio
    async def test_week_month_layers_present(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {}

        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        result = await _handle_introspect(config, mem, cast(Any, FakeDesire()))
        assert "This week:" in result
        assert "This month" in result
        assert "Recent memories:" not in result

    @pytest.mark.asyncio
    async def test_desire_trend_section(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {"curiosity": 0.5, "expression": 0.5}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {"curiosity": 0.8, "expression": 0.2}

        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        result = await _handle_introspect(config, mem, cast(Any, FakeDesire()))
        assert "Desire trend:" in result
        assert "curiosity: rising" in result
        assert "expression: settling" in result

    @pytest.mark.asyncio
    async def test_new_question_hint_shown_without_questions(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {}

        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        result = await _handle_introspect(config, mem, cast(Any, FakeDesire()))

        assert (
            'No unresolved questions yet.\nTo hold a new question: update_self(field="new_question", '
            'value={"question": ..., "importance": 1-5})'
            in result
        )

    @pytest.mark.asyncio
    async def test_new_question_hint_shown_with_resolve_hint(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        SelfModelStore(config.data_dir / "self_model.json").add_question(
            "What remains open?", importance=5
        )
        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {}

        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        result = await _handle_introspect(config, mem, cast(Any, FakeDesire()))

        assert 'update_self(field="resolve_question", value="<question_id>")' in result
        assert 'update_self(field="new_question", value={"question": ...' in result


class _FakeWakeMemory:
    def __init__(self, anticipations: list[Memory]) -> None:
        self.anticipations = anticipations
        self.marked: list[str] = []

    async def list_recent(
        self,
        n: int = 30,
        category_filter: str | None = None,
    ) -> list[Memory]:
        del n, category_filter
        return []

    def list_anticipations(self, include_surfaced: bool = False) -> list[Memory]:
        if include_surfaced:
            return list(self.anticipations)
        return [
            memory
            for memory in self.anticipations
            if not memory.anticipation_surfaced
        ]

    def mark_anticipation_surfaced(self, memory_id: str) -> None:
        self.marked.append(memory_id)
        for memory in self.anticipations:
            if memory.id == memory_id:
                memory.anticipation_surfaced = True


class _FakeWakeDesire:
    _state: dict[str, Any] = {}

    @property
    def ema_levels(self) -> dict[str, float]:
        return {}

    def expire_emergent_desires(self) -> list[str]:
        return []

    def compute_levels_with_modulation(self, **_kwargs: Any) -> dict[str, float]:
        return {}

    def emergent_directions(self) -> dict[str, str]:
        return {}


class TestHandleWakeUpAnticipation:
    @pytest.mark.asyncio
    async def test_arrived_surfaces_oldest_once(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reset_tool_metadata()
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        older = Memory(
            id="old-arrived",
            content="the older appointment",
            anticipated_at=(now - timedelta(days=2)).isoformat(),
        )
        newer = Memory(
            id="new-arrived",
            content="the newer appointment",
            anticipated_at=(now - timedelta(days=1)).isoformat(),
        )
        memory = _FakeWakeMemory([newer, older])

        first = await _handle_wake_up(config, cast(Any, memory), cast(Any, _FakeWakeDesire()))
        second = await _handle_wake_up(config, cast(Any, memory), cast(Any, _FakeWakeDesire()))
        third = await _handle_wake_up(config, cast(Any, memory), cast(Any, _FakeWakeDesire()))

        assert 'That time came: "the older appointment". How was it, actually?' in first
        assert 'That time came: "the newer appointment". How was it, actually?' in second
        assert "That time came:" not in third
        assert memory.marked == ["old-arrived", "new-arrived"]

    @pytest.mark.asyncio
    async def test_imminent_beats_approaching_without_thinning(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reset_tool_metadata()
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        monkeypatch.setattr("ego_mcp._server_surface_core.random.random", lambda: 0.99)
        approaching = Memory(
            id="approaching",
            content="the later thing",
            anticipated_at=(now + timedelta(days=10)).isoformat(),
            importance=5,
        )
        imminent = Memory(
            id="imminent",
            content="the soon thing",
            anticipated_at=(now + timedelta(hours=36)).isoformat(),
            importance=1,
        )
        memory = _FakeWakeMemory([approaching, imminent])

        result = await _handle_wake_up(config, cast(Any, memory), cast(Any, _FakeWakeDesire()))

        assert 'Approaching: "the soon thing" (in a day or two).' in result
        assert "the later thing" not in result
        assert get_tool_metadata().get("anticipation_presented") == "imminent"

    @pytest.mark.asyncio
    async def test_private_anticipation_displays_without_telemetry(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reset_tool_metadata()
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        private = Memory(
            id="private-imminent",
            content="private future note",
            anticipated_at=(now + timedelta(hours=2)).isoformat(),
            is_private=True,
        )
        memory = _FakeWakeMemory([private])

        result = await _handle_wake_up(config, cast(Any, memory), cast(Any, _FakeWakeDesire()))

        assert 'Approaching: "private future note" (within a day).' in result
        assert "anticipation_presented" not in get_tool_metadata()


class TestHandleWakeUpReunion:
    @pytest.mark.asyncio
    async def test_reunion_note_is_shown_once_and_marked(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update("alice", {"name": "Alice"})
        store.set_reunion_note(
            "alice",
            gap_days=21.0,
            noted_at=now.isoformat(),
        )
        memory = _FakeWakeMemory([])

        first = await _handle_wake_up(
            config,
            cast(Any, memory),
            cast(Any, _FakeWakeDesire()),
        )
        second = await _handle_wake_up(
            config,
            cast(Any, memory),
            cast(Any, _FakeWakeDesire()),
        )

        assert (
            "Reunited with Alice recently — the first shared moment in "
            "about about three weeks."
            in first
        )
        assert "Reunited with Alice recently" not in second
        reloaded = RelationshipStore(config.data_dir / "relationships" / "models.json")
        assert reloaded.raw("alice")["reunion_note"]["wake_up_shown"] is True

    @pytest.mark.asyncio
    async def test_multiple_reunion_notes_are_shown_latest_first_one_per_wake(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(timezone_utils, "now", lambda: now)
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update("alice", {"name": "Alice"})
        store.update("bob", {"name": "Bob"})
        store.set_reunion_note(
            "alice",
            gap_days=14.0,
            noted_at=(now - timedelta(hours=1)).isoformat(),
        )
        store.set_reunion_note(
            "bob",
            gap_days=31.0,
            noted_at=now.isoformat(),
        )
        memory = _FakeWakeMemory([])

        first = await _handle_wake_up(
            config,
            cast(Any, memory),
            cast(Any, _FakeWakeDesire()),
        )
        second = await _handle_wake_up(
            config,
            cast(Any, memory),
            cast(Any, _FakeWakeDesire()),
        )

        assert "Reunited with Bob recently" in first
        assert "Reunited with Alice recently" not in first
        assert "Reunited with Alice recently" in second


class TestConsiderThemPersonTelemetry:
    """Task 3-3: consider_them telemetry person_id."""

    @pytest.fixture
    def config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EgoConfig:
        monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
        monkeypatch.setenv("EGO_MCP_COMPANION_NAME", "TestUser")
        return EgoConfig.from_env()

    @pytest.mark.asyncio
    async def test_person_id_recorded(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """person_id is recorded in telemetry when specified."""

        async def fake_tendency(_mem: object, _person: str) -> tuple[str, str, list[str], list[str]]:
            return "occasional", "neutral", [], []

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {"person": "alice"})
        assert result is not None

        meta = get_tool_metadata()
        assert meta is not None
        assert meta.get("person_id") == "alice"

    @pytest.mark.asyncio
    async def test_trust_level_for_non_companion(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """trust_level is recorded for non-companion persons."""

        async def fake_tendency(_mem: object, _person: str) -> tuple[str, str, list[str], list[str]]:
            return "occasional", "neutral", [], []

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {"person": "alice"})
        assert result is not None

        meta = get_tool_metadata()
        assert meta is not None
        assert meta.get("trust_level") is not None

    @pytest.mark.asyncio
    async def test_numeric_relationship_metadata_is_preserved(
        self,
        config: EgoConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Relationship wording does not change telemetry fields."""
        reset_tool_metadata()
        store = RelationshipStore(config.data_dir / "relationships" / "models.json")
        store.update(
            "alice",
            {
                "trust_level": 0.74,
                "total_interactions": 8,
                "shared_episode_ids": ["a", "b", "c", "d"],
            },
        )

        async def fake_tendency(
            _mem: object,
            _person: str,
        ) -> tuple[str, str, list[str], list[str]]:
            return "occasional", "neutral", [], []

        monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
        mem = AsyncMock()
        result = await _handle_consider_them(config, mem, {"person": "alice"})
        assert result is not None

        meta = get_tool_metadata()
        assert meta["person_id"] == "alice"
        assert meta["trust_level"] == 0.74
        assert meta["total_interactions"] == 8
        assert meta["shared_episodes_count"] == 4


class TestActivePersonsTelemetry:
    """Task 3-4: active_person_ids telemetry for wake_up/introspect/attune."""

    @pytest.fixture
    def config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EgoConfig:
        monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
        monkeypatch.setenv("EGO_MCP_COMPANION_NAME", "TestUser")
        return EgoConfig.from_env()

    @pytest.mark.asyncio
    async def test_active_person_ids_in_wake_up(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """wake_up records active_person_ids in telemetry."""

        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        # Mock _format_active_persons to return a non-empty string
        import ego_mcp._server_surface_core as core_mod
        monkeypatch.setattr(
            core_mod,
            "_format_active_persons",
            lambda *a, **k: "\nAlice and Bob surfaced on their own.",
        )
        monkeypatch.setattr(
            core_mod,
            "_get_active_person_ids",
            lambda *a, **k: ["alice", "bob"],
        )

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {}

            def expire_emergent_desires(self) -> None:
                pass

            def emergent_directions(self) -> dict[str, str]:
                return {}

            _state: dict[str, Any] = {}

        result = await _handle_wake_up(config, mem, cast(Any, FakeDesire()))
        assert result is not None

        meta = get_tool_metadata()
        assert meta is not None
        assert meta.get("active_person_ids") is not None
        import json as json_mod
        parsed = json_mod.loads(str(meta["active_person_ids"]))
        assert "alice" in parsed
        assert "bob" in parsed

    @pytest.mark.asyncio
    async def test_active_person_ids_in_introspect(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """introspect records active_person_ids in telemetry."""

        mem = AsyncMock()
        mem.list_recent = AsyncMock(return_value=[])

        import ego_mcp._server_surface_core as core_mod
        monkeypatch.setattr(
            core_mod,
            "_format_active_persons",
            lambda *a, **k: "\nAlice surfaced on their own.",
        )
        monkeypatch.setattr(
            core_mod,
            "_get_active_person_ids",
            lambda *a, **k: ["alice"],
        )

        class FakeDesire:
            @property
            def ema_levels(self) -> dict[str, float]:
                return {}

            def compute_levels_with_modulation(self, **kw: Any) -> dict[str, float]:
                return {}

        mock_store = MagicMock()
        mock_store.list_all.return_value = []
        monkeypatch.setattr(core_mod, "get_notion_store", lambda: mock_store)

        result = await _handle_introspect(config, mem, cast(Any, FakeDesire()))
        assert result is not None

        meta = get_tool_metadata()
        assert meta is not None
        assert meta.get("active_person_ids") is not None
        import json as json_mod
        parsed = json_mod.loads(str(meta["active_person_ids"]))
        assert "alice" in parsed
