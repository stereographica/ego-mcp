"""Tests for _server_surface_core to improve coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import ego_mcp._server_surface_core as core_mod
from ego_mcp._server_surface_core import (
    _filter_desire_scaffold,
    _format_associated_from_map,
    _handle_consider_them,
    _handle_introspect,
    _handle_pause,
    _merge_topic_hints,
    _parse_episode_time,
    _sanitize_impulse_event,
)
from ego_mcp.config import EgoConfig
from ego_mcp.types import Emotion, Notion


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
    monkeypatch.setattr(core_mod, "_get_body_state_override", lambda: {"time_phase": "morning", "system_load": "low"})


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
