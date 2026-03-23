"""Tests for notion title migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ego_mcp import migrations as migrations_mod
from ego_mcp.notion import NotionStore
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory, Notion


def _memory(memory_id: str, content: str) -> Memory:
    return Memory(
        id=memory_id,
        content=content,
        category=Category.INTROSPECTION,
        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS, valence=0.3),
    )


def _install_fake_chroma(
    monkeypatch: pytest.MonkeyPatch,
    migration_mod: object,
    memory_map: dict[str, Memory],
) -> None:
    class _FakeCollection:
        def get(self, *, ids: list[str], include: list[str]) -> dict[str, object]:
            assert include == ["documents", "metadatas"]
            available_ids = [memory_id for memory_id in ids if memory_id in memory_map]
            return {
                "ids": available_ids,
                "documents": [memory_map[memory_id].content for memory_id in available_ids],
                "metadatas": [{"category": memory_map[memory_id].category.value} for memory_id in available_ids],
            }

    class _FakePersistentClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_collection(self, name: str) -> _FakeCollection:
            assert name == "ego_memories"
            return _FakeCollection()

    monkeypatch.setattr(
        migration_mod,
        "load_chromadb",
        lambda: SimpleNamespace(PersistentClient=_FakePersistentClient),
    )
    monkeypatch.setattr(
        migration_mod,
        "memory_from_chromadb",
        lambda memory_id, document, _metadata: memory_map[memory_id].__class__(
            **{**memory_map[memory_id].__dict__, "content": document, "id": memory_id}
        ),
    )


def test_0003_notion_content_titles_relabels_untitled_notions_from_source_memories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0003_notion_content_titles")
    data_dir = tmp_path
    (data_dir / "chroma").mkdir()

    store = NotionStore(data_dir / "notions.json")
    store.save(
        Notion(
            id="notion_untitled",
            label="untitled (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["mem_a", "mem_b"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )
    store.save(
        Notion(
            id="notion_named",
            label="pattern & signal (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["mem_c"],
            tags=["pattern", "signal"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    _install_fake_chroma(
        monkeypatch,
        migration_mod,
        {
            "mem_a": _memory(
                "mem_a",
                "A recurring thought about continuity. emotion traces might carry weight.",
            ),
            "mem_b": _memory("mem_b", "A recurring thought about continuity.\nFurther detail."),
            "mem_c": _memory("mem_c", "Named notion should stay untouched."),
        },
    )

    migration_mod.up(data_dir)

    migrated_store = NotionStore(data_dir / "notions.json")
    migrated = migrated_store.get_by_id("notion_untitled")
    named = migrated_store.get_by_id("notion_named")

    assert migrated is not None
    assert migrated.label == "A recurring thought about continuity (curious)"
    assert named is not None
    assert named.label == "pattern & signal (curious)"


def test_0003_notion_content_titles_noop_when_notions_file_missing(tmp_path: Path) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0003_notion_content_titles")

    migration_mod.up(tmp_path)

    assert not (tmp_path / "notions.json").exists()


def test_0003_notion_content_titles_leaves_placeholder_when_source_memories_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0003_notion_content_titles")
    data_dir = tmp_path
    (data_dir / "chroma").mkdir()

    store = NotionStore(data_dir / "notions.json")
    store.save(
        Notion(
            id="notion_untitled",
            label="untitled (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["mem_missing"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    _install_fake_chroma(monkeypatch, migration_mod, {})

    migration_mod.up(data_dir)

    migrated = NotionStore(data_dir / "notions.json").get_by_id("notion_untitled")
    assert migrated is not None
    assert migrated.label == "untitled (curious)"


def test_0003_notion_content_titles_skips_when_chroma_directory_is_missing(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0003_notion_content_titles")
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_untitled",
            label="untitled (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["mem_a"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_untitled")
    assert migrated is not None
    assert migrated.label == "untitled (curious)"


def test_run_migrations_applies_0003_notion_content_titles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0003_notion_content_titles")
    data_dir = tmp_path
    (data_dir / "chroma").mkdir()

    store = NotionStore(data_dir / "notions.json")
    store.save(
        Notion(
            id="notion_untitled",
            label="untitled (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["mem_a"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    _install_fake_chroma(
        monkeypatch,
        migration_mod,
        {"mem_a": _memory("mem_a", "A recurring thought about continuity. More detail.")},
    )

    applied = migrations_mod.run_migrations(data_dir)

    migrated = NotionStore(data_dir / "notions.json").get_by_id("notion_untitled")
    state = json.loads((data_dir / "migration_state.json").read_text(encoding="utf-8"))

    assert migrated is not None
    assert migrated.label == "A recurring thought about continuity (curious)"
    assert "0003_notion_content_titles" in applied
    assert "0003_notion_content_titles" in state["applied"]
