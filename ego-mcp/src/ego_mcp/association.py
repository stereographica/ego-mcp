"""Associative expansion for memory recall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ego_mcp.memory import MemoryStore


@dataclass(frozen=True)
class AssociationResult:
    """Expanded candidate memory with provenance score."""

    memory_id: str
    score: float
    depth: int
    source: str


class AssociationEngine:
    """Expand candidates from seed memories using explicit and implicit links."""

    def __init__(
        self, explicit_weight: float = 1.0, implicit_weight: float = 0.7
    ) -> None:
        self._explicit_weight = explicit_weight
        self._implicit_weight = implicit_weight

    async def spread(
        self,
        seed_ids: list[str],
        memory_store: "MemoryStore",
        depth: int = 2,
        top_k: int = 10,
    ) -> list[AssociationResult]:
        if not seed_ids or depth <= 0 or top_k <= 0:
            return []

        seed_set = set(seed_ids)
        visited: set[str] = set(seed_ids)
        frontier: list[tuple[str, int]] = [(mid, 0) for mid in seed_ids]
        scored: dict[str, AssociationResult] = {}

        while frontier:
            current_id, current_depth = frontier.pop(0)
            if current_depth >= depth:
                continue

            current_memory = await memory_store.get_by_id(current_id)
            if current_memory is None:
                continue

            for link in current_memory.linked_ids:
                candidate_id = link.target_id
                if not candidate_id:
                    continue
                score = self._explicit_weight * max(0.0, min(1.0, link.confidence))
                if score <= 0.0:
                    continue
                self._update_result(
                    scored, candidate_id, score, current_depth + 1, "explicit"
                )
                if candidate_id not in visited:
                    visited.add(candidate_id)
                    frontier.append((candidate_id, current_depth + 1))

            implicit = await memory_store.search(
                current_memory.content,
                n_results=max(top_k + 1, 5),
            )
            for item in implicit:
                candidate_id = item.memory.id
                if candidate_id == current_id:
                    continue
                score = self._implicit_weight * max(0.0, min(1.0, 1.0 - item.distance))
                if score <= 0.0:
                    continue
                self._update_result(
                    scored, candidate_id, score, current_depth + 1, "implicit"
                )
                if candidate_id not in visited:
                    visited.add(candidate_id)
                    frontier.append((candidate_id, current_depth + 1))

        results = [
            result for memory_id, result in scored.items() if memory_id not in seed_set
        ]
        results.sort(key=lambda r: (-r.score, r.depth, r.memory_id))
        return results[:top_k]

    @staticmethod
    def _update_result(
        scored: dict[str, AssociationResult],
        memory_id: str,
        score: float,
        depth: int,
        source: str,
    ) -> None:
        existing = scored.get(memory_id)
        if existing is None or score > existing.score:
            scored[memory_id] = AssociationResult(
                memory_id=memory_id,
                score=score,
                depth=depth,
                source=source,
            )
