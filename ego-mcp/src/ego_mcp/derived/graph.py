"""Shared graph and vector computations for derived lenses (D0 S5).

Pure functions over a :class:`~ego_mcp.derived.source.SourceSnapshot`: nothing
here reads files or mutates the snapshot.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ego_mcp.derived.source import SourceSnapshot


@dataclass(frozen=True)
class MemoryGraph:
    """The undirected memory link graph plus notion membership."""

    adjacency: dict[str, set[str]]
    degree: dict[str, int]
    components: list[set[str]]
    component_of: dict[str, int]
    notion_members: dict[str, set[str]]
    notions_of_memory: dict[str, set[str]]


def connected_components(
    adjacency: dict[str, set[str]],
) -> tuple[list[set[str]], dict[str, int]]:
    """Return the components of an undirected adjacency map and their index.

    Every key is part of exactly one component, so an isolated node forms a
    component of its own. Neighbours that are not keys are ignored.
    """
    components: list[set[str]] = []
    component_of: dict[str, int] = {}
    for node in adjacency:
        if node in component_of:
            continue
        index = len(components)
        component: set[str] = {node}
        component_of[node] = index
        queue: deque[str] = deque([node])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, ()):
                if neighbor in component_of or neighbor not in adjacency:
                    continue
                component_of[neighbor] = index
                component.add(neighbor)
                queue.append(neighbor)
        components.append(component)
    return components, component_of


def build_memory_graph(snapshot: SourceSnapshot) -> MemoryGraph:
    """Build the undirected memory graph, dropping dead links.

    ``linked_ids`` is directional on disk; both directions are recorded here.
    Targets that no longer exist (deleted memories) are skipped, as are
    self-links.
    """
    adjacency: dict[str, set[str]] = {memory.id: set() for memory in snapshot.memories}

    for memory in snapshot.memories:
        for link in memory.linked_ids:
            target = link.target_id
            if not target or target == memory.id or target not in adjacency:
                continue
            adjacency[memory.id].add(target)
            adjacency[target].add(memory.id)

    degree = {memory_id: len(neighbors) for memory_id, neighbors in adjacency.items()}
    components, component_of = connected_components(adjacency)

    notion_members: dict[str, set[str]] = {}
    notions_of_memory: dict[str, set[str]] = {}
    for notion in snapshot.notions:
        members = {
            memory_id
            for memory_id in notion.source_memory_ids
            if isinstance(memory_id, str) and memory_id in adjacency
        }
        notion_members[notion.id] = members
        for memory_id in members:
            notions_of_memory.setdefault(memory_id, set()).add(notion.id)

    return MemoryGraph(
        adjacency=adjacency,
        degree=degree,
        components=components,
        component_of=component_of,
        notion_members=notion_members,
        notions_of_memory=notions_of_memory,
    )


def has_path_within(graph: MemoryGraph, a: str, b: str, max_hops: int) -> bool:
    """Return whether ``a`` reaches ``b`` in at most ``max_hops`` edges.

    Bidirectional BFS: each side expands up to half the budget, so the work
    stays proportional to the neighbourhood rather than the component.
    """
    if a not in graph.adjacency or b not in graph.adjacency:
        return False
    if a == b:
        return True
    if max_hops < 1:
        return False
    if graph.component_of.get(a) != graph.component_of.get(b):
        return False

    forward: dict[str, int] = {a: 0}
    backward: dict[str, int] = {b: 0}
    forward_queue: deque[str] = deque([a])
    backward_queue: deque[str] = deque([b])
    forward_budget = max_hops // 2
    backward_budget = max_hops - forward_budget

    while forward_queue or backward_queue:
        progressed = False
        if forward_queue:
            for node in _expand(graph, forward_queue, forward, forward_budget):
                if node in backward:
                    return True
                progressed = True
        if backward_queue:
            for node in _expand(graph, backward_queue, backward, backward_budget):
                if node in forward:
                    return True
                progressed = True
        if not progressed:
            return False
    return False


def _expand(
    graph: MemoryGraph,
    queue: deque[str],
    seen: dict[str, int],
    budget: int,
) -> list[str]:
    """Expand one BFS level, returning the newly discovered nodes."""
    discovered: list[str] = []
    for _ in range(len(queue)):
        current = queue.popleft()
        depth = seen[current]
        if depth >= budget:
            continue
        for neighbor in graph.adjacency.get(current, ()):
            if neighbor in seen:
                continue
            seen[neighbor] = depth + 1
            queue.append(neighbor)
            discovered.append(neighbor)
    return discovered


def cosine_distance(u: np.ndarray, v: np.ndarray) -> float:
    """Cosine distance for unit vectors: ``1 - dot(u, v)``."""
    return float(1.0 - float(np.dot(u, v)))


def centroid(vectors: Sequence[np.ndarray]) -> np.ndarray | None:
    """Return the L2-normalized mean of ``vectors``, or ``None`` if empty."""
    if not vectors:
        return None
    stacked = np.asarray(vectors, dtype=np.float32)
    mean = stacked.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm < 1e-8:
        return None
    normalized: np.ndarray = (mean / norm).astype(np.float32)
    return normalized
