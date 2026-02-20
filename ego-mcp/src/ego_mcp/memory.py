"""Memory store with ChromaDB backend."""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from ego_mcp.chromadb_compat import load_chromadb

from ego_mcp.config import EgoConfig
from ego_mcp.embedding import EgoEmbeddingFunction
from ego_mcp.hopfield import ModernHopfieldNetwork
from ego_mcp.types import (
    BodyState,
    Category,
    Emotion,
    EmotionalTrace,
    Memory,
    MemoryLink,
    MemorySearchResult,
    LinkType,
)

logger = logging.getLogger(__name__)
chromadb = load_chromadb()


# --- Scoring functions (ported from embodied-claude/memory-mcp) ---

EMOTION_BOOST_MAP: dict[str, float] = {
    "excited": 0.4,
    "surprised": 0.35,
    "moved": 0.3,
    "sad": 0.25,
    "happy": 0.2,
    "nostalgic": 0.15,
    "curious": 0.1,
    "neutral": 0.0,
}


def calculate_time_decay(
    timestamp: str,
    now: datetime | None = None,
    half_life_days: float = 30.0,
) -> float:
    """Exponential time decay. Returns 0.0 (forgotten) to 1.0 (fresh)."""
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        memory_time = datetime.fromisoformat(timestamp)
        if memory_time.tzinfo is None:
            memory_time = memory_time.replace(tzinfo=timezone.utc)
    except ValueError:
        return 1.0

    age_seconds = (now - memory_time).total_seconds()
    if age_seconds < 0:
        return 1.0

    age_days = age_seconds / 86400
    decay = math.pow(2, -age_days / half_life_days)
    return max(0.0, min(1.0, decay))


def calculate_emotion_boost(emotion: str) -> float:
    """Emotion-based boost value."""
    return EMOTION_BOOST_MAP.get(emotion, 0.0)


def calculate_importance_boost(importance: int) -> float:
    """Importance-based boost. 1→0.0, 5→0.4."""
    clamped = max(1, min(5, importance))
    return (clamped - 1) / 10


def calculate_final_score(
    semantic_distance: float,
    time_decay: float,
    emotion_boost: float,
    importance_boost: float,
    semantic_weight: float = 1.0,
    decay_weight: float = 0.3,
    emotion_weight: float = 0.2,
    importance_weight: float = 0.2,
) -> float:
    """Combined score. Lower = more relevant."""
    decay_penalty = (1.0 - time_decay) * decay_weight
    total_boost = emotion_boost * emotion_weight + importance_boost * importance_weight
    final = semantic_distance * semantic_weight + decay_penalty - total_boost
    return max(0.0, final)


# --- Helper functions ---


def _memory_from_chromadb(
    memory_id: str, content: str, metadata: dict[str, Any]
) -> Memory:
    """Reconstruct Memory from ChromaDB metadata."""
    emotion_str = metadata.get("emotion", "neutral")
    try:
        primary_emotion = Emotion(emotion_str)
    except ValueError:
        primary_emotion = Emotion.NEUTRAL

    category_str = metadata.get("category", "daily")
    try:
        category = Category(category_str)
    except ValueError:
        category = Category.DAILY

    # Parse linked_ids from JSON
    linked_ids: list[MemoryLink] = []
    linked_json = metadata.get("linked_ids", "")
    if linked_json:
        try:
            link_list = json.loads(linked_json)
            for link_data in link_list:
                try:
                    linked_ids.append(
                        MemoryLink(
                            target_id=link_data.get("target_id", ""),
                            link_type=LinkType(link_data.get("link_type", "related")),
                            confidence=float(link_data.get("confidence", 0.5)),
                            note=link_data.get("note", ""),
                        )
                    )
                except (ValueError, TypeError):
                    pass
        except (json.JSONDecodeError, TypeError):
            pass

    secondary: list[Emotion] = []
    secondary_raw = metadata.get("secondary", "")
    if isinstance(secondary_raw, str) and secondary_raw:
        for token in secondary_raw.split(","):
            try:
                secondary.append(Emotion(token))
            except ValueError:
                continue

    body_state: BodyState | None = None
    body_state_raw = metadata.get("body_state", "")
    if isinstance(body_state_raw, str) and body_state_raw:
        try:
            payload = json.loads(body_state_raw)
            if isinstance(payload, dict):
                body_state = BodyState(
                    time_phase=str(payload.get("time_phase", "unknown")),
                    system_load=str(payload.get("system_load", "unknown")),
                    uptime_hours=float(payload.get("uptime_hours", 0.0)),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            body_state = None

    return Memory(
        id=memory_id,
        content=content,
        timestamp=metadata.get("timestamp", ""),
        emotional_trace=EmotionalTrace(
            primary=primary_emotion,
            secondary=secondary,
            intensity=float(metadata.get("intensity", 0.5)),
            valence=float(metadata.get("valence", 0.0)),
            arousal=float(metadata.get("arousal", 0.5)),
            body_state=body_state,
        ),
        importance=int(metadata.get("importance", 3)),
        category=category,
        tags=metadata.get("tags", "").split(",") if metadata.get("tags") else [],
        linked_ids=linked_ids,
    )


def _links_to_json(links: list[MemoryLink]) -> str:
    """Serialize MemoryLinks to JSON string for ChromaDB metadata."""
    return json.dumps(
        [
            {
                "target_id": link.target_id,
                "link_type": link.link_type.value,
                "confidence": link.confidence,
                "note": link.note,
            }
            for link in links
        ]
    )


# --- MemoryStore ---


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
        link_threshold: float = 0.3,
        max_links: int = 5,
    ) -> tuple[Memory, int]:
        """Save memory and auto-link bidirectionally to similar existing memories.

        Returns:
            (saved_memory, num_links_created)
        """
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
        )

        # Search for similar memories to auto-link
        num_links = 0
        collection = self._ensure_connected()
        try:
            similar = await self.search(content, n_results=max_links + 1)
            for result in similar:
                if result.memory.id == memory.id:
                    continue
                if result.distance < link_threshold:
                    confidence = 1.0 - result.distance
                    # Forward link: new memory → existing
                    memory.linked_ids.append(
                        MemoryLink(
                            target_id=result.memory.id,
                            link_type=LinkType.SIMILAR,
                            confidence=confidence,
                        )
                    )
                    # Reverse link: existing memory → new memory (persist to ChromaDB)
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
                        metadatas=[{"linked_ids": _links_to_json(existing_links)}],
                    )

                    num_links += 1
                    if num_links >= max_links:
                        break

            # Persist forward links on new memory
            if num_links > 0:
                collection.update(
                    ids=[memory.id],
                    metadatas=[{"linked_ids": _links_to_json(memory.linked_ids)}],
                )
        except (ValueError, KeyError) as e:
            logger.warning("Auto-link failed: %s", e)

        return memory, num_links

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

        # Check if already linked
        if any(link.target_id == target_id for link in source.linked_ids):
            return False

        # Add forward link
        source.linked_ids.append(MemoryLink(target_id=target_id, link_type=lt))
        collection.update(
            ids=[source_id],
            metadatas=[{"linked_ids": _links_to_json(source.linked_ids)}],
        )

        # Add reverse link
        target.linked_ids.append(MemoryLink(target_id=source_id, link_type=lt))
        collection.update(
            ids=[target_id],
            metadatas=[{"linked_ids": _links_to_json(target.linked_ids)}],
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
                metadatas=[{"linked_ids": _links_to_json(source.linked_ids)}],
            )
        if changed_target:
            collection.update(
                ids=[target_id],
                metadatas=[{"linked_ids": _links_to_json(target.linked_ids)}],
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
        collection = self._ensure_connected()

        where_clauses: list[dict[str, Any]] = []
        if emotion_filter:
            where_clauses.append({"emotion": emotion_filter})
        if category_filter:
            where_clauses.append({"category": category_filter})

        collection_count = collection.count()
        if collection_count == 0:
            return []

        # date and emotion ranges are post-filters; over-fetch to avoid false negatives.
        has_date_filter = bool(date_from or date_to)
        has_valence_filter = bool(valence_range and len(valence_range) == 2)
        has_arousal_filter = bool(arousal_range and len(arousal_range) == 2)
        fetch_n = n_results
        if has_date_filter or has_valence_filter or has_arousal_filter:
            fetch_n = max(n_results * 5, 20)

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(fetch_n, collection_count),
            "include": ["documents", "metadatas", "distances"],
        }
        if where_clauses:
            if len(where_clauses) == 1:
                query_kwargs["where"] = where_clauses[0]
            else:
                query_kwargs["where"] = {"$and": where_clauses}

        results = collection.query(**query_kwargs)

        search_results: list[MemorySearchResult] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for mid, doc, meta, dist in zip(ids, docs, metas, distances):
            memory = _memory_from_chromadb(mid, doc, meta)

            # Post-filter by date range (ISO string comparison works for dates)
            if date_from and memory.timestamp < date_from:
                continue
            if date_to and memory.timestamp[: len(date_to)] > date_to:
                continue
            if has_valence_filter and valence_range is not None:
                valence = memory.emotional_trace.valence
                if valence < min(valence_range) or valence > max(valence_range):
                    continue
            if has_arousal_filter and arousal_range is not None:
                arousal = memory.emotional_trace.arousal
                if arousal < min(arousal_range) or arousal > max(arousal_range):
                    continue

            time_decay = calculate_time_decay(memory.timestamp)
            emotion_boost = calculate_emotion_boost(
                memory.emotional_trace.primary.value
            )
            importance_boost = calculate_importance_boost(memory.importance)
            score = calculate_final_score(
                dist, time_decay, emotion_boost, importance_boost
            )

            search_results.append(
                MemorySearchResult(memory=memory, distance=dist, score=score)
            )

        search_results.sort(key=lambda r: r.score)
        return search_results[:n_results]

    async def recall(
        self,
        context: str,
        n_results: int = 3,
        valence_range: list[float] | None = None,
        arousal_range: list[float] | None = None,
    ) -> list[MemorySearchResult]:
        """Recall memories using semantic search + Hopfield hybrid.

        ChromaDB provides semantic candidates. Hopfield re-ranks using
        pattern completion for associative recall.
        """
        collection = self._ensure_connected()
        if collection.count() == 0:
            return []

        # Phase 1: semantic candidates (fetch more than needed for Hopfield)
        candidates = await self.search(
            context,
            n_results=max(n_results * 3, 10),
            valence_range=valence_range,
            arousal_range=arousal_range,
        )
        if not candidates:
            return []

        # Phase 2: load embeddings into Hopfield and re-rank
        try:
            candidate_ids = [r.memory.id for r in candidates]
            embed_results = collection.get(
                ids=candidate_ids,
                include=["embeddings"],
            )
            embeddings = embed_results.get("embeddings")

            if embeddings and len(embeddings) > 0:
                contents = [r.memory.content for r in candidates]
                self._hopfield.store(embeddings, candidate_ids, contents)

                # Get query embedding
                query_embeddings = self._embedding_fn([context])
                if query_embeddings and len(query_embeddings) > 0:
                    _, similarities = self._hopfield.retrieve(query_embeddings[0])

                    if similarities:
                        hopfield_results = self._hopfield.recall_results(
                            similarities, k=n_results
                        )

                        # Merge: combine semantic score with Hopfield score
                        id_to_semantic = {r.memory.id: r for r in candidates}
                        merged: list[MemorySearchResult] = []
                        for hr in hopfield_results:
                            if hr.memory_id in id_to_semantic:
                                sr = id_to_semantic[hr.memory_id]
                                # Blend scores: lower semantic + higher hopfield → better
                                blended_score = (
                                    sr.score * 0.6 + (1.0 - hr.hopfield_score) * 0.4
                                )
                                merged.append(
                                    MemorySearchResult(
                                        memory=sr.memory,
                                        distance=sr.distance,
                                        score=blended_score,
                                    )
                                )
                        if merged:
                            merged.sort(key=lambda r: r.score)
                            return merged[:n_results]
        except Exception as e:
            logger.warning("Hopfield recall fallback to semantic-only: %s", e)

        # Fallback: semantic-only
        return candidates[:n_results]

    async def list_recent(
        self, n: int = 10, category_filter: str | None = None
    ) -> list[Memory]:
        """List recent memories sorted by timestamp descending."""
        collection = self._ensure_connected()
        if collection.count() == 0:
            return []

        get_kwargs: dict[str, Any] = {
            "limit": min(n * 3, collection.count()),  # over-fetch to sort
            "include": ["documents", "metadatas"],
        }
        if category_filter:
            get_kwargs["where"] = {"category": category_filter}

        results = collection.get(**get_kwargs)

        memories: list[Memory] = []
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        for mid, doc, meta in zip(ids, docs, metas):
            memories.append(_memory_from_chromadb(mid, doc, meta))

        memories.sort(key=lambda m: m.timestamp, reverse=True)
        return memories[:n]

    async def get_by_id(self, memory_id: str) -> Memory | None:
        """Retrieve a specific memory by ID."""
        collection = self._ensure_connected()
        try:
            results = collection.get(
                ids=[memory_id],
                include=["documents", "metadatas"],
            )
            if not results["ids"]:
                return None
            return _memory_from_chromadb(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
            )
        except (KeyError, ValueError, IndexError) as e:
            logger.warning("Failed to get memory %s: %s", memory_id, e)
            return None
