"""Episode memory management."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ego_mcp.chromadb_compat import load_chromadb

if TYPE_CHECKING:
    from ego_mcp.memory import MemoryStore

logger = logging.getLogger(__name__)
chromadb = load_chromadb()


@dataclass
class Episode:
    """A coherent sequence of memories forming a narrative."""

    id: str = ""
    summary: str = ""
    memory_ids: list[str] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    importance: int = 3

    def to_metadata(self) -> dict[str, Any]:
        return {
            "memory_ids": json.dumps(self.memory_ids),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "importance": self.importance,
        }

    @classmethod
    def from_metadata(
        cls, episode_id: str, summary: str, metadata: dict[str, Any]
    ) -> Episode:
        memory_ids_raw = metadata.get("memory_ids", "[]")
        if isinstance(memory_ids_raw, str):
            try:
                memory_ids = json.loads(memory_ids_raw)
            except json.JSONDecodeError:
                memory_ids = []
        else:
            memory_ids = list(memory_ids_raw)

        return cls(
            id=episode_id,
            summary=summary,
            memory_ids=memory_ids,
            start_time=metadata.get("start_time", ""),
            end_time=metadata.get("end_time", ""),
            importance=int(metadata.get("importance", 3)),
        )


class EpisodeStore:
    """ChromaDB-backed episode storage."""

    def __init__(self, memory_store: "MemoryStore", collection: Any) -> None:
        self._memory_store = memory_store
        self._collection = collection

    async def create(
        self,
        memory_ids: list[str],
        summary: str,
    ) -> Episode:
        """Create an episode from memory IDs."""
        if not memory_ids:
            raise ValueError("memory_ids cannot be empty")

        # Get memories to determine time range and importance
        memories = []
        for mid in memory_ids:
            m = await self._memory_store.get_by_id(mid)
            if m is not None:
                memories.append(m)

        if not memories:
            raise ValueError("No valid memories found for given IDs")

        memories.sort(key=lambda m: m.timestamp)

        episode = Episode(
            id=f"ep_{uuid.uuid4().hex[:12]}",
            summary=summary,
            memory_ids=[m.id for m in memories],
            start_time=memories[0].timestamp,
            end_time=memories[-1].timestamp
            if len(memories) > 1
            else memories[0].timestamp,
            importance=max(m.importance for m in memories),
        )

        self._collection.add(
            ids=[episode.id],
            documents=[episode.summary],
            metadatas=[episode.to_metadata()],
        )

        logger.info("Created episode %s with %d memories", episode.id, len(memories))
        return episode

    async def get_by_id(self, episode_id: str) -> Episode | None:
        """Get episode by ID."""
        try:
            results = self._collection.get(
                ids=[episode_id],
                include=["documents", "metadatas"],
            )
            if not results["ids"]:
                return None
            return Episode.from_metadata(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
            )
        except Exception as e:
            logger.warning("Failed to get episode %s: %s", episode_id, e)
            return None

    async def search(self, query: str, n_results: int = 5) -> list[Episode]:
        """Search episodes by summary."""
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.warning("Failed to search episodes: %s", e)
            return []

        found: list[Episode] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        for eid, doc, meta in zip(ids, docs, metas):
            found.append(Episode.from_metadata(eid, doc, meta))
        return found

    async def list_episodes(self, limit: int = 20) -> list[Episode]:
        """List all episodes, newest first."""
        total = int(self._collection.count())
        if total == 0 or limit <= 0:
            return []

        results = self._collection.get(
            limit=total,
            include=["documents", "metadatas"],
        )
        episodes = []
        for eid, doc, meta in zip(
            results["ids"], results["documents"], results["metadatas"]
        ):
            episodes.append(Episode.from_metadata(eid, doc, meta))
        episodes.sort(key=lambda e: e.start_time, reverse=True)
        return episodes[:limit]
