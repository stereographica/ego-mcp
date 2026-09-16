"""consider_them presentation of the derived layer (P2 S2 affect trajectory)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import ego_mcp._server_surface_core as core_mod
from ego_mcp import timezone_utils
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_core import _handle_consider_them
from ego_mcp.config import EgoConfig
from ego_mcp.derived.contract import DerivedFile, write_lens_file
from ego_mcp.relationship import RelationshipStore
from ego_mcp.self_model import SelfModelStore

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)

BRIGHTER = (
    "The shared moments of the last while lean brighter than the ones before."
)
DARKER = "The shared moments of the last while lean darker than the ones before."
LIVELIER = "The shared moments of the last while run livelier than before."
QUIETER = "The shared moments of the last while run quieter than before."


def write_items(
    data_dir: Path,
    items: list[dict[str, Any]],
    *,
    now: datetime = NOW,
    ttl_hours: float = 168.0,
) -> None:
    """Write the affect lens file the way the nightly batch would."""
    write_lens_file(
        data_dir,
        DerivedFile(
            lens="affect",
            generated_at=now.isoformat(),
            valid_until=(now + timedelta(hours=ttl_hours)).isoformat(),
            source={},
            items=items,
        ),
    )


def affect_item(
    *,
    person_id: str = "alice",
    valence: str = "steady",
    arousal: str = "steady",
    dv: float = 0.0,
    da: float = 0.0,
) -> dict[str, Any]:
    return {
        "key": f"affect:{person_id}:2026-09-17",
        "person_id": person_id,
        "dv": dv,
        "da": da,
        "valence_direction": valence,
        "arousal_direction": arousal,
        "n_recent": 6,
        "n_prior": 9,
    }


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
def _surface_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_tendency(
        _memory: Any, _person: str
    ) -> tuple[str, str, list[str], list[str]]:
        return "a steady week of conversation", "warm", [], []

    monkeypatch.setattr(core_mod, "_summarize_conversation_tendency", fake_tendency)
    notion_store = MagicMock()
    notion_store.list_all.return_value = []
    monkeypatch.setattr(core_mod, "get_notion_store", lambda: notion_store)
    monkeypatch.setattr(timezone_utils, "now", lambda: NOW)
    reset_tool_metadata()


@pytest.fixture
def relationships(config: EgoConfig) -> RelationshipStore:
    store = RelationshipStore(config.data_dir / "relationships" / "models.json")
    store.update("alice", {"name": "Alice"})
    return store


async def run_consider_them(config: EgoConfig, person: str = "alice") -> str:
    memory = AsyncMock()
    memory.list_recent = AsyncMock(return_value=[])
    return await _handle_consider_them(
        config, cast(Any, memory), {"person": person}
    )


class TestAffectTrajectoryLine:
    @pytest.mark.asyncio
    async def test_brighter_is_verbatim(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(
            config.data_dir, [affect_item(valence="brighter", dv=0.31)]
        )

        result = await run_consider_them(config)

        assert BRIGHTER in result

    @pytest.mark.asyncio
    async def test_darker_is_verbatim(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(config.data_dir, [affect_item(valence="darker", dv=-0.4)])

        result = await run_consider_them(config)

        assert DARKER in result

    @pytest.mark.asyncio
    async def test_livelier_is_verbatim(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(config.data_dir, [affect_item(arousal="livelier", da=0.22)])

        result = await run_consider_them(config)

        assert LIVELIER in result

    @pytest.mark.asyncio
    async def test_quieter_is_verbatim(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(config.data_dir, [affect_item(arousal="quieter", da=-0.2)])

        result = await run_consider_them(config)

        assert QUIETER in result

    @pytest.mark.asyncio
    async def test_valence_wins_over_arousal(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(
            config.data_dir,
            [
                affect_item(
                    valence="brighter", arousal="livelier", dv=0.3, da=0.2
                )
            ],
        )

        result = await run_consider_them(config)

        assert BRIGHTER in result
        assert LIVELIER not in result

    @pytest.mark.asyncio
    async def test_both_steady_says_nothing(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(config.data_dir, [affect_item()])

        result = await run_consider_them(config)

        assert "The shared moments of the last while" not in result

    @pytest.mark.asyncio
    async def test_unknown_person_says_nothing(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(
            config.data_dir,
            [affect_item(person_id="bob", valence="darker", dv=-0.5)],
        )

        result = await run_consider_them(config)

        assert "The shared moments of the last while" not in result

    @pytest.mark.asyncio
    async def test_line_sits_after_absence_frame_and_before_held_together(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        relationships.add_interaction(
            "alice", (NOW - timedelta(days=21)).isoformat(), "calm"
        )
        SelfModelStore(config.data_dir / "self_model.json").add_question(
            "What did we leave unfinished?", importance=4, person_id="alice"
        )
        write_items(config.data_dir, [affect_item(valence="darker", dv=-0.5)])

        result = await run_consider_them(config)

        assert (
            result.index("What would you want to ask first?") < result.index(DARKER)
        )
        assert result.index(DARKER) < result.index("Held together with Alice:")

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_output_unchanged(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        baseline = await run_consider_them(config)

        write_items(
            config.data_dir,
            [affect_item(valence="darker", dv=-0.5)],
            now=NOW - timedelta(days=30),
        )
        with_stale = await run_consider_them(config)

        assert with_stale == baseline
        assert "The shared moments of the last while" not in baseline

    @pytest.mark.asyncio
    async def test_telemetry_keys(
        self, config: EgoConfig, relationships: RelationshipStore
    ) -> None:
        write_items(
            config.data_dir,
            [
                affect_item(
                    valence="brighter", arousal="quieter", dv=0.25, da=-0.18
                )
            ],
        )

        await run_consider_them(config)

        metadata = get_tool_metadata()
        assert metadata["affect_valence_direction"] == "brighter"
        assert metadata["affect_arousal_direction"] == "quieter"
        assert metadata["affect_dv"] == 0.25
        assert metadata["affect_da"] == -0.18
