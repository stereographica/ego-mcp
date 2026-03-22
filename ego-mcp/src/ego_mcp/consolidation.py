"""Memory consolidation engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Sequence

from ego_mcp import timezone_utils
from ego_mcp._memory_serialization import links_to_json

if TYPE_CHECKING:
    from ego_mcp.memory import MemoryStore
    from ego_mcp.types import Memory

logger = logging.getLogger(__name__)
_MAX_CLUSTER_NODES = 64
_MAX_CLUSTER_ITERATIONS = 10_000


@dataclass(frozen=True)
class MergeCandidate:
    """A pair of memories that are near-duplicates."""

    memory_a_id: str
    memory_b_id: str
    distance: float
    snippet_a: str
    snippet_b: str


@dataclass(frozen=True)
class ConsolidationStats:
    """Summary of consolidation run."""

    replay_events: int
    coactivation_updates: int
    link_updates: int
    refreshed_memories: int
    pruned_links: int = 0
    emotion_links: int = 0
    theme_links: int = 0
    cross_category_links: int = 0
    notions_created: int = 0
    detected_clusters: tuple[tuple[str, ...], ...] = ()
    merge_candidates: tuple[MergeCandidate, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "replay_events": self.replay_events,
            "coactivation_updates": self.coactivation_updates,
            "link_updates": self.link_updates,
            "refreshed_memories": self.refreshed_memories,
            "pruned_links": self.pruned_links,
            "emotion_links": self.emotion_links,
            "theme_links": self.theme_links,
            "cross_category_links": self.cross_category_links,
            "notions_created": self.notions_created,
            "detected_clusters": [list(cluster) for cluster in self.detected_clusters],
            "merge_candidates": [
                {
                    "memory_a_id": candidate.memory_a_id,
                    "memory_b_id": candidate.memory_b_id,
                    "distance": candidate.distance,
                    "snippet_a": candidate.snippet_a,
                    "snippet_b": candidate.snippet_b,
                }
                for candidate in self.merge_candidates
            ],
        }


def _detect_link_clusters(
    memories: Sequence["Memory"],
    min_cluster_size: int = 3,
    existing_clusters: set[frozenset[str]] | None = None,
    max_candidate_nodes: int = _MAX_CLUSTER_NODES,
    max_iterations: int = _MAX_CLUSTER_ITERATIONS,
) -> list[list[str]]:
    """Detect maximal fully connected memory clusters."""
    adjacency: dict[str, set[str]] = {
        memory.id: {link.target_id for link in memory.linked_ids}
        for memory in memories
    }
    candidate_ids = [
        memory_id
        for memory_id, neighbors in adjacency.items()
        if len(neighbors) >= max(0, min_cluster_size - 1)
    ]
    if len(candidate_ids) > max_candidate_nodes:
        candidate_ids = sorted(
            candidate_ids,
            key=lambda memory_id: (-len(adjacency[memory_id]), memory_id),
        )[:max_candidate_nodes]
        logger.warning(
            "Cluster detection limited to %s dense nodes out of %s candidates",
            max_candidate_nodes,
            len(adjacency),
        )
    candidate_set = set(candidate_ids)
    adjacency = {
        memory_id: adjacency[memory_id] & candidate_set for memory_id in candidate_ids
    }
    maximal: set[frozenset[str]] = set()
    iterations = 0
    exhausted = False

    def bron_kerbosch(r: set[str], p: set[str], x: set[str]) -> None:
        nonlocal iterations, exhausted
        if exhausted:
            return
        iterations += 1
        if iterations > max_iterations:
            exhausted = True
            return
        if not p and not x:
            if len(r) >= min_cluster_size:
                maximal.add(frozenset(r))
            return

        for vertex in list(p):
            neighbors = adjacency.get(vertex, set())
            bron_kerbosch(r | {vertex}, p & neighbors, x & neighbors)
            p.remove(vertex)
            x.add(vertex)

    bron_kerbosch(set(), set(adjacency), set())
    if exhausted:
        logger.warning(
            "Cluster detection stopped after reaching iteration limit (%s)",
            max_iterations,
        )
    excluded = existing_clusters or set()
    clusters = [sorted(cluster) for cluster in maximal if frozenset(cluster) not in excluded]
    clusters.sort()
    return clusters


class ConsolidationEngine:
    """Replay recent memories and create links between co-occurring ones."""

    def __init__(self, embedding_provider: object | None = None) -> None:
        # Reserved for swapping replay/association strategy by provider.
        self._embedding_provider = embedding_provider

    @staticmethod
    def _collect_replay_targets(
        memories: Sequence["Memory"], cutoff: datetime
    ) -> list["Memory"]:
        selected: list["Memory"] = []
        for memory in memories:
            if ConsolidationEngine._is_after(memory.timestamp, cutoff):
                selected.append(memory)
        return selected

    @staticmethod
    async def _prune_low_confidence_links(
        store: "MemoryStore",
        memories: Sequence["Memory"],
        threshold: float = 0.1,
    ) -> int:
        collection = store._ensure_connected()
        memory_map = {memory.id: memory for memory in memories}
        pair_keys: set[tuple[str, str]] = set()
        for memory in memories:
            for link in memory.linked_ids:
                if link.confidence < threshold:
                    if memory.id <= link.target_id:
                        pair_keys.add((memory.id, link.target_id))
                    else:
                        pair_keys.add((link.target_id, memory.id))

        pruned_links = 0
        for left_id, right_id in pair_keys:
            left = memory_map.get(left_id) or await store.get_by_id(left_id)
            right = memory_map.get(right_id) or await store.get_by_id(right_id)
            if left is None or right is None:
                continue

            left_before = len(left.linked_ids)
            right_before = len(right.linked_ids)
            left.linked_ids = [link for link in left.linked_ids if link.target_id != right_id]
            right.linked_ids = [link for link in right.linked_ids if link.target_id != left_id]
            removed = (left_before - len(left.linked_ids)) + (right_before - len(right.linked_ids))
            if removed == 0:
                continue

            pruned_links += removed
            collection.update(
                ids=[left.id, right.id],
                metadatas=[
                    {"linked_ids": links_to_json(left.linked_ids)},
                    {"linked_ids": links_to_json(right.linked_ids)},
                ],
            )
            memory_map[left.id] = left
            memory_map[right.id] = right

        return pruned_links

    @staticmethod
    def _iter_pairs(memories: Sequence["Memory"]) -> list[tuple["Memory", "Memory"]]:
        pairs: list[tuple["Memory", "Memory"]] = []
        for left_idx, left in enumerate(memories):
            for right in memories[left_idx + 1 :]:
                pairs.append((left, right))
        return pairs

    async def run(
        self,
        store: "MemoryStore",
        window: int | None = None,
        window_hours: int = 24,
        max_replay_events: int = 100,
        merge_threshold: float = 0.10,
        max_merge_candidates: int = 5,
        existing_clusters: set[frozenset[str]] | None = None,
    ) -> ConsolidationStats:
        """Run consolidation over recent memories.

        Replays temporally adjacent memories and expands links using
        emotional, thematic, and cross-category similarity.
        """
        effective_window = window if window is not None else window_hours
        cutoff = timezone_utils.now() - timedelta(hours=max(1, effective_window))
        all_memories = await store.list_recent(
            n=max(store.collection_count(), max_replay_events * 2)
        )
        pruned_links = await self._prune_low_confidence_links(store, all_memories)
        recent = self._collect_replay_targets(all_memories, cutoff)

        if not recent:
            return ConsolidationStats(
                replay_events=0,
                coactivation_updates=0,
                link_updates=0,
                refreshed_memories=0,
                pruned_links=pruned_links,
                emotion_links=0,
                theme_links=0,
                cross_category_links=0,
                notions_created=0,
                detected_clusters=(),
                merge_candidates=(),
            )

        replay_events = 0
        coactivation_updates = 0
        link_updates = 0
        emotion_links = 0
        theme_links = 0
        cross_category_links = 0
        refreshed_ids: set[str] = set()

        if len(recent) >= 2:
            for idx in range(len(recent) - 1):
                if replay_events >= max_replay_events:
                    break

                left = recent[idx]
                right = recent[idx + 1]

                created = await store.link_memories(left.id, right.id, "related")
                if created:
                    link_updates += 1
                updated = await store.bump_link_confidence(left.id, right.id, delta=0.1)
                if updated:
                    coactivation_updates += 1

                refreshed_ids.add(left.id)
                refreshed_ids.add(right.id)
                replay_events += 1

        for left, right in self._iter_pairs(recent):
            if (
                left.emotional_trace.primary == right.emotional_trace.primary
                and abs(left.emotional_trace.intensity - right.emotional_trace.intensity) < 0.2
            ):
                if await store.link_memories(left.id, right.id, "similar"):
                    emotion_links += 1
                    link_updates += 1

            if len(set(left.tags) & set(right.tags)) >= 2:
                if await store.link_memories(left.id, right.id, "related"):
                    theme_links += 1
                    link_updates += 1

        semantic_distances: dict[str, dict[str, float]] = {}
        for left, right in self._iter_pairs(recent):
            if left.category == right.category:
                continue
            cached = semantic_distances.get(left.id)
            if cached is None:
                cached = {}
                search_results = await store.search(left.content, n_results=len(recent))
                for result in search_results:
                    cached[result.memory.id] = result.distance
                semantic_distances[left.id] = cached
            distance = cached.get(right.id)
            if distance is not None and distance < 0.25:
                if await store.link_memories(left.id, right.id, "related"):
                    cross_category_links += 1
                    link_updates += 1

        merge_candidates: list[MergeCandidate] = []
        seen_pairs: set[tuple[str, str]] = set()
        for memory in recent:
            if len(merge_candidates) >= max_merge_candidates:
                break

            try:
                similar = await store.search(memory.content, n_results=3)
            except (ValueError, KeyError) as exc:
                logger.warning("Merge candidate search failed for %s: %s", memory.id, exc)
                continue

            for result in similar:
                if result.memory.id == memory.id:
                    continue
                if result.distance >= merge_threshold:
                    continue

                if memory.id <= result.memory.id:
                    pair_key = (memory.id, result.memory.id)
                else:
                    pair_key = (result.memory.id, memory.id)
                if pair_key in seen_pairs:
                    continue

                seen_pairs.add(pair_key)
                merge_candidates.append(
                    MergeCandidate(
                        memory_a_id=memory.id,
                        memory_b_id=result.memory.id,
                        distance=result.distance,
                        snippet_a=memory.content[:100],
                        snippet_b=result.memory.content[:100],
                    )
                )
                if len(merge_candidates) >= max_merge_candidates:
                    break

        refreshed_memories = len(refreshed_ids)
        if len(recent) == 1:
            refreshed_memories = 1

        updated_recent = await store.list_recent(n=max(store.collection_count(), len(recent)))
        detected_clusters = tuple(
            tuple(cluster)
            for cluster in _detect_link_clusters(
                updated_recent,
                existing_clusters=existing_clusters,
            )
        )

        return ConsolidationStats(
            replay_events=replay_events,
            coactivation_updates=coactivation_updates,
            link_updates=link_updates,
            refreshed_memories=refreshed_memories,
            pruned_links=pruned_links,
            emotion_links=emotion_links,
            theme_links=theme_links,
            cross_category_links=cross_category_links,
            notions_created=0,
            detected_clusters=detected_clusters,
            merge_candidates=tuple(merge_candidates),
        )

    @staticmethod
    def _is_after(timestamp: str, cutoff: datetime) -> bool:
        try:
            ts = datetime.fromisoformat(timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone_utils.app_timezone())
            return ts >= cutoff
        except ValueError:
            return False
