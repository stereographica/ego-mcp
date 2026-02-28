"""Chroma-backed MemoryStore implementation."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from ego_mcp import _memory_queries
from ego_mcp._memory_serialization import links_to_json
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.config import EgoConfig
from ego_mcp.embedding import EgoEmbeddingFunction
from ego_mcp.hopfield import ModernHopfieldNetwork
from ego_mcp.types import (
    BodyState,
    Category,
    Emotion,
    EmotionalTrace,
    LinkType,
    Memory,
    MemoryLink,
    MemorySearchResult,
)

logger = logging.getLogger(__name__)
chromadb = load_chromadb()


class MemoryStore:
    """ChromaDB-backed memory storage with semantic search, Hopfield recall, and auto-linking."""

    def __init__(self, config: EgoConfig, embedding_fn: EgoEmbeddingFunction) -> None:
        self._config = config
        self._embedding_fn = embedding_fn
        self._client: Any = None
        self._collection: Any = None
        self._hopfield = ModernHopfieldNetwork(beta=4.0, n_iters=3)

    def connect(self) -> None:
        """Initialize ChromaDB connection."""
        chroma_dir = self._config.data_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(chroma_dir)
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name="ego_memories",
            embedding_function=self._embedding_fn,
        )

    def close(self) -> None:
        """Best-effort shutdown for ChromaDB client resources."""
        if self._client is None:
            return
        server = getattr(self._client, "_server", None)
        if server is not None and hasattr(server, "stop"):
            try:
                server.stop()
            except Exception:
                pass
        self._client = None
        self._collection = None

    def _ensure_connected(self) -> Any:
        if self._collection is None:
            self.connect()
        assert self._collection is not None
        return self._collection

    def get_client(self) -> Any:
        """Return active vector-store client (connect lazily if needed)."""
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    @property
    def data_dir(self) -> Path:
        """Return configured data directory path."""
        return self._config.data_dir

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the configured embedding function."""
        return self._embedding_fn(texts)

    def collection_count(self) -> int:
        """Return number of stored memories."""
        return int(self._ensure_connected().count())

    async def save(
        self,
        content: str,
        emotion: str = "neutral",
        secondary: list[str] | None = None,
        intensity: float = 0.5,
        importance: int = 3,
        category: str = "daily",
        valence: float = 0.0,
        arousal: float = 0.5,
        body_state: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        private: bool = False,
    ) -> Memory:
        """Save a single memory."""
        collection = self._ensure_connected()
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        timestamp = Memory.now_iso()

        metadata: dict[str, Any] = {
            "emotion": emotion,
            "secondary": ",".join(secondary) if secondary else "",
            "intensity": intensity,
            "importance": importance,
            "category": category,
            "timestamp": timestamp,
            "valence": valence,
            "arousal": arousal,
            "body_state": json.dumps(body_state) if body_state else "",
            "tags": ",".join(tags) if tags else "",
            "linked_ids": "[]",
            "is_private": bool(private),
        }

        collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[metadata],
        )

        try:
            primary_emotion = Emotion(emotion)
        except ValueError:
            primary_emotion = Emotion.NEUTRAL

        try:
            cat = Category(category)
        except ValueError:
            cat = Category.DAILY

        secondary_emotions: list[Emotion] = []
        if secondary:
            for token in secondary:
                try:
                    secondary_emotions.append(Emotion(token))
                except ValueError:
                    continue

        state_obj: BodyState | None = None
        if body_state:
            try:
                state_obj = BodyState(
                    time_phase=str(body_state.get("time_phase", "unknown")),
                    system_load=str(body_state.get("system_load", "unknown")),
                    uptime_hours=float(body_state.get("uptime_hours", 0.0)),
                )
            except (TypeError, ValueError):
                state_obj = None

        return Memory(
            id=memory_id,
            content=content,
            timestamp=timestamp,
            emotional_trace=EmotionalTrace(
                primary=primary_emotion,
                secondary=secondary_emotions,
                intensity=float(intensity),
                valence=valence,
                arousal=arousal,
                body_state=state_obj,
            ),
            importance=importance,
            category=cat,
            tags=tags or [],
            is_private=bool(private),
        )

    async def save_with_auto_link(
        self,
        content: str,
        emotion: str = "neutral",
        secondary: list[str] | None = None,
        intensity: float = 0.5,
        importance: int = 3,
        category: str = "daily",
        valence: float = 0.0,
        arousal: float = 0.5,
        body_state: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        private: bool = False,
        link_threshold: float = 0.3,
        max_links: int = 5,
        dedup_threshold: float = 0.05,
    ) -> tuple[Memory | None, int, list[MemorySearchResult], MemorySearchResult | None]:
        """Save memory and auto-link bidirectionally to similar existing memories.

        Returns:
            (saved_memory_or_none, num_links_created, linked_results, duplicate_of)
        """
        collection = self._ensure_connected()

        if int(collection.count()) > 0:
            dedup_candidates = await self.search(content, n_results=1)
            if dedup_candidates and dedup_candidates[0].distance < dedup_threshold:
                return None, 0, [], dedup_candidates[0]

        memory = await self.save(
            content=content,
            emotion=emotion,
            secondary=secondary,
            intensity=intensity,
            importance=importance,
            category=category,
            valence=valence,
            arousal=arousal,
            body_state=body_state,
            tags=tags,
            private=private,
        )

        num_links = 0
        linked_results: list[MemorySearchResult] = []
        try:
            similar = await self.search(content, n_results=max_links + 1)
            for result in similar:
                if result.memory.id == memory.id:
                    continue
                if result.distance < link_threshold:
                    linked_results.append(result)
                    confidence = 1.0 - result.distance
                    memory.linked_ids.append(
                        MemoryLink(
                            target_id=result.memory.id,
                            link_type=LinkType.SIMILAR,
                            confidence=confidence,
                        )
                    )
                    existing_links = list(result.memory.linked_ids)
                    existing_links.append(
                        MemoryLink(
                            target_id=memory.id,
                            link_type=LinkType.SIMILAR,
                            confidence=confidence,
                        )
                    )
                    collection.update(
                        ids=[result.memory.id],
                        metadatas=[{"linked_ids": links_to_json(existing_links)}],
                    )

                    num_links += 1
                    if num_links >= max_links:
                        break

            if num_links > 0:
                collection.update(
                    ids=[memory.id],
                    metadatas=[{"linked_ids": links_to_json(memory.linked_ids)}],
                )
        except (ValueError, KeyError) as e:
            logger.warning("Auto-link failed: %s", e)

        return memory, num_links, linked_results, None

    async def link_memories(
        self, source_id: str, target_id: str, link_type: str = "related"
    ) -> bool:
        """Create a bidirectional link between two memories.

        Returns True if a new link was created, False if already linked.
        """
        collection = self._ensure_connected()
        try:
            lt = LinkType(link_type)
        except ValueError:
            lt = LinkType.RELATED

        source = await self.get_by_id(source_id)
        target = await self.get_by_id(target_id)
        if source is None or target is None:
            logger.warning("Cannot link: one or both memories not found")
            return False

        if any(link.target_id == target_id for link in source.linked_ids):
            return False

        source.linked_ids.append(MemoryLink(target_id=target_id, link_type=lt))
        collection.update(
            ids=[source_id],
            metadatas=[{"linked_ids": links_to_json(source.linked_ids)}],
        )

        target.linked_ids.append(MemoryLink(target_id=source_id, link_type=lt))
        collection.update(
            ids=[target_id],
            metadatas=[{"linked_ids": links_to_json(target.linked_ids)}],
        )

        return True

    async def bump_link_confidence(
        self,
        source_id: str,
        target_id: str,
        delta: float = 0.1,
    ) -> bool:
        """Increase bidirectional link confidence and persist metadata.

        If the link does not exist, create a related link with baseline confidence.
        """
        collection = self._ensure_connected()
        source = await self.get_by_id(source_id)
        target = await self.get_by_id(target_id)
        if source is None or target is None:
            return False

        clamped_delta = max(0.0, min(1.0, delta))

        def _bump(memory: Memory, other_id: str) -> bool:
            for link in memory.linked_ids:
                if link.target_id == other_id:
                    before = link.confidence
                    link.confidence = min(1.0, max(0.0, before + clamped_delta))
                    return link.confidence != before
            memory.linked_ids.append(
                MemoryLink(
                    target_id=other_id,
                    link_type=LinkType.RELATED,
                    confidence=min(1.0, 0.5 + clamped_delta),
                )
            )
            return True

        changed_source = _bump(source, target_id)
        changed_target = _bump(target, source_id)

        if changed_source:
            collection.update(
                ids=[source_id],
                metadatas=[{"linked_ids": links_to_json(source.linked_ids)}],
            )
        if changed_target:
            collection.update(
                ids=[target_id],
                metadatas=[{"linked_ids": links_to_json(target.linked_ids)}],
            )
        return changed_source or changed_target

    async def search(
        self,
        query: str,
        n_results: int = 5,
        emotion_filter: str | None = None,
        category_filter: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        valence_range: list[float] | None = None,
        arousal_range: list[float] | None = None,
    ) -> list[MemorySearchResult]:
        """Search memories by semantic similarity with optional filters."""
        return await _memory_queries.search(
            self,
            query=query,
            n_results=n_results,
            emotion_filter=emotion_filter,
            category_filter=category_filter,
            date_from=date_from,
            date_to=date_to,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )

    async def recall(
        self,
        context: str,
        n_results: int = 3,
        valence_range: list[float] | None = None,
        arousal_range: list[float] | None = None,
    ) -> list[MemorySearchResult]:
        """Recall memories using semantic search + Hopfield hybrid."""
        return await _memory_queries.recall(
            self,
            context=context,
            n_results=n_results,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )

    async def list_recent(
        self, n: int = 10, category_filter: str | None = None
    ) -> list[Memory]:
        """List recent memories sorted by timestamp descending."""
        return await _memory_queries.list_recent(
            self, n=n, category_filter=category_filter
        )

    async def get_by_id(self, memory_id: str) -> Memory | None:
        """Retrieve a specific memory by ID."""
        return await _memory_queries.get_by_id(self, memory_id)

    async def delete(self, memory_id: str) -> Memory | None:
        """Delete a memory and clean reverse links from linked targets."""
        return await _memory_queries.delete(self, memory_id)
