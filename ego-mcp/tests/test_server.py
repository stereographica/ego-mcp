"""Focused tests for server-side tool dispatch behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mcp.types import TextContent

import ego_mcp.server as server_mod
from ego_mcp.consolidation import ConsolidationStats, MergeCandidate
from ego_mcp.desire import DesireEngine
from ego_mcp.types import Emotion, EmotionalTrace, Memory


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

    @pytest.mark.asyncio
    async def test_completion_log_context_emits_snapshot_for_non_feel_desires(self) -> None:
        class FakeMemoryStore:
            async def list_recent(self, n: int = 1) -> list[Memory]:
                assert n == 1
                return [
                    Memory(
                        id="mem_1",
                        content="latest",
                        timestamp="2026-02-26T00:00:00+00:00",
                        emotional_trace=EmotionalTrace(
                            primary=Emotion.CURIOUS,
                            intensity=0.8,
                            valence=0.2,
                            arousal=0.7,
                        ),
                    )
                ]

        extra = await server_mod._completion_log_context(
            "remember",
            cast(Any, FakeMemoryStore()),
        )

        assert extra["emotion_primary"] == "curious"
        assert extra["emotion_intensity"] == 0.8
        assert extra["valence"] == 0.2
        assert extra["arousal"] == 0.7


class TestForgetToolServerHandlers:
    @pytest.mark.asyncio
    async def test_handle_forget_existing_memory_returns_summary_and_syncs_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        deleted_memory = Memory(
            id="mem_forget_1",
            content="This memory should be forgotten after consolidation review.",
            timestamp="2026-02-20T12:34:56+00:00",
            emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS, intensity=0.8),
            importance=4,
        )

        class FakeMemoryStore:
            async def delete(self, memory_id: str) -> Memory | None:
                assert memory_id == "mem_forget_1"
                return deleted_memory

        class FakeSync:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove_memory(self, memory_id: str) -> bool:
                self.calls.append(memory_id)
                return True

        fake_sync = FakeSync()
        monkeypatch.setattr(server_mod, "_workspace_sync", fake_sync)

        text = await server_mod._handle_forget(
            cast(Any, FakeMemoryStore()),
            {"memory_id": "mem_forget_1"},
        )

        assert "Forgot" in text
        assert "mem_forget_1" in text
        assert "emotion: curious" in text
        assert "importance: 4" in text
        assert fake_sync.calls == ["mem_forget_1"]

    @pytest.mark.asyncio
    async def test_handle_forget_missing_memory_returns_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeMemoryStore:
            async def delete(self, memory_id: str) -> Memory | None:
                assert memory_id == "mem_missing"
                return None

        monkeypatch.setattr(server_mod, "_workspace_sync", None)

        text = await server_mod._handle_forget(
            cast(Any, FakeMemoryStore()),
            {"memory_id": "mem_missing"},
        )

        assert "Memory not found: mem_missing" in text
        assert "Double-check the ID." in text

    @pytest.mark.asyncio
    async def test_dispatch_forget_does_not_satisfy_implicit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[tuple[str, dict[str, Any] | None]] = []

        class FakeDesire:
            def satisfy_implicit(self, name: str, category: str | None = None) -> None:
                calls.append((name, {"category": category} if category else None))

        async def fake_handle_forget(_memory: object, _args: dict[str, object]) -> str:
            return "forgot"

        monkeypatch.setattr(server_mod, "_handle_forget", fake_handle_forget)

        text = await server_mod._dispatch(
            "forget",
            {"memory_id": "mem_abc"},
            cast(Any, SimpleNamespace(companion_name="Master")),
            cast(Any, object()),
            FakeDesire(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

        assert text == "forgot"
        assert calls == []

    @pytest.mark.asyncio
    async def test_handle_consolidate_merge_candidates_scaffold_mentions_forget(self) -> None:
        class FakeConsolidation:
            async def run(self, _memory: object) -> ConsolidationStats:
                return ConsolidationStats(
                    replay_events=1,
                    coactivation_updates=1,
                    link_updates=0,
                    refreshed_memories=1,
                    merge_candidates=(
                        MergeCandidate(
                            memory_a_id="mem_a",
                            memory_b_id="mem_b",
                            distance=0.08,
                            snippet_a="A side",
                            snippet_b="B side",
                        ),
                    ),
                )

        text = await server_mod._handle_consolidate(
            cast(Any, object()),
            cast(Any, FakeConsolidation()),
        )

        assert "use forget to remove it" in text
        assert "If both have value, consider which perspective to keep." in text

    @pytest.mark.asyncio
    async def test_handle_get_episode_filters_deleted_memory_ids_and_adds_note(self) -> None:
        episode = SimpleNamespace(
            id="ep_1",
            summary="Test episode",
            memory_ids=["mem_keep", "mem_gone"],
            start_time="2026-02-20T12:00:00+00:00",
            end_time="2026-02-20T13:00:00+00:00",
            importance=4,
        )

        class FakeEpisodeStore:
            async def get_by_id(self, episode_id: str) -> object | None:
                assert episode_id == "ep_1"
                return episode

        class FakeMemoryStore:
            async def get_by_id(self, memory_id: str) -> Memory | None:
                if memory_id == "mem_keep":
                    return Memory(
                        id="mem_keep",
                        content="still exists",
                        timestamp="2026-02-20T12:05:00+00:00",
                    )
                return None

        text = await server_mod._handle_get_episode(
            FakeEpisodeStore(),  # type: ignore[arg-type]
            FakeMemoryStore(),  # type: ignore[arg-type]
            {"episode_id": "ep_1"},
        )

        assert "Episode: ep_1" in text
        assert "Memories: 1" in text
        assert "Note: 1 memory(ies) no longer exist." in text
