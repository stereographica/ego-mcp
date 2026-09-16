"""introspect presentation of the derived layer (D3 / D4 / D5 / D6 S3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import ego_mcp._server_surface_core as core_mod
from ego_mcp import timezone_utils
from ego_mcp._server_runtime import get_tool_metadata, reset_tool_metadata
from ego_mcp._server_surface_core import _handle_introspect
from ego_mcp.config import EgoConfig
from ego_mcp.derived import stagnation as stagnation_lens
from ego_mcp.derived.contract import DerivedFile, DerivedReader, write_lens_file
from ego_mcp.notion import NotionStore
from ego_mcp.relationship import RelationshipStore
from ego_mcp.types import Memory, Notion

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def write_items(
    data_dir: Path,
    lens: str,
    items: list[dict[str, Any]],
    *,
    now: datetime = NOW,
    ttl_hours: float = 168.0,
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
    def __init__(self, by_id: dict[str, Memory] | None = None) -> None:
        self.by_id = by_id or {}

    async def list_recent(
        self, n: int = 30, category_filter: str | None = None
    ) -> list[Memory]:
        del n, category_filter
        return []

    async def get_by_id(self, memory_id: str) -> Memory | None:
        return self.by_id.get(memory_id)


class _FakeDesire:
    @property
    def ema_levels(self) -> dict[str, float]:
        return {}

    def compute_levels_with_modulation(self, **_kwargs: Any) -> dict[str, float]:
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


@pytest.fixture
def notion_store(config: EgoConfig, monkeypatch: pytest.MonkeyPatch) -> NotionStore:
    store = NotionStore(config.data_dir / "notions.json")
    monkeypatch.setattr(core_mod, "get_notion_store", lambda: store)
    return store


@pytest.fixture(autouse=True)
def _surface_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_relationship(_config: Any, _memory: Any, _person: str) -> str:
        return "relationship snapshot"

    async def fake_modulation(
        *_args: Any, **_kwargs: Any
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        return {}, {}, {}

    monkeypatch.setattr(core_mod, "_relationship_snapshot_override", fake_relationship)
    monkeypatch.setattr(core_mod, "_derive_desire_modulation_override", fake_modulation)
    monkeypatch.setattr(timezone_utils, "now", lambda: NOW)
    reset_tool_metadata()


async def run_introspect(
    config: EgoConfig,
    memory: _FakeMemory | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    return await _handle_introspect(
        config,
        cast(Any, memory or _FakeMemory()),
        cast(Any, _FakeDesire()),
        args,
    )


# ---------------------------------------------------------------------------
# D3 S2 — Unconnected density (focus=network)
# ---------------------------------------------------------------------------


def holes_items() -> list[dict[str, Any]]:
    return [
        {
            "key": "holes:person_unlinked:alice",
            "kind": "person_unlinked",
            "person_id": "alice",
            "memory_ids": ["m1"],
            "count": 7,
        },
        {
            "key": "holes:worn_isolated:mem_worn",
            "kind": "worn_isolated",
            "memory_id": "mem_worn",
            "access_count": 9,
        },
        {
            "key": "holes:tag_without_notion:rain",
            "kind": "tag_without_notion",
            "tag": "rain",
            "memory_ids": ["m2"],
            "count": 8,
        },
        {
            "key": "holes:straddling:mem_strad",
            "kind": "straddling",
            "memory_id": "mem_strad",
            "notion_ids": ["n_alpha", "n_beta"],
        },
    ]


EXPECTED_HOLES_SECTION = (
    "\nUnconnected density:\n"
    "  Alice appears in many memories that never connected to anything.\n"
    '  "the worn one" — returned to often, linked to nothing.\n'
    '  "rain" runs through many memories but no notion holds it.\n'
    '  "the straddler" stands between "Alpha" and "Beta".'
)


@pytest.fixture
def holes_world(
    config: EgoConfig, notion_store: NotionStore
) -> _FakeMemory:
    RelationshipStore(config.data_dir / "relationships" / "models.json").update(
        "alice", {"name": "Alice"}
    )
    notion_store.save(Notion(id="n_alpha", label="Alpha", confidence=0.4))
    notion_store.save(Notion(id="n_beta", label="Beta", confidence=0.4))
    return _FakeMemory(
        {
            "mem_worn": Memory(id="mem_worn", content="the worn one"),
            "mem_strad": Memory(id="mem_strad", content="the straddler"),
        }
    )


class TestUnconnectedDensity:
    @pytest.mark.asyncio
    async def test_section_is_verbatim(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        write_items(config.data_dir, "holes", holes_items())

        result = await run_introspect(config, holes_world, {"focus": "network"})

        assert EXPECTED_HOLES_SECTION in result

    @pytest.mark.asyncio
    async def test_kind_order_is_fixed_regardless_of_file_order(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        write_items(config.data_dir, "holes", list(reversed(holes_items())))

        result = await run_introspect(config, holes_world, {"focus": "network"})

        assert EXPECTED_HOLES_SECTION in result

    @pytest.mark.asyncio
    async def test_at_most_four_lines(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        write_items(config.data_dir, "holes", holes_items())

        result = await run_introspect(config, holes_world, {"focus": "network"})

        section = result.split("Unconnected density:\n", 1)[1].split("\n\n---", 1)[0]
        assert len(section.splitlines()) == 4

    @pytest.mark.asyncio
    async def test_deleted_target_skips_the_kind_without_falling_back(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        items = holes_items()
        items.insert(
            2,
            {
                "key": "holes:worn_isolated:mem_second",
                "kind": "worn_isolated",
                "memory_id": "mem_second",
                "access_count": 4,
            },
        )
        holes_world.by_id.pop("mem_worn")
        holes_world.by_id["mem_second"] = Memory(
            id="mem_second", content="the runner-up"
        )
        write_items(config.data_dir, "holes", items)

        result = await run_introspect(config, holes_world, {"focus": "network"})

        assert "returned to often, linked to nothing." not in result
        assert "the runner-up" not in result
        assert "Alice appears in many memories" in result

    @pytest.mark.asyncio
    async def test_telemetry_lists_shown_kinds(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        write_items(config.data_dir, "holes", holes_items())

        await run_introspect(config, holes_world, {"focus": "network"})

        assert get_tool_metadata()["holes_presented"] == json.dumps(
            [
                "person_unlinked",
                "worn_isolated",
                "tag_without_notion",
                "straddling",
            ]
        )

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_network_output_unchanged(
        self, config: EgoConfig, holes_world: _FakeMemory
    ) -> None:
        baseline = await run_introspect(config, holes_world, {"focus": "network"})

        write_items(
            config.data_dir,
            "holes",
            holes_items(),
            now=NOW - timedelta(days=30),
        )
        with_stale = await run_introspect(config, holes_world, {"focus": "network"})

        assert with_stale == baseline
        assert "Unconnected density:" not in baseline


# ---------------------------------------------------------------------------
# D4 S2 — notion drift replaces landscape lines
# ---------------------------------------------------------------------------


def drift_item(notion_id: str, *, generated: str = "2026-09-17") -> dict[str, Any]:
    return {
        "key": f"drift:{notion_id}:{generated}",
        "kind": "drift",
        "notion_id": notion_id,
        "distance": 0.31,
        "ratio": 2.1,
        "newest_source_memory_id": "mem_x",
    }


def stale_item(notion_id: str, *, generated: str = "2026-09-17") -> dict[str, Any]:
    return {
        "key": f"drift:{notion_id}:{generated}:stale",
        "kind": "stale_conviction",
        "notion_id": notion_id,
        "days_since_reinforced": 60,
    }


@pytest.fixture
def landscape(notion_store: NotionStore) -> NotionStore:
    notion_store.save(Notion(id="n1", label="First", confidence=0.9))
    notion_store.save(Notion(id="n2", label="Second", confidence=0.8))
    notion_store.save(Notion(id="n3", label="Third", confidence=0.7))
    return notion_store


class TestDriftLandscape:
    @pytest.mark.asyncio
    async def test_drift_line_is_verbatim(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        write_items(config.data_dir, "drift", [drift_item("n1")])

        result = await run_introspect(config)

        assert (
            '- "First" confidence: 0.9 — is this still true? '
            "Its recent ground has shifted." in result
        )

    @pytest.mark.asyncio
    async def test_stale_line_is_verbatim(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        write_items(config.data_dir, "drift", [stale_item("n3")])

        result = await run_introspect(config)

        assert (
            '- "Third" confidence: 0.7 — unrevisited for a while. Still true?'
            in result
        )

    @pytest.mark.asyncio
    async def test_at_most_two_replacements_drift_first(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        write_items(
            config.data_dir,
            "drift",
            [drift_item("n3"), stale_item("n1"), stale_item("n2")],
        )

        result = await run_introspect(config)

        assert '- "Third" confidence: 0.7 — is this still true?' in result
        assert '- "First" confidence: 0.9 — unrevisited for a while.' in result
        assert '- "Second" confidence: 0.8' in result
        assert '- "Second" confidence: 0.8 —' not in result

    @pytest.mark.asyncio
    async def test_same_generation_is_shown_once(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        write_items(config.data_dir, "drift", [drift_item("n1")])

        first = await run_introspect(config)
        again = await run_introspect(config)

        assert "is this still true?" in first
        assert "is this still true?" not in again

    @pytest.mark.asyncio
    async def test_recent_presentation_holds_the_seven_day_cooldown(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        DerivedReader(config.data_dir).mark_surfaced(
            "drift:n1:2026-09-16", now=NOW - timedelta(days=1)
        )
        write_items(config.data_dir, "drift", [drift_item("n1")])

        result = await run_introspect(config)

        assert "is this still true?" not in result

    @pytest.mark.asyncio
    async def test_cooldown_expires_after_seven_days(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        DerivedReader(config.data_dir).mark_surfaced(
            "drift:n1:2026-09-08", now=NOW - timedelta(days=8)
        )
        write_items(config.data_dir, "drift", [drift_item("n1")])

        result = await run_introspect(config)

        assert "is this still true?" in result

    @pytest.mark.asyncio
    async def test_notion_outside_the_landscape_adds_no_line(
        self, config: EgoConfig, notion_store: NotionStore
    ) -> None:
        notion_store.save(Notion(id="n1", label="First", confidence=0.95))
        notion_store.save(Notion(id="low", label="Quiet one", confidence=0.4))
        write_items(config.data_dir, "drift", [drift_item("low")])

        result = await run_introspect(config)

        assert "Quiet one" not in result
        assert "is this still true?" not in result

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_landscape_unchanged(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        baseline = await run_introspect(config)

        write_items(
            config.data_dir,
            "drift",
            [drift_item("n1")],
            now=NOW - timedelta(days=30),
        )
        with_stale = await run_introspect(config)

        assert with_stale == baseline
        assert '- "First" confidence: 0.9' in baseline

    @pytest.mark.asyncio
    async def test_telemetry_keys(
        self, config: EgoConfig, landscape: NotionStore
    ) -> None:
        write_items(config.data_dir, "drift", [drift_item("n3"), stale_item("n1")])

        await run_introspect(config)

        metadata = get_tool_metadata()
        assert metadata["drift_presented"] == json.dumps(["n3", "n1"])
        assert metadata["drift_kinds"] == json.dumps(["drift", "stale_conviction"])


# ---------------------------------------------------------------------------
# D5 S2 — chapter boundaries
# ---------------------------------------------------------------------------


def chapter_item(week: str) -> dict[str, Any]:
    return {
        "key": f"chapter:{week}",
        "boundary_week": week,
        "score": 0.52,
        "before_memory_id": "mem_before",
        "after_memory_id": "mem_after",
        "people_before": [],
        "people_after": [],
    }


FRESH_CHAPTER_BLOCK = (
    "Chapters (unnamed):\n"
    '  A turn around a few months ago — from "the old ground"'
    ' toward "the new ground".\n'
    "  If it has a name, that's yours to give."
)


@pytest.fixture
def chapter_memory() -> _FakeMemory:
    return _FakeMemory(
        {
            "mem_before": Memory(id="mem_before", content="the old ground"),
            "mem_after": Memory(id="mem_after", content="the new ground"),
        }
    )


class TestChapterLines:
    @pytest.mark.asyncio
    async def test_fresh_boundary_is_three_verbatim_lines(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
    ) -> None:
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            ttl_hours=336.0,
        )

        result = await run_introspect(config, chapter_memory)

        assert FRESH_CHAPTER_BLOCK in result

    @pytest.mark.asyncio
    async def test_second_call_collapses_to_the_count_line(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
    ) -> None:
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01"), chapter_item("2026-01-05")],
            ttl_hours=336.0,
        )

        first = await run_introspect(config, chapter_memory)
        second = await run_introspect(config, chapter_memory)
        third = await run_introspect(config, chapter_memory)

        # Newest boundary first, then the older one, then only the count line.
        assert "A turn around a few months ago" in first
        assert "A turn around about a year ago" in second
        assert (
            "Chapters (unnamed): two turns so far, the last one a few months ago."
            in third
        )

    @pytest.mark.asyncio
    async def test_count_is_a_word(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
    ) -> None:
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            ttl_hours=336.0,
        )
        DerivedReader(config.data_dir).mark_surfaced(
            "chapter:2026-06-01", now=NOW - timedelta(days=1)
        )

        result = await run_introspect(config, chapter_memory)

        assert (
            "Chapters (unnamed): one turns so far, the last one a few months ago."
            in result
        )

    @pytest.mark.asyncio
    async def test_deleted_quote_is_marked_and_skipped(
        self, config: EgoConfig, notion_store: NotionStore
    ) -> None:
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            ttl_hours=336.0,
        )

        result = await run_introspect(config, _FakeMemory())

        assert "Chapters (unnamed)" not in result
        assert DerivedReader(config.data_dir).is_surfaced("chapter:2026-06-01")

    @pytest.mark.asyncio
    async def test_section_sits_between_episodes_and_self_model(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        episode = SimpleNamespace(
            id="ep1",
            summary="a week of rain",
            memory_ids=["m1", "m2"],
            start_time=(NOW - timedelta(days=3)).isoformat(),
        )

        class _FakeEpisodes:
            async def list_episodes(self, limit: int = 10) -> list[Any]:
                del limit
                return [episode]

        monkeypatch.setattr(core_mod, "get_episodes", lambda: _FakeEpisodes())
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            ttl_hours=336.0,
        )

        result = await run_introspect(config, chapter_memory)

        assert result.index("Recent episodes:") < result.index("Chapters (unnamed):")
        assert result.index("Chapters (unnamed):") < result.index("Self model:")

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_output_unchanged(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
    ) -> None:
        baseline = await run_introspect(config, chapter_memory)

        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            now=NOW - timedelta(days=30),
            ttl_hours=336.0,
        )
        with_stale = await run_introspect(config, chapter_memory)

        assert with_stale == baseline
        assert "Chapters (unnamed)" not in baseline

    @pytest.mark.asyncio
    async def test_telemetry_keys(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        chapter_memory: _FakeMemory,
    ) -> None:
        write_items(
            config.data_dir,
            "chapters",
            [chapter_item("2026-06-01")],
            ttl_hours=336.0,
        )

        await run_introspect(config, chapter_memory)

        metadata = get_tool_metadata()
        assert metadata["derived_presented"] == "chapter:2026-06-01"
        assert metadata["chapter_presented"] == "chapter:2026-06-01"
        assert metadata["chapter_count"] == 1


# ---------------------------------------------------------------------------
# D6 S3 — the stagnation bridge line on the scaffold
# ---------------------------------------------------------------------------


def stagnation_item(band: str) -> dict[str, Any]:
    return {
        "key": "stagnation:2026-09-17",
        "band": band,
        "score": 0.7 if band == "stuck" else 0.5,
        "components": {
            "sameness": 0.8,
            "repetition": 0.7,
            "novelty": 0.1,
            "births": 0.0,
        },
        "memory_count": 12,
    }


BRIDGE_LINE = (
    "Some of this might be worth bringing to TestUser "
    "rather than turning over alone."
)


class TestStagnationBridge:
    @pytest.mark.asyncio
    async def test_disabled_by_default(
        self, config: EgoConfig, notion_store: NotionStore
    ) -> None:
        write_items(
            config.data_dir, "stagnation", [stagnation_item("stuck")], ttl_hours=36.0
        )

        result = await run_introspect(config)

        assert BRIDGE_LINE not in result
        assert "stagnation_bridge_shown" not in get_tool_metadata()

    @pytest.mark.asyncio
    async def test_shown_for_circling_when_enabled(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            stagnation_lens, "STAGNATION_MODULATION_ENABLED", True
        )
        write_items(
            config.data_dir,
            "stagnation",
            [stagnation_item("circling")],
            ttl_hours=36.0,
        )

        result = await run_introspect(config)

        assert result.endswith(BRIDGE_LINE)
        assert get_tool_metadata()["stagnation_bridge_shown"] is True

    @pytest.mark.asyncio
    async def test_shown_for_stuck_when_enabled(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            stagnation_lens, "STAGNATION_MODULATION_ENABLED", True
        )
        write_items(
            config.data_dir, "stagnation", [stagnation_item("stuck")], ttl_hours=36.0
        )

        result = await run_introspect(config)

        assert BRIDGE_LINE in result

    @pytest.mark.asyncio
    async def test_flowing_stays_quiet_when_enabled(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            stagnation_lens, "STAGNATION_MODULATION_ENABLED", True
        )
        write_items(
            config.data_dir,
            "stagnation",
            [stagnation_item("flowing")],
            ttl_hours=36.0,
        )

        result = await run_introspect(config)

        assert BRIDGE_LINE not in result

    @pytest.mark.asyncio
    async def test_no_derived_file_leaves_scaffold_unchanged(
        self,
        config: EgoConfig,
        notion_store: NotionStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            stagnation_lens, "STAGNATION_MODULATION_ENABLED", True
        )
        baseline = await run_introspect(config)

        write_items(
            config.data_dir,
            "stagnation",
            [stagnation_item("stuck")],
            now=NOW - timedelta(days=5),
            ttl_hours=36.0,
        )
        with_stale = await run_introspect(config)

        assert with_stale == baseline
        assert BRIDGE_LINE not in baseline
