"""Tests for the rewritten wake_up handler."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ego_mcp._server_surface_core import (
    _detect_weakened_notions,
    _handle_wake_up,
)
from ego_mcp.config import EgoConfig
from ego_mcp.desire import DesireEngine
from ego_mcp.types import Notion


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
    """Override callables used by wake_up to avoid real computation."""
    import ego_mcp._server_surface_core as core_mod

    async def fake_relationship(config: Any, memory: Any, name: str) -> str:
        return f"Relationship with {name}: trust is steady."

    async def fake_modulation(*args: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(
        core_mod,
        "_relationship_snapshot_override",
        fake_relationship,
    )
    monkeypatch.setattr(
        core_mod,
        "_derive_desire_modulation_override",
        fake_modulation,
    )
    monkeypatch.setattr(
        core_mod,
        "_get_body_state_override",
        lambda: {"time_phase": "morning"},
    )


@pytest.fixture(autouse=True)
def _runtime_accessors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up runtime accessors for wake_up handler."""
    import ego_mcp._server_runtime as runtime
    import ego_mcp._server_surface_core as core_mod

    mock_impulse = MagicMock()
    mock_impulse.consume_event.return_value = {}
    mock_impulse.consume_boosts.return_value = {}
    mock_impulse.register_proust_event.return_value = {}
    monkeypatch.setattr(runtime, "_impulse_manager_getter", lambda: mock_impulse)

    mock_notion_store = MagicMock()
    mock_notion_store.list_all.return_value = []
    monkeypatch.setattr(runtime, "_notion_store_getter", lambda: mock_notion_store)

    monkeypatch.setattr(core_mod, "get_workspace_sync", lambda: None)


class TestHandleWakeUp:
    @pytest.mark.asyncio
    async def test_returns_desire_currents_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        assert "Desire currents:" in result

    @pytest.mark.asyncio
    async def test_returns_relationship_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        assert "Relationship with TestUser" in result

    @pytest.mark.asyncio
    async def test_returns_scaffold_separator(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        assert "---" in result

    @pytest.mark.asyncio
    async def test_contains_last_introspection_section(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        # Either shows an introspection or "No introspection yet."
        assert "introspection" in result.lower()

    @pytest.mark.asyncio
    async def test_contains_companion_name_in_scaffold(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        assert "TestUser" in result

    @pytest.mark.asyncio
    async def test_no_embers_when_no_data(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        result = await _handle_wake_up(config, memory, engine)
        # With no memories, embers section should not appear
        assert "Embers:" not in result

    @pytest.mark.asyncio
    async def test_stale_emergent_desire_not_rendered(
        self, config: EgoConfig, memory: AsyncMock, engine: DesireEngine
    ) -> None:
        engine._state["be_with_someone"] = {
            "is_emergent": True,
            "created": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            "last_satisfied": "",
            "satisfaction_quality": 0.5,
            "boost": 0.0,
            "satisfaction_hours": 24.0,
        }

        result = await _handle_wake_up(config, memory, engine)

        assert "...be with someone" not in result
        assert "You want to be with someone." not in result


class TestDetectWeakenedNotions:
    def test_no_previous_snapshot_returns_empty(self, tmp_path: Path) -> None:
        snapshot = tmp_path / "snap.json"
        notions = [Notion(id="n1", confidence=0.3)]
        result = _detect_weakened_notions(notions, snapshot)
        assert result == []

    def test_detects_confidence_drop(self, tmp_path: Path) -> None:
        snapshot = tmp_path / "snap.json"
        snapshot.write_text(json.dumps({"n1": 0.8, "n2": 0.5}))
        notions = [
            Notion(id="n1", confidence=0.6),  # dropped 0.2 >= 0.1
            Notion(id="n2", confidence=0.45),  # dropped 0.05 < 0.1
        ]
        result = _detect_weakened_notions(notions, snapshot)
        assert len(result) == 1
        assert result[0].id == "n1"

    def test_saves_current_snapshot(self, tmp_path: Path) -> None:
        snapshot = tmp_path / "snap.json"
        notions = [Notion(id="n1", confidence=0.7)]
        _detect_weakened_notions(notions, snapshot)
        saved = json.loads(snapshot.read_text())
        assert saved == {"n1": 0.7}

    def test_corrupted_snapshot_treated_as_empty(self, tmp_path: Path) -> None:
        snapshot = tmp_path / "snap.json"
        snapshot.write_text("not json")
        notions = [Notion(id="n1", confidence=0.3)]
        result = _detect_weakened_notions(notions, snapshot)
        assert result == []

    def test_notion_removed_since_last_snapshot(self, tmp_path: Path) -> None:
        snapshot = tmp_path / "snap.json"
        snapshot.write_text(json.dumps({"n1": 0.8, "n2": 0.9}))
        # n2 no longer present
        notions = [Notion(id="n1", confidence=0.8)]
        result = _detect_weakened_notions(notions, snapshot)
        assert result == []
        saved = json.loads(snapshot.read_text())
        assert "n2" not in saved
