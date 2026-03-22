"""Query-oriented operations used by MemoryStore."""

from __future__ import annotations

import logging
import random
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
_SPREAD_WEIGHT = 0.3
_DORMANT_DECAY_THRESHOLD = 0.3
PROUST_PROBABILITY = 0.25


def _max_link_confidence(memory: Memory) -> float:
    return max((link.confidence for link in memory.linked_ids), default=0.0)


def _scored_result(memory: Memory, distance: float) -> MemorySearchResult:
    decay = calculate_time_decay(
        memory.timestamp,
        link_confidence_max=_max_link_confidence(memory),
        access_count=memory.access_count,
    )
    emotion_boost = calculate_emotion_boost(memory.emotional_trace.primary.value)
    importance_boost = calculate_importance_boost(memory.importance)
    score = calculate_final_score(distance, decay, emotion_boost, importance_boost)
    return MemorySearchResult(
        memory=memory,
        distance=distance,
        score=score,
        decay=decay,
    )


def _raw_semantic_result(memory: Memory, distance: float) -> MemorySearchResult:
    decay = calculate_time_decay(
        memory.timestamp,
        link_confidence_max=_max_link_confidence(memory),
        access_count=memory.access_count,
    )
    return MemorySearchResult(
        memory=memory,
        distance=distance,
        score=distance,
        decay=decay,
    )


async def _increment_access_metadata(
    store: MemoryStore,
    results: list[MemorySearchResult],
) -> None:
    collection = store._ensure_connected()
    seen_ids: set[str] = set()
    for result in results:
        memory = result.memory
        if memory.id in seen_ids:
            continue
        seen_ids.add(memory.id)
        memory.access_count += 1
        memory.last_accessed = Memory.now_iso()
        collection.update(
            ids=[memory.id],
            metadatas=[
                {
                    "access_count": memory.access_count,
                    "last_accessed": memory.last_accessed,
                }
            ],
        )


async def _query_semantic_results(
    store: MemoryStore,
    query: str,
    n_results: int,
    *,
    raw_distance_only: bool = False,
) -> list[MemorySearchResult]:
    collection = store._ensure_connected()
    collection_count = int(collection.count())
    if collection_count == 0:
        return []

    raw = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection_count),
        include=["documents", "metadatas", "distances"],
    )
    ids = raw.get("ids", [[]])[0]
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    results: list[MemorySearchResult] = []
    for memory_id, doc, meta, distance in zip(ids, docs, metas, distances):
        memory = memory_from_chromadb(memory_id, doc, meta)
        distance_value = float(distance)
        if raw_distance_only:
            results.append(_raw_semantic_result(memory, distance_value))
        else:
            results.append(_scored_result(memory, distance_value))
    results.sort(key=lambda item: item.distance if raw_distance_only else item.score)
    return results


async def _sample_dormant_memories(
    store: MemoryStore,
    query: str,
    decay_threshold: float = _DORMANT_DECAY_THRESHOLD,
    max_candidates: int = 5,
    valence_range: list[float] | None = None,
    arousal_range: list[float] | None = None,
) -> list[MemorySearchResult]:
    candidates = await _query_semantic_results(
        store,
        query,
        n_results=30,
        raw_distance_only=True,
    )
    if valence_range is not None and len(valence_range) == 2:
        low, high = min(valence_range), max(valence_range)
        candidates = [
            result
            for result in candidates
            if low <= result.memory.emotional_trace.valence <= high
        ]
    if arousal_range is not None and len(arousal_range) == 2:
        low, high = min(arousal_range), max(arousal_range)
        candidates = [
            result
            for result in candidates
            if low <= result.memory.emotional_trace.arousal <= high
        ]
    dormant = [result for result in candidates if result.decay < decay_threshold]
    return dormant[:max_candidates]


async def find_resurfacing_memories(
    store: MemoryStore,
    query: str,
    decay_threshold: float = _DORMANT_DECAY_THRESHOLD,
    similarity_threshold: float = 0.4,
    max_results: int = 2,
    exclude_ids: set[str] | None = None,
) -> list[MemorySearchResult]:
    excluded = exclude_ids or set()
    candidates = await _query_semantic_results(store, query, n_results=20)
    resurfacing = [
        result
        for result in candidates
        if result.memory.id not in excluded
        and result.decay < decay_threshold
        and result.distance < similarity_threshold
    ][:max_results]
    if resurfacing:
        await _increment_access_metadata(store, resurfacing)
    return resurfacing


async def _apply_spreading_activation(
    store: MemoryStore,
    base_results: list[MemorySearchResult],
    n_results: int,
) -> list[MemorySearchResult]:
    if not base_results:
        return []

    existing_ids = {result.memory.id for result in base_results}
    spread_candidates: dict[str, MemorySearchResult] = {}
    for source in base_results:
        for link in source.memory.linked_ids:
            if link.target_id in existing_ids:
                continue
            target = await get_by_id(store, link.target_id)
            if target is None:
                continue
            target_result = _scored_result(target, source.distance)
            target_result.score = max(
                0.0,
                target_result.score
                * (1.0 - max(0.0, min(1.0, link.confidence)) * _SPREAD_WEIGHT),
            )
            current = spread_candidates.get(target.id)
            if current is None or target_result.score < current.score:
                spread_candidates[target.id] = target_result

    expanded = [*base_results, *spread_candidates.values()]
    expanded.sort(key=lambda result: result.score)
    return expanded[:n_results]


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

        search_results.append(_scored_result(memory, float(dist)))

    search_results.sort(key=lambda r: r.score)
    return search_results[:n_results]


async def recall(
    store: MemoryStore,
    context: str,
    n_results: int = 3,
    emotion_filter: str | None = None,
    category_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    valence_range: list[float] | None = None,
    arousal_range: list[float] | None = None,
    proust_probability: float = PROUST_PROBABILITY,
) -> list[MemorySearchResult]:
    """Recall memories using semantic search + Hopfield hybrid."""
    store._last_recall_metadata = {}
    collection = store._ensure_connected()
    if collection.count() == 0:
        return []

    explicit_filters = bool(emotion_filter or category_filter or date_from or date_to)
    if explicit_filters:
        results = await search(
            store,
            context,
            n_results=n_results,
            emotion_filter=emotion_filter,
            category_filter=category_filter,
            date_from=date_from,
            date_to=date_to,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )
        if results:
            await _increment_access_metadata(store, results)
        store._last_recall_metadata = {
            "fuzzy_recall_count": sum(1 for result in results if result.decay < 0.5),
            "proust_triggered": False,
            "proust_memory_id": None,
            "proust_memory_decay": None,
        }
        return results

    candidates = await search(
        store,
        context,
        n_results=max(n_results * 3, 10),
        valence_range=valence_range,
        arousal_range=arousal_range,
    )
    if not candidates:
        return []

    dormant_candidates = await _sample_dormant_memories(
        store,
        context,
        valence_range=valence_range,
        arousal_range=arousal_range,
    )
    candidate_pool: list[MemorySearchResult] = []
    seen_candidate_ids: set[str] = set()
    for result in [*candidates, *dormant_candidates]:
        if result.memory.id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(result.memory.id)
        candidate_pool.append(result)

    hopfield_scores: dict[str, float] = {}
    base_results = candidates[:n_results]
    try:
        candidate_ids = [result.memory.id for result in candidate_pool]
        embed_results = collection.get(
            ids=candidate_ids,
            include=["embeddings"],
        )
        embeddings = embed_results.get("embeddings")

        if embeddings and len(embeddings) > 0:
            contents = [result.memory.content for result in candidate_pool]
            store._hopfield.store(embeddings, candidate_ids, contents)

            query_embeddings = store._embedding_fn([context])
            if query_embeddings and len(query_embeddings) > 0:
                _, similarities = store._hopfield.retrieve(query_embeddings[0])

                if similarities:
                    hopfield_results = store._hopfield.recall_results(
                        similarities, k=len(candidate_ids)
                    )
                    hopfield_scores = {
                        result.memory_id: result.hopfield_score for result in hopfield_results
                    }

                    id_to_semantic = {result.memory.id: result for result in candidate_pool}
                    merged: list[MemorySearchResult] = []
                    for hopfield_result in hopfield_results:
                        semantic_result = id_to_semantic.get(hopfield_result.memory_id)
                        if semantic_result is None:
                            continue
                        blended_score = semantic_result.score * 0.6 + (
                            1.0 - hopfield_result.hopfield_score
                        ) * 0.4
                        merged.append(
                            MemorySearchResult(
                                memory=semantic_result.memory,
                                distance=semantic_result.distance,
                                score=blended_score,
                                decay=semantic_result.decay,
                            )
                        )
                    if merged:
                        merged.sort(key=lambda result: result.score)
                        base_results = merged[:n_results]
    except Exception as exc:
        logger.warning("Hopfield recall fallback to semantic-only: %s", exc)

    base_results = await _apply_spreading_activation(store, base_results, n_results)

    proust_result: MemorySearchResult | None = None
    if dormant_candidates and random.random() < proust_probability:
        ranked_dormant = sorted(
            dormant_candidates,
            key=lambda result: hopfield_scores.get(result.memory.id, 0.0),
            reverse=True,
        )
        visible_ids = {result.memory.id for result in base_results}
        for candidate in ranked_dormant:
            if candidate.memory.id in visible_ids:
                continue
            proust_result = MemorySearchResult(
                memory=candidate.memory,
                distance=candidate.distance,
                score=candidate.score,
                decay=candidate.decay,
                is_proust=True,
            )
            base_results = [
                *base_results,
                proust_result,
            ]
            break

    if base_results:
        await _increment_access_metadata(store, base_results)
    store._last_recall_metadata = {
        "fuzzy_recall_count": sum(1 for result in base_results if result.decay < 0.5),
        "proust_triggered": proust_result is not None,
        "proust_memory_id": proust_result.memory.id if proust_result is not None else None,
        "proust_memory_decay": (
            proust_result.decay if proust_result is not None else None
        ),
    }
    return base_results


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

    memories.sort(key=lambda memory: memory.timestamp, reverse=True)
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
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("Failed to get memory %s: %s", memory_id, exc)
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
