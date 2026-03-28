"""Backfill notion network and maturity fields."""

from __future__ import annotations

import json
from pathlib import Path

from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.notion import NotionStore, infer_person_id

TARGET_VERSION = "0.5.0"
_EPISODE_COLLECTION_NAME = "ego_episodes"


def _load_relationship_payload(data_dir: Path) -> dict[str, dict[str, object]]:
    relationship_path = data_dir / "relationships" / "models.json"
    if not relationship_path.exists():
        return {}
    try:
        payload = json.loads(relationship_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        person: raw for person, raw in payload.items() if isinstance(person, str) and isinstance(raw, dict)
    }


def _load_person_memory_ids(data_dir: Path) -> dict[str, set[str]]:
    chroma_dir = data_dir / "chroma"
    if not chroma_dir.exists():
        return {}

    relationships = _load_relationship_payload(data_dir)
    if not relationships:
        return {}

    try:
        chromadb = load_chromadb()
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=_EPISODE_COLLECTION_NAME)
    except Exception:
        return {}

    person_memory_ids: dict[str, set[str]] = {}
    for person, raw in relationships.items():
        episode_ids = raw.get("shared_episode_ids", [])
        if not isinstance(episode_ids, list):
            continue
        normalized_episode_ids = [episode_id for episode_id in episode_ids if isinstance(episode_id, str)]
        if not normalized_episode_ids:
            continue
        try:
            rows = collection.get(ids=normalized_episode_ids, include=["documents", "metadatas"])
        except Exception:
            continue
        metadatas = rows.get("metadatas", [])
        memories: set[str] = set()
        for metadata in metadatas:
            if not isinstance(metadata, dict):
                continue
            raw_memory_ids = metadata.get("memory_ids", "[]")
            if isinstance(raw_memory_ids, str):
                try:
                    memory_ids = json.loads(raw_memory_ids)
                except json.JSONDecodeError:
                    memory_ids = []
            else:
                memory_ids = raw_memory_ids
            if isinstance(memory_ids, list):
                memories.update(
                    memory_id
                    for memory_id in memory_ids
                    if isinstance(memory_id, str) and memory_id
                )
        if memories:
            person_memory_ids[person] = memories
    return person_memory_ids


def up(data_dir: Path) -> None:
    """Backfill notion fields introduced in v0.5.0."""
    notion_path = data_dir / "notions.json"
    if not notion_path.exists():
        return

    person_memory_ids = _load_person_memory_ids(data_dir)
    store = NotionStore(notion_path)
    for notion in store.list_all():
        store.update(
            notion.id,
            related_notion_ids=list(notion.related_notion_ids),
            reinforcement_count=max(0, len(notion.source_memory_ids) - 3),
            person_id=infer_person_id(notion.source_memory_ids, person_memory_ids),
        )
