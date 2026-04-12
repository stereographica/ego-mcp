"""Tests for desire satisfaction inference from remember content (§5)."""

from __future__ import annotations

import math

import pytest

from ego_mcp.desire_catalog import (
    DesireCatalog,
    DesireSentenceConfig,
    EmergentDesireConfig,
    FixedDesireConfig,
    default_desire_catalog,
)
from ego_mcp.desire_satisfaction import _cosine_similarity, infer_desire_satisfaction


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
