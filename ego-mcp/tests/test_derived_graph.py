"""Tests for derived/graph.py (D0 S5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from ego_mcp.derived.graph import (
    build_memory_graph,
    centroid,
    cosine_distance,
    has_path_within,
)
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import LinkType, Memory, MemoryLink, Notion

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _memory(memory_id: str, *, links: list[str] | None = None) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp=NOW.isoformat(),
        linked_ids=[
            MemoryLink(target_id=target, link_type=LinkType.RELATED)
            for target in (links or [])
        ],
    )


def _snapshot(
    memories: list[Memory], notions: list[Notion] | None = None
) -> SourceSnapshot:
    return SourceSnapshot(
        now=NOW,
        memories=memories,
        embeddings=None,
        notions=notions or [],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


def _chain(n: int) -> SourceSnapshot:
    memories = [
        _memory(f"m{i}", links=[f"m{i + 1}"] if i < n - 1 else []) for i in range(n)
    ]
    return _snapshot(memories)


# --- build_memory_graph -----------------------------------------------------


def test_graph_is_undirected() -> None:
    graph = build_memory_graph(_snapshot([_memory("a", links=["b"]), _memory("b")]))
    assert graph.adjacency["a"] == {"b"}
    assert graph.adjacency["b"] == {"a"}
    assert graph.degree == {"a": 1, "b": 1}


def test_graph_drops_dead_links() -> None:
    graph = build_memory_graph(
        _snapshot([_memory("a", links=["ghost", "b"]), _memory("b")])
    )
    assert graph.adjacency["a"] == {"b"}
    assert "ghost" not in graph.adjacency
    assert graph.degree["a"] == 1


def test_graph_drops_self_links_and_blank_targets() -> None:
    graph = build_memory_graph(_snapshot([_memory("a", links=["a", ""])]))
    assert graph.adjacency["a"] == set()
    assert graph.degree["a"] == 0


def test_graph_isolated_memory_is_present_with_degree_zero() -> None:
    graph = build_memory_graph(_snapshot([_memory("lonely")]))
    assert graph.adjacency == {"lonely": set()}
    assert graph.degree == {"lonely": 0}
    assert graph.components == [{"lonely"}]


def test_graph_components() -> None:
    graph = build_memory_graph(
        _snapshot(
            [
                _memory("a", links=["b"]),
                _memory("b"),
                _memory("c", links=["d"]),
                _memory("d"),
                _memory("e"),
            ]
        )
    )
    assert sorted(len(component) for component in graph.components) == [1, 2, 2]
    assert graph.component_of["a"] == graph.component_of["b"]
    assert graph.component_of["c"] == graph.component_of["d"]
    assert graph.component_of["a"] != graph.component_of["c"]
    assert graph.component_of["e"] not in (
        graph.component_of["a"],
        graph.component_of["c"],
    )


def test_graph_notion_membership_skips_missing_memories() -> None:
    notion = Notion(
        id="notion_1",
        label="something",
        source_memory_ids=["a", "gone", "b"],
    )
    graph = build_memory_graph(_snapshot([_memory("a"), _memory("b")], [notion]))
    assert graph.notion_members["notion_1"] == {"a", "b"}
    assert graph.notions_of_memory["a"] == {"notion_1"}
    assert graph.notions_of_memory["b"] == {"notion_1"}
    assert "gone" not in graph.notions_of_memory


def test_graph_memory_can_belong_to_several_notions() -> None:
    notions = [
        Notion(id="notion_1", label="x", source_memory_ids=["a"]),
        Notion(id="notion_2", label="y", source_memory_ids=["a"]),
    ]
    graph = build_memory_graph(_snapshot([_memory("a")], notions))
    assert graph.notions_of_memory["a"] == {"notion_1", "notion_2"}


def test_graph_empty_snapshot() -> None:
    graph = build_memory_graph(_snapshot([]))
    assert graph.adjacency == {}
    assert graph.components == []


# --- has_path_within --------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "max_hops", "expected"),
    [
        ("m0", "m1", 1, True),
        ("m0", "m2", 1, False),
        ("m0", "m2", 2, True),
        ("m0", "m3", 2, False),
        ("m0", "m3", 3, True),
        ("m0", "m4", 3, False),
        ("m0", "m4", 4, True),
        ("m0", "m5", 4, False),
        ("m0", "m5", 5, True),
        ("m0", "m6", 5, False),
        ("m0", "m6", 6, True),
    ],
)
def test_has_path_within_hop_limit(a: str, b: str, max_hops: int, expected: bool) -> None:
    graph = build_memory_graph(_chain(7))
    assert has_path_within(graph, a, b, max_hops) is expected


def test_has_path_within_same_node_is_true() -> None:
    graph = build_memory_graph(_chain(3))
    assert has_path_within(graph, "m0", "m0", 1) is True
    assert has_path_within(graph, "m0", "m0", 0) is True


def test_has_path_within_zero_hops_between_neighbours_is_false() -> None:
    graph = build_memory_graph(_chain(3))
    assert has_path_within(graph, "m0", "m1", 0) is False


def test_has_path_within_unknown_nodes() -> None:
    graph = build_memory_graph(_chain(3))
    assert has_path_within(graph, "m0", "ghost", 5) is False
    assert has_path_within(graph, "ghost", "m0", 5) is False


def test_has_path_within_separate_components() -> None:
    graph = build_memory_graph(
        _snapshot([_memory("a", links=["b"]), _memory("b"), _memory("c")])
    )
    assert has_path_within(graph, "a", "c", 99) is False


def test_has_path_within_finds_the_shorter_of_two_routes() -> None:
    # a-b-c-d-e long way, a-e short way
    graph = build_memory_graph(
        _snapshot(
            [
                _memory("a", links=["b", "e"]),
                _memory("b", links=["c"]),
                _memory("c", links=["d"]),
                _memory("d", links=["e"]),
                _memory("e"),
            ]
        )
    )
    assert has_path_within(graph, "a", "e", 1) is True


# --- vectors ----------------------------------------------------------------


def test_cosine_distance_of_identical_unit_vectors_is_zero() -> None:
    u = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_distance(u, u) == pytest.approx(0.0, abs=1e-6)


def test_cosine_distance_orthogonal_and_opposite() -> None:
    u = np.array([1.0, 0.0], dtype=np.float32)
    v = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_distance(u, v) == pytest.approx(1.0, abs=1e-6)
    assert cosine_distance(u, -u) == pytest.approx(2.0, abs=1e-6)


def test_centroid_is_unit_length() -> None:
    vectors = [
        np.array([1.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0], dtype=np.float32),
    ]
    result = centroid(vectors)
    assert result is not None
    assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-6)
    assert result.dtype == np.float32


def test_centroid_of_empty_sequence_is_none() -> None:
    assert centroid([]) is None


def test_centroid_of_cancelling_vectors_is_none() -> None:
    u = np.array([1.0, 0.0], dtype=np.float32)
    assert centroid([u, -u]) is None
