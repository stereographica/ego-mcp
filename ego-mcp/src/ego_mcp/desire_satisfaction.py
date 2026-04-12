"""Desire satisfaction inference from remember content (§5).

When a positive experience is remembered (valence > 0.2, intensity > 0.3),
compare the content against each desire's satisfaction_signals via embedding
similarity.  Desires exceeding the similarity threshold are partially
satisfied with quality = similarity * 0.5.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ego_mcp.desire_catalog import DesireCatalog


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_SIMILARITY_THRESHOLD = 0.6


def infer_desire_satisfaction(
    content: str,
    valence: float,
    intensity: float,
    catalog: DesireCatalog,
    embed_fn: Callable[[list[str]], list[list[float]]],
) -> list[tuple[str, float]]:
    """Infer which desires are partially satisfied by a remembered experience.

    Preconditions (AND):
      - valence > 0.2   (positive emotional experience)
      - intensity > 0.3  (with felt sense)

    Returns (desire_id, quality) pairs sorted by quality descending.
    """
    if valence <= 0.2 or intensity <= 0.3:
        return []

    desire_signals: list[tuple[str, str]] = []
    for desire_id, config in catalog.fixed_desires.items():
        for signal in config.satisfaction_signals:
            desire_signals.append((desire_id, signal))

    if not desire_signals:
        return []

    texts = [content] + [signal for _, signal in desire_signals]
    embeddings = embed_fn(texts)

    content_embedding = embeddings[0]
    signal_embeddings = embeddings[1:]

    best_per_desire: dict[str, float] = {}
    for i, (desire_id, _) in enumerate(desire_signals):
        sim = _cosine_similarity(content_embedding, signal_embeddings[i])
        if sim > best_per_desire.get(desire_id, 0.0):
            best_per_desire[desire_id] = sim

    results: list[tuple[str, float]] = []
    for desire_id, similarity in best_per_desire.items():
        if similarity > _SIMILARITY_THRESHOLD:
            quality = similarity * 0.5
            results.append((desire_id, quality))

    return sorted(results, key=lambda x: -x[1])
