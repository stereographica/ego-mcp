"""wake_up presentation of the derived layer (D1 S2 recurrence, D2 S2 dream)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

import ego_mcp._server_surface_core as core_mod
from ego_mcp import timezone_utils
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_core import _handle_wake_up
from ego_mcp.config import EgoConfig
from ego_mcp.derived.contract import DerivedFile, DerivedReader, write_lens_file
from ego_mcp.types import Memory

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
TODAY = "2026-09-17"


def write_items(
    data_dir: Path,
    lens: str,
    items: list[dict[str, Any]],
    *,
    now: datetime = NOW,
    ttl_hours: float = 36.0,
) -> None:
    """Write one derived lens file the way the nightly batch would."""
    write_lens_file(
        data_dir,
        DerivedFile(
            lens=lens,
            generated_at=now.isoformat(),
            valid_until=(now + timedelta(hours=ttl_hours)).isoformat(),
            source={},
            items=items,
        ),
    )


class _FakeMemory:
    """Minimal MemoryStore stand-in for the wake_up handler."""

    def __init__(
        self,
        *,
        recent: list[Memory] | None = None,
        by_id: dict[str, Memory] | None = None,
    ) -> None:
        self.recent = recent or []
        self.by_id = by_id or {}
        self.requested: list[str] = []

    async def list_recent(
        self, n: int = 30, category_filter: str | None = None
    ) -> list[Memory]:
        del n, category_filter
        return list(self.recent)

    async def get_by_id(self, memory_id: str) -> Memory | None:
        self.requested.append(memory_id)
        return self.by_id.get(memory_id)

    def list_anticipations(self, include_surfaced: bool = False) -> list[Memory]:
        del include_surfaced
        return []


class _FakeDesire:
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
    import ego_mcp._server_runtime as runtime

    async def fake_relationship(_config: Any, _memory: Any, name: str) -> str:
        return f"Relationship with {name}: trust is steady."

    async def fake_modulation(
        *_args: Any, **_kwargs: Any
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(core_mod, "_relationship_snapshot_override", fake_relationship)
    monkeypatch.setattr(core_mod, "_derive_desire_modulation_override", fake_modulation)
    monkeypatch.setattr(
        core_mod, "_get_body_state_override", lambda: {"time_phase": "morning"}
    )
    monkeypatch.setattr(core_mod, "get_workspace_sync", lambda: None)

    impulse = MagicMock()
    impulse.register_proust_event.return_value = {}
    monkeypatch.setattr(runtime, "_impulse_manager_getter", lambda: impulse)
    notion_store = MagicMock()
    notion_store.list_all.return_value = []
    monkeypatch.setattr(runtime, "_notion_store_getter", lambda: notion_store)

    monkeypatch.setattr(timezone_utils, "now", lambda: NOW)
    reset_tool_metadata()


async def run_wake_up(config: EgoConfig, memory: _FakeMemory) -> str:
    return await _handle_wake_up(
        config, cast(Any, memory), cast(Any, _FakeDesire())
    )


def set_dice(monkeypatch: pytest.MonkeyPatch, value: float) -> None:
    monkeypatch.setattr(
        "ego_mcp._server_surface_core.random.random", lambda: value
    )


# ---------------------------------------------------------------------------
# D1 S2 — recurrence
# ---------------------------------------------------------------------------


def recurrence_item(
    *,
    memory_id: str = "mem_old",
    on_date: str = TODAY,
    period: str = "year",
    span: int = 1,
) -> dict[str, Any]:
    return {
        "key": f"recurrence:{memory_id}:{on_date}",
        "memory_id": memory_id,
        "on_date": on_date,
        "period": period,
        "span": span,
        "score": 1.2,
    }


@pytest.fixture
def recalled() -> Memory:
    return Memory(id="mem_old", content="Walked the old road with her.")


class TestRecurrenceSurfaceLine:
    @pytest.mark.asyncio
    async def test_year_wording_is_verbatim(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(config.data_dir, "recurrence", [recurrence_item()])
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        assert (
            'Around this time a year ago: "Walked the old road with her."' in result
        )

    @pytest.mark.asyncio
    async def test_multi_year_span_is_a_word(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(
            config.data_dir, "recurrence", [recurrence_item(period="year", span=2)]
        )
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        assert (
            'Around this time two years ago: "Walked the old road with her."'
            in result
        )

    @pytest.mark.asyncio
    async def test_half_year_wording(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(
            config.data_dir,
            "recurrence",
            [recurrence_item(period="half_year", span=1)],
        )
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        assert "Around this time half a year ago:" in result

    @pytest.mark.asyncio
    async def test_line_sits_between_anticipation_and_desire_currents(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(config.data_dir, "recurrence", [recurrence_item()])
        set_dice(monkeypatch, 0.1)
        approaching = Memory(
            id="soon",
            content="the soon thing",
            anticipated_at=(NOW + timedelta(hours=2)).isoformat(),
        )
        memory = _FakeMemory(by_id={"mem_old": recalled})
        memory.list_anticipations = lambda include_surfaced=False: [  # type: ignore[method-assign]
            approaching
        ]

        result = await run_wake_up(config, memory)

        assert result.index("Approaching:") < result.index("Around this time")
        assert result.index("Around this time") < result.index("Desire currents:")

    @pytest.mark.asyncio
    async def test_probability_gate_boundaries(
        self,
        config: EgoConfig,
        recalled: Memory,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "recurrence", [recurrence_item()])

        set_dice(monkeypatch, 0.49)
        shown = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))
        assert "Around this time" in shown

        # A fresh data dir so the one-per-day mark does not decide this.
        silent_dir = tmp_path / "silent"
        silent_dir.mkdir()
        silent_config = replace(config, data_dir=silent_dir)
        write_items(silent_dir, "recurrence", [recurrence_item()])
        set_dice(monkeypatch, 0.5)
        silent = await run_wake_up(
            silent_config, _FakeMemory(by_id={"mem_old": recalled})
        )
        assert "Around this time" not in silent

    @pytest.mark.asyncio
    async def test_only_todays_items_are_used(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(
            config.data_dir,
            "recurrence",
            [recurrence_item(on_date="2026-09-18")],
        )
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        assert "Around this time" not in result

    @pytest.mark.asyncio
    async def test_at_most_one_per_day(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        second = Memory(id="mem_other", content="Another old day.")
        write_items(
            config.data_dir,
            "recurrence",
            [recurrence_item(), recurrence_item(memory_id="mem_other")],
        )
        set_dice(monkeypatch, 0.1)
        memory = _FakeMemory(by_id={"mem_old": recalled, "mem_other": second})

        first = await run_wake_up(config, memory)
        again = await run_wake_up(config, memory)

        assert "Walked the old road with her." in first
        assert "Around this time" not in again

    @pytest.mark.asyncio
    async def test_deleted_memory_is_marked_and_skipped(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(config.data_dir, "recurrence", [recurrence_item()])
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory())

        assert "Around this time" not in result
        reader = DerivedReader(config.data_dir)
        assert reader.is_surfaced(f"recurrence:mem_old:{TODAY}")

    @pytest.mark.asyncio
    async def test_expired_file_emits_nothing(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(
            config.data_dir,
            "recurrence",
            [recurrence_item()],
            now=NOW - timedelta(hours=48),
        )
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        assert "Around this time" not in result

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_output_unchanged(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_dice(monkeypatch, 0.1)
        baseline = await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        write_items(
            config.data_dir,
            "recurrence",
            [recurrence_item()],
            now=NOW - timedelta(hours=48),
        )
        with_stale = await run_wake_up(
            config, _FakeMemory(by_id={"mem_old": recalled})
        )

        assert with_stale == baseline

    @pytest.mark.asyncio
    async def test_telemetry_keys(
        self, config: EgoConfig, recalled: Memory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(config.data_dir, "recurrence", [recurrence_item()])
        set_dice(monkeypatch, 0.1)

        await run_wake_up(config, _FakeMemory(by_id={"mem_old": recalled}))

        metadata = get_tool_metadata()
        assert metadata["derived_presented"] == f"recurrence:mem_old:{TODAY}"
        assert metadata["recurrence_presented"] == "mem_old"
        assert metadata["recurrence_period"] == "year"


# ---------------------------------------------------------------------------
# D2 S2 — dream
# ---------------------------------------------------------------------------


DREAM_ITEM: dict[str, Any] = {
    "key": "dream:mem_a:mem_b",
    "memory_ids": ["mem_a", "mem_b"],
    "distance": 0.81,
    "threads": ["emotion", "hour"],
}

DREAM_BLOCK = (
    "A strange dream:\n"
    '  "the first fragment"\n'
    '  "the second fragment"\n'
    "They were side by side. Nothing says why."
)


@pytest.fixture
def dream_pair() -> dict[str, Memory]:
    return {
        "mem_a": Memory(id="mem_a", content="the first fragment"),
        "mem_b": Memory(id="mem_b", content="the second fragment"),
    }


class TestDreamSurfaceBlock:
    @pytest.mark.asyncio
    async def test_block_is_verbatim(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)

        result = await run_wake_up(config, _FakeMemory(by_id=dream_pair))

        assert DREAM_BLOCK in result

    @pytest.mark.asyncio
    async def test_not_shown_when_proust_fired(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)
        seed = Memory(id="seed", content="today's thought")

        async def fake_proust(_seed: str, _memory: Any) -> Memory:
            return Memory(id="proust", content="the old smell")

        monkeypatch.setattr(core_mod, "find_proust_memory", fake_proust)

        result = await run_wake_up(
            config, _FakeMemory(recent=[seed], by_id=dream_pair)
        )

        assert "Involuntary recall:" in result
        assert "A strange dream:" not in result

    @pytest.mark.asyncio
    async def test_shown_when_proust_found_nothing(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)
        seed = Memory(id="seed", content="today's thought")

        async def fake_proust(_seed: str, _memory: Any) -> Memory | None:
            return None

        monkeypatch.setattr(core_mod, "find_proust_memory", fake_proust)

        result = await run_wake_up(
            config, _FakeMemory(recent=[seed], by_id=dream_pair)
        )

        assert "A strange dream:" in result

    @pytest.mark.asyncio
    async def test_probability_gate_boundaries(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.14)
        shown = await run_wake_up(config, _FakeMemory(by_id=dream_pair))
        assert "A strange dream:" in shown

        silent_dir = tmp_path / "silent"
        silent_dir.mkdir()
        silent_config = replace(config, data_dir=silent_dir)
        write_items(silent_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.15)
        silent = await run_wake_up(silent_config, _FakeMemory(by_id=dream_pair))
        assert "A strange dream:" not in silent

    @pytest.mark.asyncio
    async def test_shown_only_once(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)
        memory = _FakeMemory(by_id=dream_pair)

        first = await run_wake_up(config, memory)
        again = await run_wake_up(config, memory)

        assert "A strange dream:" in first
        assert "A strange dream:" not in again

    @pytest.mark.asyncio
    async def test_missing_side_is_marked_and_skipped(
        self, config: EgoConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)
        only_one = {"mem_a": Memory(id="mem_a", content="the first fragment")}

        result = await run_wake_up(config, _FakeMemory(by_id=only_one))

        assert "A strange dream:" not in result
        assert DerivedReader(config.data_dir).is_surfaced("dream:mem_a:mem_b")

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_output_unchanged(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dice(monkeypatch, 0.1)
        baseline = await run_wake_up(config, _FakeMemory(by_id=dream_pair))

        write_items(
            config.data_dir,
            "dream",
            [DREAM_ITEM],
            now=NOW - timedelta(hours=72),
            ttl_hours=48.0,
        )
        with_stale = await run_wake_up(config, _FakeMemory(by_id=dream_pair))

        assert with_stale == baseline

    @pytest.mark.asyncio
    async def test_telemetry_keys(
        self,
        config: EgoConfig,
        dream_pair: dict[str, Memory],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_items(config.data_dir, "dream", [DREAM_ITEM], ttl_hours=48.0)
        set_dice(monkeypatch, 0.1)

        await run_wake_up(config, _FakeMemory(by_id=dream_pair))

        metadata = get_tool_metadata()
        assert metadata["derived_presented"] == "dream:mem_a:mem_b"
        assert metadata["dream_presented"] == "dream:mem_a:mem_b"
        assert metadata["dream_thread"] == "emotion,hour"
