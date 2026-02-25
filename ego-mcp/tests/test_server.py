"""Focused tests for server-side tool dispatch behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import TextContent

import ego_mcp.server as server_mod
from ego_mcp.desire import DesireEngine


def _seed_high_desire(desire: DesireEngine, name: str) -> float:
    desire._state[name]["last_satisfied"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()
    return desire.compute_levels()[name]


@pytest.fixture
def desire(tmp_path: Path) -> DesireEngine:
    return DesireEngine(tmp_path / "desires.json")


@pytest.fixture(autouse=True)
def bind_minimal_server_state(
    monkeypatch: pytest.MonkeyPatch, desire: DesireEngine
) -> None:
    monkeypatch.setattr(server_mod, "_config", SimpleNamespace(companion_name="Master"))
    monkeypatch.setattr(server_mod, "_memory", object())
    monkeypatch.setattr(server_mod, "_desire", desire)
    monkeypatch.setattr(server_mod, "_episodes", object())
    monkeypatch.setattr(server_mod, "_consolidation", object())
    monkeypatch.setattr(server_mod, "_tool_log_context", lambda: {})


class TestImplicitSatisfactionFromServer:
    @pytest.mark.asyncio
    async def test_remember_lowers_expression_after_tool_call(
        self,
        desire: DesireEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        before = _seed_high_desire(desire, "expression")

        async def fake_handle_remember(_memory: object, _args: dict[str, object]) -> str:
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

        async def fake_handle_remember(_memory: object, _args: dict[str, object]) -> str:
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
