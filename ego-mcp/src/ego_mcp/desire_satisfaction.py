"""Desire satisfaction inference from remember content (§5).

When a positive experience is remembered (valence > 0.2, intensity > 0.3),
compare the content against each desire's satisfaction_signals via embedding
similarity.  Desires exceeding the similarity threshold are partially
satisfied with quality = similarity * 0.5.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Callable
from pathlib import Path

from ego_mcp.desire_catalog import DesireCatalog

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_SIMILARITY_THRESHOLD = 0.6


class SignalEmbeddingCache:
    """Caches satisfaction-signal embeddings to disk.

    Signal texts are derived from the desire catalog and rarely change.
    By persisting their embeddings, ``remember`` only needs to embed the
    content text (1 API call) instead of content + all signals.

    The cache is keyed by a SHA-256 fingerprint of the sorted signal texts.
    When the catalog changes (via ``configure_desires`` or direct edit of
    ``desires.json``), the fingerprint misses and embeddings are recomputed.
    """

    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._fingerprint: str = ""
        self._signals: list[tuple[str, str]] = []
        self._embeddings: list[list[float]] = []
        self._load()

    # -- public API --------------------------------------------------

    def get(
        self,
        catalog: DesireCatalog,
        embed_fn: Callable[[list[str]], list[list[float]]],
    ) -> tuple[list[tuple[str, str]], list[list[float]]]:
        """Return (signals, embeddings), using cache when possible."""
        fp = _compute_fingerprint(catalog)
        if fp == self._fingerprint and self._embeddings:
            return self._signals, self._embeddings

        signals: list[tuple[str, str]] = []
        for desire_id, config in catalog.fixed_desires.items():
            for signal in config.satisfaction_signals:
                signals.append((desire_id, signal))

        if not signals:
            self._fingerprint = fp
            self._signals = []
            self._embeddings = []
            return [], []

        embeddings = embed_fn([sig for _, sig in signals])

        self._fingerprint = fp
        self._signals = signals
        self._embeddings = embeddings
        self._save()
        return signals, embeddings

    # -- persistence -------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._fingerprint = data.get("fingerprint", "")
            self._signals = [(s[0], s[1]) for s in data.get("signals", [])]
            self._embeddings = data.get("embeddings", [])
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("Signal embedding cache load failed: %s", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprint": self._fingerprint,
            "signals": [list(s) for s in self._signals],
            "embeddings": self._embeddings,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)


def _compute_fingerprint(catalog: DesireCatalog) -> str:
    """SHA-256 of sorted signal texts.  Deterministic across restarts."""
    parts: list[str] = []
    for desire_id, config in sorted(catalog.fixed_desires.items()):
        for signal in sorted(config.satisfaction_signals):
            parts.append(f"{desire_id}:{signal}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def infer_desire_satisfaction(
    content: str,
    valence: float,
    intensity: float,
    catalog: DesireCatalog,
    embed_fn: Callable[[list[str]], list[list[float]]],
    signal_cache: SignalEmbeddingCache | None = None,
) -> list[tuple[str, float]]:
    """Infer which desires are partially satisfied by a remembered experience.

    Preconditions (AND):
      - valence > 0.2   (positive emotional experience)
      - intensity > 0.3  (with felt sense)

    Returns (desire_id, quality) pairs sorted by quality descending.
    """
    if valence <= 0.2 or intensity <= 0.3:
        return []

    if signal_cache is not None:
        desire_signals, signal_embeddings = signal_cache.get(catalog, embed_fn)
        if not desire_signals:
            return []
        content_embedding = embed_fn([content])[0]
    else:
        desire_signals = []
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
