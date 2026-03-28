"""Backfill placeholder notion titles from source memory content."""

from __future__ import annotations

from pathlib import Path

from ego_mcp._memory_serialization import memory_from_chromadb
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.notion import NotionStore, derive_notion_label, is_placeholder_notion_label
from ego_mcp.types import Memory

TARGET_VERSION = "0.4.2"
_MEMORY_COLLECTION_NAME = "ego_memories"


def _load_source_memories(data_dir: Path, memory_ids: list[str]) -> list[Memory]:
    chroma_dir = data_dir / "chroma"
    if not memory_ids or not chroma_dir.exists():
        return []

    try:
        chromadb = load_chromadb()
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=_MEMORY_COLLECTION_NAME)
        rows = collection.get(ids=memory_ids, include=["documents", "metadatas"])
    except Exception:
        return []

    ids = rows.get("ids", [])
    documents = rows.get("documents", [])
    metadatas = rows.get("metadatas", [])

    memories_by_id: dict[str, Memory] = {}
    for memory_id, document, metadata in zip(ids, documents, metadatas):
        if (
            not isinstance(memory_id, str)
            or not isinstance(document, str)
            or not isinstance(metadata, dict)
        ):
            continue
        memories_by_id[memory_id] = memory_from_chromadb(memory_id, document, metadata)

    return [memories_by_id[memory_id] for memory_id in memory_ids if memory_id in memories_by_id]


def up(data_dir: Path) -> None:
    """Replace placeholder notion labels with content-derived titles when possible."""
    notion_path = data_dir / "notions.json"
    if not notion_path.exists():
        return

    store = NotionStore(notion_path)
    for notion in store.list_all():
        if not notion.id or not is_placeholder_notion_label(notion.label):
            continue

        source_memories = _load_source_memories(data_dir, notion.source_memory_ids)
        if not source_memories:
            continue

        next_label = derive_notion_label(
            notion.emotion_tone,
            source_memories,
            notion_tags=notion.tags,
        )
        if is_placeholder_notion_label(next_label):
            continue

        store.update(notion.id, label=next_label)
