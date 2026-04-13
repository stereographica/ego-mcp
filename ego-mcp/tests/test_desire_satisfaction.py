"""Tests for desire satisfaction inference from remember content (§5)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from ego_mcp.desire_catalog import (
    DesireCatalog,
    DesireSentenceConfig,
    EmergentDesireConfig,
    FixedDesireConfig,
    default_desire_catalog,
)
from ego_mcp.desire_satisfaction import (
    SignalEmbeddingCache,
    _compute_fingerprint,
    _cosine_similarity,
    infer_desire_satisfaction,
)


def _make_catalog(
    signals: dict[str, list[str]],
) -> DesireCatalog:
    """Minimal catalog with specified satisfaction signals per desire."""
    fixed = {}
    for desire_id, sigs in signals.items():
        fixed[desire_id] = FixedDesireConfig(
            satisfaction_hours=24.0,
            maslow_level=3,
            sentence=DesireSentenceConfig(
                rising="r",
                steady="s",
                settling="t",
            ),
            satisfaction_signals=sigs,
        )
    return DesireCatalog(
        version=2,
        fixed_desires=fixed,
        emergent=EmergentDesireConfig(
            satisfaction_hours=12.0,
            expiry_hours=72.0,
            satisfied_ttl_hours=4.0,
        ),
    )


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_negative_correlation(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


class TestInferDesireSatisfaction:
    """§5.2: valence > 0.2 AND intensity > 0.3 gate, similarity > 0.6, quality = sim * 0.5."""

    def test_low_valence_returns_empty(self) -> None:
        catalog = _make_catalog({"d1": ["signal"]})
        result = infer_desire_satisfaction(
            "text", 0.1, 0.5, catalog, lambda t: [[1.0]] * len(t)
        )
        assert result == []

    def test_low_intensity_returns_empty(self) -> None:
        catalog = _make_catalog({"d1": ["signal"]})
        result = infer_desire_satisfaction(
            "text", 0.5, 0.2, catalog, lambda t: [[1.0]] * len(t)
        )
        assert result == []

    def test_boundary_valence_excluded(self) -> None:
        """valence == 0.2 must NOT trigger (strictly greater)."""
        catalog = _make_catalog({"d1": ["signal"]})
        result = infer_desire_satisfaction(
            "text", 0.2, 0.5, catalog, lambda t: [[1.0]] * len(t)
        )
        assert result == []

    def test_boundary_intensity_excluded(self) -> None:
        """intensity == 0.3 must NOT trigger (strictly greater)."""
        catalog = _make_catalog({"d1": ["signal"]})
        result = infer_desire_satisfaction(
            "text", 0.5, 0.3, catalog, lambda t: [[1.0]] * len(t)
        )
        assert result == []

    def test_high_similarity_returns_satisfaction(self) -> None:
        catalog = _make_catalog({"desire_a": ["matching signal"]})

        def embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        results = infer_desire_satisfaction("content", 0.5, 0.5, catalog, embed)
        assert len(results) == 1
        assert results[0][0] == "desire_a"
        assert results[0][1] == pytest.approx(0.5)  # sim=1.0 * 0.5

    def test_quality_equals_similarity_times_half(self) -> None:
        """§5.2: quality = similarity * 0.5."""
        catalog = _make_catalog({"d1": ["sig"]})

        def embed(texts: list[str]) -> list[list[float]]:
            vecs = []
            for i in range(len(texts)):
                if i == 0:
                    vecs.append([1.0, 0.0, 0.0])
                else:
                    vecs.append([0.8, 0.2, 0.0])
            return vecs

        results = infer_desire_satisfaction("c", 0.5, 0.5, catalog, embed)
        expected_sim = (0.8) / (1.0 * math.sqrt(0.68))
        assert results[0][1] == pytest.approx(expected_sim * 0.5, abs=0.001)

    def test_below_similarity_threshold_excluded(self) -> None:
        """similarity ≤ 0.6 → not satisfied."""
        catalog = _make_catalog({"d1": ["signal"]})

        def embed(texts: list[str]) -> list[list[float]]:
            vecs = []
            for i in range(len(texts)):
                if i == 0:
                    vecs.append([1.0, 0.0, 0.0, 0.0])
                else:
                    vecs.append([0.0, 0.0, 0.0, 1.0])
            return vecs

        results = infer_desire_satisfaction("c", 0.5, 0.5, catalog, embed)
        assert results == []

    def test_no_signals_returns_empty(self) -> None:
        catalog = _make_catalog({"d1": []})
        results = infer_desire_satisfaction(
            "c", 0.5, 0.5, catalog, lambda t: [[0.0]] * len(t)
        )
        assert results == []

    def test_multiple_desires_best_per_desire(self) -> None:
        """Each desire picks the best-matching signal."""
        catalog = _make_catalog({
            "da": ["sig_a1", "sig_a2"],
            "db": ["sig_b"],
        })

        def embed(texts: list[str]) -> list[list[float]]:
            # texts: content, sig_a1, sig_a2, sig_b
            return [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.95, 0.05, 0.0],
                [1.0, 0.0, 0.0],
            ]

        results = infer_desire_satisfaction("c", 0.5, 0.5, catalog, embed)
        ids = [r[0] for r in results]
        assert "da" in ids
        assert "db" in ids

    def test_results_sorted_descending(self) -> None:
        catalog = _make_catalog({"d1": ["s1"], "d2": ["s2"]})

        def embed(texts: list[str]) -> list[list[float]]:
            return [
                [1.0, 0.0, 0.0],
                [0.7, 0.3, 0.0],
                [1.0, 0.0, 0.0],
            ]

        results = infer_desire_satisfaction("c", 0.5, 0.5, catalog, embed)
        if len(results) >= 2:
            assert results[0][1] >= results[1][1]

    def test_builtin_catalog_no_crash(self) -> None:
        """Verify no crash with default catalog (all signals populated)."""
        catalog = default_desire_catalog()

        def embed(texts: list[str]) -> list[list[float]]:
            return [[0.0, 1.0]] * len(texts)

        results = infer_desire_satisfaction("c", 0.5, 0.5, catalog, embed)
        assert isinstance(results, list)

    def test_with_signal_cache_produces_same_results(self, tmp_path: Path) -> None:
        """Cache path should produce identical results to uncached."""
        catalog = _make_catalog({"desire_a": ["matching signal"]})
        cache = SignalEmbeddingCache(tmp_path / "cache.json")

        def embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        uncached = infer_desire_satisfaction("content", 0.5, 0.5, catalog, embed)
        cached = infer_desire_satisfaction(
            "content", 0.5, 0.5, catalog, embed, signal_cache=cache
        )
        assert cached == uncached


class TestSignalEmbeddingCache:
    def test_disk_persistence(self, tmp_path: Path) -> None:
        """Embeddings should survive across cache instances."""
        cache_path = tmp_path / "cache.json"
        catalog = _make_catalog({"d1": ["sig1"]})
        call_count = 0

        def embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return [[1.0, 0.0] for _ in texts]

        cache1 = SignalEmbeddingCache(cache_path)
        signals1, embs1 = cache1.get(catalog, embed)
        assert call_count == 1
        assert cache_path.exists()

        # New instance should load from disk, no embed call
        cache2 = SignalEmbeddingCache(cache_path)
        signals2, embs2 = cache2.get(catalog, embed)
        assert call_count == 1  # no additional API call
        assert signals1 == signals2
        assert embs1 == embs2

    def test_in_memory_hit(self, tmp_path: Path) -> None:
        """Repeated calls on same instance should not re-embed."""
        catalog = _make_catalog({"d1": ["sig1"]})
        call_count = 0

        def embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return [[1.0, 0.0] for _ in texts]

        cache = SignalEmbeddingCache(tmp_path / "cache.json")
        cache.get(catalog, embed)
        cache.get(catalog, embed)
        cache.get(catalog, embed)
        assert call_count == 1

    def test_fingerprint_invalidation_on_catalog_change(
        self, tmp_path: Path
    ) -> None:
        """Changing catalog signals should invalidate the cache."""
        cache_path = tmp_path / "cache.json"
        catalog_v1 = _make_catalog({"d1": ["signal_a"]})
        catalog_v2 = _make_catalog({"d1": ["signal_b"]})
        call_count = 0

        def embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return [[1.0, 0.0] for _ in texts]

        cache = SignalEmbeddingCache(cache_path)
        cache.get(catalog_v1, embed)
        assert call_count == 1

        cache.get(catalog_v2, embed)
        assert call_count == 2  # re-embedded due to fingerprint change

    def test_empty_signals(self, tmp_path: Path) -> None:
        """Catalog with no signals should return empty without crash."""
        catalog = _make_catalog({"d1": []})
        cache = SignalEmbeddingCache(tmp_path / "cache.json")

        def embed(texts: list[str]) -> list[list[float]]:
            return [[0.0]] * len(texts)

        signals, embs = cache.get(catalog, embed)
        assert signals == []
        assert embs == []

    def test_corrupted_cache_file(self, tmp_path: Path) -> None:
        """Corrupted cache file should be handled gracefully."""
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not valid json", encoding="utf-8")

        catalog = _make_catalog({"d1": ["sig"]})
        call_count = 0

        def embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return [[1.0, 0.0] for _ in texts]

        cache = SignalEmbeddingCache(cache_path)
        signals, embs = cache.get(catalog, embed)
        assert call_count == 1
        assert len(signals) == 1

    def test_disk_persistence_across_restart(self, tmp_path: Path) -> None:
        """Verify JSON structure written to disk is valid and complete."""
        cache_path = tmp_path / "cache.json"
        catalog = _make_catalog({"d1": ["sig1"], "d2": ["sig2a", "sig2b"]})

        def embed(texts: list[str]) -> list[list[float]]:
            return [[float(i), 0.0] for i in range(len(texts))]

        cache = SignalEmbeddingCache(cache_path)
        cache.get(catalog, embed)

        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "fingerprint" in data
        assert "signals" in data
        assert "embeddings" in data
        assert len(data["signals"]) == 3
        assert len(data["embeddings"]) == 3


class TestComputeFingerprint:
    def test_deterministic(self) -> None:
        catalog = _make_catalog({"d1": ["a", "b"], "d2": ["c"]})
        assert _compute_fingerprint(catalog) == _compute_fingerprint(catalog)

    def test_order_independent(self) -> None:
        """Fingerprint should be the same regardless of dict insertion order."""
        cat1 = _make_catalog({"a": ["x", "y"], "b": ["z"]})
        cat2 = _make_catalog({"b": ["z"], "a": ["y", "x"]})
        assert _compute_fingerprint(cat1) == _compute_fingerprint(cat2)

    def test_different_signals_different_fingerprint(self) -> None:
        cat1 = _make_catalog({"d1": ["signal_a"]})
        cat2 = _make_catalog({"d1": ["signal_b"]})
        assert _compute_fingerprint(cat1) != _compute_fingerprint(cat2)
