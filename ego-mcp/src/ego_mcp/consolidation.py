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
class ConsolidationStats:
    """Summary of consolidation run."""

    replay_events: int
    coactivation_updates: int
    link_updates: int
    refreshed_memories: int

    def to_dict(self) -> dict[str, int]:
        return {
            "replay_events": self.replay_events,
            "coactivation_updates": self.coactivation_updates,
            "link_updates": self.link_updates,
            "refreshed_memories": self.refreshed_memories,
        }


class ConsolidationEngine:
    """Replay recent memories and create links between co-occurring ones."""

    def __init__(self, embedding_provider: object | None = None) -> None:
        # Reserved for swapping replay/association strategy by provider.
        self._embedding_provider = embedding_provider

    @staticmethod
    def _collect_replay_targets(memories: Sequence["Memory"], cutoff: datetime) -> list["Memory"]:
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
    ) -> ConsolidationStats:
        """Run consolidation over recent memories.

        Replays temporally adjacent memory pairs and creates
        similarity-based links between them.
        """
        effective_window = window if window is not None else window_hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, effective_window))
        recent = await store.list_recent(n=max_replay_events * 2)
        recent = self._collect_replay_targets(recent, cutoff)

        if len(recent) < 2:
            return ConsolidationStats(0, 0, 0, len(recent))

        replay_events = 0
        coactivation_updates = 0
        link_updates = 0
        refreshed_ids: set[str] = set()

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

        return ConsolidationStats(
            replay_events=replay_events,
            coactivation_updates=coactivation_updates,
            link_updates=link_updates,
            refreshed_memories=len(refreshed_ids),
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
