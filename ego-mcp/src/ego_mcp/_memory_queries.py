"""Query-oriented operations used by MemoryStore."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ego_mcp._memory_scoring import (
    calculate_emotion_boost,
    calculate_final_score,
    calculate_importance_boost,
    calculate_time_decay,
)
from ego_mcp._memory_serialization import links_to_json, memory_from_chromadb
from ego_mcp.types import Memory, MemorySearchResult

if TYPE_CHECKING:
    from ego_mcp._memory_store import MemoryStore

logger = logging.getLogger(__name__)


async def search(
    store: MemoryStore,
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
    collection = store._ensure_connected()

    where_clauses: list[dict[str, Any]] = []
    if emotion_filter:
        where_clauses.append({"emotion": emotion_filter})
    if category_filter:
        where_clauses.append({"category": category_filter})

    collection_count = collection.count()
    if collection_count == 0:
        return []

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
        memory = memory_from_chromadb(mid, doc, meta)

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
        emotion_boost = calculate_emotion_boost(memory.emotional_trace.primary.value)
        importance_boost = calculate_importance_boost(memory.importance)
        score = calculate_final_score(dist, time_decay, emotion_boost, importance_boost)

        search_results.append(
            MemorySearchResult(memory=memory, distance=dist, score=score)
        )

    search_results.sort(key=lambda r: r.score)
    return search_results[:n_results]


async def recall(
    store: MemoryStore,
    context: str,
    n_results: int = 3,
    valence_range: list[float] | None = None,
    arousal_range: list[float] | None = None,
) -> list[MemorySearchResult]:
    """Recall memories using semantic search + Hopfield hybrid."""
    collection = store._ensure_connected()
    if collection.count() == 0:
        return []

    candidates = await search(
        store,
        context,
        n_results=max(n_results * 3, 10),
        valence_range=valence_range,
        arousal_range=arousal_range,
    )
    if not candidates:
        return []

    try:
        candidate_ids = [r.memory.id for r in candidates]
        embed_results = collection.get(
            ids=candidate_ids,
            include=["embeddings"],
        )
        embeddings = embed_results.get("embeddings")

        if embeddings and len(embeddings) > 0:
            contents = [r.memory.content for r in candidates]
            store._hopfield.store(embeddings, candidate_ids, contents)

            query_embeddings = store._embedding_fn([context])
            if query_embeddings and len(query_embeddings) > 0:
                _, similarities = store._hopfield.retrieve(query_embeddings[0])

                if similarities:
                    hopfield_results = store._hopfield.recall_results(
                        similarities, k=n_results
                    )

                    id_to_semantic = {r.memory.id: r for r in candidates}
                    merged: list[MemorySearchResult] = []
                    for hr in hopfield_results:
                        if hr.memory_id in id_to_semantic:
                            sr = id_to_semantic[hr.memory_id]
                            blended_score = sr.score * 0.6 + (1.0 - hr.hopfield_score) * 0.4
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

    return candidates[:n_results]


async def list_recent(
    store: MemoryStore,
    n: int = 10,
    category_filter: str | None = None,
) -> list[Memory]:
    """List recent memories sorted by timestamp descending."""
    collection = store._ensure_connected()
    total = int(collection.count())
    if total == 0:
        return []

    get_kwargs: dict[str, Any] = {
        "limit": total,
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
        memories.append(memory_from_chromadb(mid, doc, meta))

    memories.sort(key=lambda m: m.timestamp, reverse=True)
    return memories[:n]


async def get_by_id(store: MemoryStore, memory_id: str) -> Memory | None:
    """Retrieve a specific memory by ID."""
    collection = store._ensure_connected()
    try:
        results = collection.get(
            ids=[memory_id],
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            return None
        return memory_from_chromadb(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
        )
    except (KeyError, ValueError, IndexError) as e:
        logger.warning("Failed to get memory %s: %s", memory_id, e)
        return None


async def delete(store: MemoryStore, memory_id: str) -> Memory | None:
    """Delete a memory and clean reverse links from linked targets."""
    collection = store._ensure_connected()
    memory = await get_by_id(store, memory_id)
    if memory is None:
        return None

    for link in memory.linked_ids:
        target = await get_by_id(store, link.target_id)
        if target is None:
            continue
        cleaned_links = [
            existing for existing in target.linked_ids if existing.target_id != memory_id
        ]
        if len(cleaned_links) == len(target.linked_ids):
            continue
        collection.update(
            ids=[target.id],
            metadatas=[{"linked_ids": links_to_json(cleaned_links)}],
        )

    collection.delete(ids=[memory_id])
    return memory
