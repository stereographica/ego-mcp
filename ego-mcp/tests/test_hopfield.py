"""Tests for Hopfield network."""

from __future__ import annotations

from ego_mcp.hopfield import HopfieldRecallResult, ModernHopfieldNetwork


class TestHopfieldStore:
    def test_store_sets_state(self) -> None:
        net = ModernHopfieldNetwork()
        embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        net.store(embeddings, ["a", "b"], ["hello", "world"])
        assert net.is_loaded
        assert net.n_memories == 2
        assert net.dim == 3

    def test_store_empty(self) -> None:
        net = ModernHopfieldNetwork()
        net.store([], [], [])
        assert not net.is_loaded
        assert net.n_memories == 0


class TestHopfieldRetrieve:
    def test_retrieve_finds_closest(self) -> None:
        net = ModernHopfieldNetwork(beta=4.0)
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        net.store(embeddings, ["x", "y", "z"], ["a", "b", "c"])

        # Query close to first pattern
        _, similarities = net.retrieve([0.9, 0.1, 0.0])
        assert len(similarities) == 3
        # First pattern should have highest similarity
        top = net.find_top_k(similarities, k=1)
        assert top[0][0] == 0  # index 0

    def test_retrieve_unloaded(self) -> None:
        net = ModernHopfieldNetwork()
        pattern, similarities = net.retrieve([1.0, 0.0])
        assert len(similarities) == 0


class TestHopfieldRecallResults:
    def test_recall_returns_results(self) -> None:
        net = ModernHopfieldNetwork()
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        net.store(embeddings, ["mem1", "mem2"], ["content1", "content2"])
        _, similarities = net.retrieve([1.0, 0.0])
        results = net.recall_results(similarities, k=2)
        assert len(results) == 2
        assert all(isinstance(r, HopfieldRecallResult) for r in results)
        # First result should be mem1 (closest to query)
        assert results[0].memory_id == "mem1"
