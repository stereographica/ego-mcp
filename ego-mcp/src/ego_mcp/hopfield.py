"""Modern Hopfield Network for associative memory retrieval.

Ported from embodied-claude/memory-mcp/src/memory_mcp/hopfield.py.
Uses Modern Continuous Hopfield Networks (Ramsauer et al., 2020).
"""

from __future__ import annotations
# mypy: disable-error-code=import-not-found

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HopfieldRecallResult:
    """Single recall result from Hopfield retrieval."""

    memory_id: str
    content: str
    similarity: float
    hopfield_score: float


@dataclass
class HopfieldState:
    """Internal state of stored patterns."""

    patterns: np.ndarray  # (n_memories, dim), L2-normalized
    ids: list[str]
    contents: list[str]
    n_memories: int = field(init=False)
    dim: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_memories, self.dim = self.patterns.shape


class ModernHopfieldNetwork:
    """Modern Hopfield Network (continuous version).

    Update rule: ξ_new = R^T · softmax(β · R · ξ)
    Exponential memory capacity O(2^(dim/2)).
    """

    def __init__(self, beta: float = 4.0, n_iters: int = 3) -> None:
        self.beta = beta
        self.n_iters = n_iters
        self._state: HopfieldState | None = None

    def store(
        self,
        embeddings: list[list[float]],
        ids: list[str],
        contents: list[str],
    ) -> None:
        """Store embedding patterns for retrieval."""
        if not embeddings:
            logger.warning("Hopfield: No embeddings provided, skipping store.")
            self._state = None
            return

        arr = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms < 1e-8, 1.0, norms)
        normalized = arr / norms

        self._state = HopfieldState(
            patterns=normalized,
            ids=list(ids),
            contents=list(contents),
        )
        logger.debug(
            "Hopfield: stored %d patterns, dim=%d, beta=%.2f",
            self._state.n_memories,
            self._state.dim,
            self.beta,
        )

    def retrieve(self, query_embedding: list[float]) -> tuple[np.ndarray, list[float]]:
        """Retrieve via Hopfield update rule.

        Returns:
            (converged_pattern, similarities_per_memory)
        """
        if self._state is None:
            return np.array(query_embedding, dtype=np.float32), []

        patterns = self._state.patterns
        xi = np.array(query_embedding, dtype=np.float32)

        norm = np.linalg.norm(xi)
        if norm > 1e-8:
            xi = xi / norm

        for iteration in range(self.n_iters):
            scores = patterns @ xi
            scores_scaled = self.beta * scores
            scores_scaled = scores_scaled - scores_scaled.max()
            weights = np.exp(scores_scaled)
            weights = weights / (weights.sum() + 1e-12)

            xi_new = patterns.T @ weights
            norm_new = np.linalg.norm(xi_new)
            if norm_new > 1e-8:
                xi_new = xi_new / norm_new

            delta = np.linalg.norm(xi_new - xi)
            xi = xi_new
            if delta < 1e-5:
                break

        similarities = (patterns @ xi).tolist()
        return xi, similarities

    def find_top_k(
        self, similarities: list[float], k: int = 5
    ) -> list[tuple[int, float]]:
        """Return top-k indices and similarities (descending)."""
        if not similarities:
            return []

        arr = np.array(similarities)
        k = min(k, len(arr))
        top_indices = np.argsort(arr)[-k:][::-1]
        return [(int(i), float(arr[i])) for i in top_indices]

    def recall_results(
        self, similarities: list[float], k: int = 5
    ) -> list[HopfieldRecallResult]:
        """Return structured recall results."""
        if self._state is None:
            return []

        top_k = self.find_top_k(similarities, k)
        results = []
        for idx, sim in top_k:
            if 0 <= idx < self._state.n_memories:
                results.append(
                    HopfieldRecallResult(
                        memory_id=self._state.ids[idx],
                        content=self._state.contents[idx],
                        similarity=sim,
                        hopfield_score=sim,
                    )
                )
        return results

    @property
    def is_loaded(self) -> bool:
        return self._state is not None

    @property
    def n_memories(self) -> int:
        return self._state.n_memories if self._state else 0

    @property
    def dim(self) -> int:
        return self._state.dim if self._state else 0
