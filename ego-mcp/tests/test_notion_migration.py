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


def _install_fake_episode_chroma(
    monkeypatch: pytest.MonkeyPatch,
    migration_mod: object,
    episode_rows: dict[str, dict[str, object]],
) -> None:
    class _FakeCollection:
        def get(
            self,
            *,
            ids: list[str],
            include: list[str],
        ) -> dict[str, object]:
            assert include == ["documents", "metadatas"]
            available_ids = [episode_id for episode_id in ids if episode_id in episode_rows]
            return {
                "ids": available_ids,
                "documents": [str(episode_rows[episode_id].get("summary", "")) for episode_id in available_ids],
                "metadatas": [
                    dict(metadata)
                    for episode_id in available_ids
                    for metadata in [episode_rows[episode_id].get("metadata", {})]
                    if isinstance(metadata, dict)
                ],
            }

    class _FakePersistentClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_collection(self, name: str) -> _FakeCollection:
            assert name == "ego_episodes"
            return _FakeCollection()

    monkeypatch.setattr(
        migration_mod,
        "load_chromadb",
        lambda: SimpleNamespace(PersistentClient=_FakePersistentClient),
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
    assert "0004_notion_fields" in applied
    assert "0003_notion_content_titles" in state["applied"]
    assert "0004_notion_fields" in state["applied"]
    assert migrated.related_notion_ids == []
    assert migrated.reinforcement_count == 0
    assert migrated.person_id == ""


def test_0004_notion_fields_backfills_defaults_and_person_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0004_notion_fields")
    data_dir = tmp_path
    (data_dir / "chroma").mkdir()
    relationships_dir = data_dir / "relationships"
    relationships_dir.mkdir()
    (relationships_dir / "models.json").write_text(
        json.dumps(
            {
                "Master": {
                    "shared_episode_ids": ["ep_master"],
                }
            }
        ),
        encoding="utf-8",
    )

    store = NotionStore(data_dir / "notions.json")
    store.save(
        Notion(
            id="notion_1",
            label="pattern (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3", "m4"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    _install_fake_episode_chroma(
        monkeypatch,
        migration_mod,
        {
            "ep_master": {
                "summary": "shared work",
                "metadata": {
                    "memory_ids": json.dumps(["m1", "m2", "m3", "m9"]),
                    "start_time": "2026-03-01T00:00:00+00:00",
                    "end_time": "2026-03-01T01:00:00+00:00",
                    "importance": 4,
                },
            }
        },
    )

    migration_mod.up(data_dir)

    migrated = NotionStore(data_dir / "notions.json").get_by_id("notion_1")
    assert migrated is not None
    assert migrated.related_notion_ids == []
    assert migrated.reinforcement_count == 1
    assert migrated.person_id == "Master"


def test_0004_notion_fields_skips_person_inference_when_no_majority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0004_notion_fields")
    data_dir = tmp_path
    (data_dir / "chroma").mkdir()
    relationships_dir = data_dir / "relationships"
    relationships_dir.mkdir()
    (relationships_dir / "models.json").write_text(
        json.dumps(
            {
                "Master": {"shared_episode_ids": ["ep_master"]},
                "Friend": {"shared_episode_ids": ["ep_friend"]},
            }
        ),
        encoding="utf-8",
    )

    store = NotionStore(data_dir / "notions.json")
    store.save(
        Notion(
            id="notion_2",
            label="balanced (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3", "m4"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    _install_fake_episode_chroma(
        monkeypatch,
        migration_mod,
        {
            "ep_master": {
                "summary": "master",
                "metadata": {
                    "memory_ids": json.dumps(["m1", "m2"]),
                    "start_time": "",
                    "end_time": "",
                    "importance": 3,
                },
            },
            "ep_friend": {
                "summary": "friend",
                "metadata": {
                    "memory_ids": json.dumps(["m3", "m4"]),
                    "start_time": "",
                    "end_time": "",
                    "importance": 3,
                },
            },
        },
    )

    migration_mod.up(data_dir)

    migrated = NotionStore(data_dir / "notions.json").get_by_id("notion_2")
    assert migrated is not None
    assert migrated.person_id == ""


def test_0004_notion_fields_backfills_defaults_without_chroma_or_relationships(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0004_notion_fields")
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_plain",
            label="plain (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3", "m4"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_plain")
    assert migrated is not None
    assert migrated.related_notion_ids == []
    assert migrated.reinforcement_count == 1
    assert migrated.person_id == ""


def test_0004_notion_fields_keeps_reinforcement_count_zero_for_small_clusters(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0004_notion_fields")
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_small",
            label="small (curious)",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_small")
    assert migrated is not None
    assert migrated.reinforcement_count == 0


def test_0009_notion_meta_fields_backfills_empty_dict_for_legacy_notions(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0009_notion_meta_fields")
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_old",
            label="old notion",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_old")
    assert migrated is not None
    assert migrated.meta_fields == {}


def test_0009_notion_meta_fields_preserves_existing_meta_fields(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0009_notion_meta_fields")
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_with_meta",
            label="notion with meta",
            emotion_tone=Emotion.CURIOUS,
            source_memory_ids=["m1", "m2", "m3"],
            created="2026-03-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
            meta_fields={
                "note": {"type": "text", "value": "hello"},
                "ids": {"type": "notion_ids", "notion_ids": ["other"]},
            },
        )
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_with_meta")
    assert migrated is not None
    assert migrated.meta_fields["note"] == {"type": "text", "value": "hello"}
    assert migrated.meta_fields["ids"] == {"type": "notion_ids", "notion_ids": ["other"]}


def test_0009_notion_meta_fields_handles_legacy_flat_dict_format(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0009_notion_meta_fields")
    notions_file = tmp_path / "notions.json"
    notions_file.write_text(
        json.dumps({
            "notion_legacy": {
                "label": "legacy notion",
                "emotion_tone": "curious",
                "confidence": 0.5,
                "source_memory_ids": ["m1"],
                "created": "2026-03-01T00:00:00+00:00",
                "last_reinforced": "2026-03-01T00:00:00+00:00",
            }
        }),
        encoding="utf-8",
    )

    migration_mod.up(tmp_path)

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_legacy")
    assert migrated is not None
    assert migrated.meta_fields == {}


def test_0009_notion_meta_fields_converts_legacy_list_to_flat_dict(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0009_notion_meta_fields")
    notions_file = tmp_path / "notions.json"
    notions_file.write_text(
        json.dumps({
            "notions": [
                {
                    "id": "notion_list",
                    "label": "list notion",
                    "emotion_tone": "curious",
                    "confidence": 0.5,
                    "source_memory_ids": ["m1"],
                    "created": "2026-03-01T00:00:00+00:00",
                    "last_reinforced": "2026-03-01T00:00:00+00:00",
                }
            ]
        }),
        encoding="utf-8",
    )

    migration_mod.up(tmp_path)

    updated_data = json.loads(notions_file.read_text(encoding="utf-8"))
    assert "notions" not in updated_data
    assert "notion_list" in updated_data
    assert updated_data["notion_list"]["meta_fields"] == {}

    migrated = NotionStore(tmp_path / "notions.json").get_by_id("notion_list")
    assert migrated is not None
    assert migrated.label == "list notion"
    assert migrated.meta_fields == {}


def test_0009_notion_meta_fields_legacy_list_handles_missing_id(
    tmp_path: Path,
) -> None:
    migration_mod = importlib.import_module("ego_mcp.migrations.0009_notion_meta_fields")
    notions_file = tmp_path / "notions.json"
    notions_file.write_text(
        json.dumps({
            "notions": [
                {
                    "label": "no id notion",
                    "emotion_tone": "curious",
                    "confidence": 0.5,
                    "source_memory_ids": ["m1"],
                    "created": "2026-03-01T00:00:00+00:00",
                    "last_reinforced": "2026-03-01T00:00:00+00:00",
                }
            ]
        }),
        encoding="utf-8",
    )

    migration_mod.up(tmp_path)

    # Entry without id is skipped, so no write happens
    updated_data = json.loads(notions_file.read_text(encoding="utf-8"))
    assert "notions" in updated_data
    assert len(updated_data["notions"]) == 1
    assert "meta_fields" not in updated_data["notions"][0]
