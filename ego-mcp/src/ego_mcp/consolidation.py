"""Memory consolidation engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ego_mcp.memory import MemoryStore
    from ego_mcp.types import Memory

logger = logging.getLogger(__name__)


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
    merge_candidates: tuple[MergeCandidate, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "replay_events": self.replay_events,
            "coactivation_updates": self.coactivation_updates,
            "link_updates": self.link_updates,
            "refreshed_memories": self.refreshed_memories,
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

    async def run(
        self,
        store: "MemoryStore",
        window: int | None = None,
        window_hours: int = 24,
        max_replay_events: int = 100,
        merge_threshold: float = 0.10,
        max_merge_candidates: int = 5,
    ) -> ConsolidationStats:
        """Run consolidation over recent memories.

        Replays temporally adjacent memory pairs and creates
        similarity-based links between them.
        """
        effective_window = window if window is not None else window_hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, effective_window))
        recent = await store.list_recent(n=max_replay_events * 2)
        recent = self._collect_replay_targets(recent, cutoff)

        if not recent:
            return ConsolidationStats(
                replay_events=0,
                coactivation_updates=0,
                link_updates=0,
                refreshed_memories=0,
                merge_candidates=(),
            )

        replay_events = 0
        coactivation_updates = 0
        link_updates = 0
        refreshed_ids: set[str] = set()

        if len(recent) >= 2:
            for idx in range(len(recent) - 1):
                if replay_events >= max_replay_events:
                    break

                left = recent[idx]
                right = recent[idx + 1]

                # Try to create a bidirectional link
                created = await store.link_memories(left.id, right.id, "related")
                if created:
                    link_updates += 1
                updated = await store.bump_link_confidence(
                    left.id,
                    right.id,
                    delta=0.1,
                )
                if updated:
                    coactivation_updates += 1

                refreshed_ids.add(left.id)
                refreshed_ids.add(right.id)
                replay_events += 1

        merge_candidates: list[MergeCandidate] = []
        seen_pairs: set[tuple[str, str]] = set()
        for memory in recent:
            if len(merge_candidates) >= max_merge_candidates:
                break

            try:
                similar = await store.search(memory.content, n_results=3)
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "Merge candidate search failed for %s: %s", memory.id, exc
                )
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
            # Preserve the legacy summary shape for a single recent memory.
            refreshed_memories = 1

        return ConsolidationStats(
            replay_events=replay_events,
            coactivation_updates=coactivation_updates,
            link_updates=link_updates,
            refreshed_memories=refreshed_memories,
            merge_candidates=tuple(merge_candidates),
        )

    @staticmethod
    def _is_after(timestamp: str, cutoff: datetime) -> bool:
        try:
            ts = datetime.fromisoformat(timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts >= cutoff
        except ValueError:
            return False
