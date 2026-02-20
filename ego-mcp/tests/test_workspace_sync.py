"""Tests for OpenClaw workspace Markdown synchronization."""

from __future__ import annotations

from pathlib import Path

from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory
from ego_mcp.workspace_sync import WorkspaceMemorySync


def _memory(
    *,
    memory_id: str,
    content: str,
    category: Category = Category.DAILY,
    importance: int = 3,
    emotion: Emotion = Emotion.NEUTRAL,
    timestamp: str = "2026-02-20T12:34:56+00:00",
) -> Memory:
    return Memory(
        id=memory_id,
        content=content,
        timestamp=timestamp,
        category=category,
        importance=importance,
        emotional_trace=EmotionalTrace(primary=emotion, intensity=0.7),
    )


class TestWorkspaceMemorySync:
    def test_read_latest_monologue_empty(self, tmp_path: Path) -> None:
        sync = WorkspaceMemorySync(tmp_path)
        text, updated = sync.read_latest_monologue()
        assert text is None
        assert updated is None

    def test_sync_introspection_updates_latest_and_daily(self, tmp_path: Path) -> None:
        sync = WorkspaceMemorySync(tmp_path)
        mem = _memory(
            memory_id="mem_intro",
            content="I want to reflect before speaking.",
            category=Category.INTROSPECTION,
            emotion=Emotion.CURIOUS,
        )
        result = sync.sync_memory(mem)
        assert result.daily_updated is True
        assert result.latest_monologue_updated is True

        latest_text, updated = sync.read_latest_monologue()
        assert latest_text == "I want to reflect before speaking."
        assert updated == "2026-02-20T12:34:56+00:00"

        daily = (tmp_path / "memory" / "2026-02-20.md").read_text(encoding="utf-8")
        assert "[id:mem_intro]" in daily

    def test_sync_curated_for_high_importance(self, tmp_path: Path) -> None:
        sync = WorkspaceMemorySync(tmp_path)
        mem = _memory(
            memory_id="mem_major",
            content="Breakthrough insight from today's collaboration.",
            category=Category.TECHNICAL,
            importance=5,
            emotion=Emotion.EXCITED,
        )
        result = sync.sync_memory(mem)
        assert result.curated_updated is True
        curated = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
        assert "[id:mem_major]" in curated

    def test_sync_deduplicates_by_memory_id(self, tmp_path: Path) -> None:
        sync = WorkspaceMemorySync(tmp_path)
        mem = _memory(
            memory_id="mem_dup",
            content="Do not duplicate this entry.",
            category=Category.LESSON,
            importance=4,
        )
        first = sync.sync_memory(mem)
        second = sync.sync_memory(mem)
        assert first.daily_updated is True
        assert second.daily_updated is False

        daily = (tmp_path / "memory" / "2026-02-20.md").read_text(encoding="utf-8")
        assert daily.count("[id:mem_dup]") == 1
