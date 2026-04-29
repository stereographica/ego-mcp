"""Tests for _collect_involuntary_persons and _format_active_persons."""

from __future__ import annotations

from pathlib import Path

from ego_mcp._memory_queries import _collect_involuntary_persons
from ego_mcp._server_surface_person import _format_active_persons
from ego_mcp.relationship import RelationshipStore
from ego_mcp.types import Memory, MemorySearchResult


def _make_result(person_ids: list[str], timestamp: str = "2026-01-15T10:00:00+00:00") -> MemorySearchResult:
    mem = Memory(id=f"mem_{timestamp}", content="test", timestamp=timestamp, involved_person_ids=person_ids)
    return MemorySearchResult(memory=mem)


class TestCollectInvoluntaryPersons:
    def test_empty_dormant_candidates(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        result = _collect_involuntary_persons([], store, set())
        assert result == []

    def test_no_involved_person_ids_in_dormant(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        results = [_make_result([])]
        result = _collect_involuntary_persons(results, store, set())
        assert result == []

    def test_excludes_resonant_persons(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        store.update("Alice", {"name": "Alice", "last_interaction": "2025-06-01T10:00:00+00:00"})
        # Master is in resonant_pids, should be excluded
        results = [
            _make_result(["Master"]),
            _make_result(["Alice"]),
        ]
        result = _collect_involuntary_persons(results, store, excluded_person_ids={"Master"})
        assert len(result) == 1
        assert result[0].person_id == "Alice"
        assert result[0].surface_type == "involuntary"

    def test_ranks_by_last_interaction_oldest_first(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Alice", {"name": "Alice", "last_interaction": "2024-01-01T10:00:00+00:00"})
        store.update("Bob", {"name": "Bob", "last_interaction": "2025-06-01T10:00:00+00:00"})
        results = [
            _make_result(["Alice"]),
            _make_result(["Bob"]),
        ]
        result = _collect_involuntary_persons(results, store, set(), max_persons=2)
        assert len(result) == 2
        assert result[0].person_id == "Alice"  # oldest first

    def test_max_persons_limit(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        for pid in ["A", "B", "C"]:
            store.update(pid, {"name": pid, "last_interaction": "2025-01-01T10:00:00+00:00"})
        results = [
            _make_result(["A"]),
            _make_result(["B"]),
            _make_result(["C"]),
        ]
        result = _collect_involuntary_persons(results, store, set(), max_persons=1)
        assert len(result) == 1

    def test_uses_person_id_as_name_when_missing(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        # Unknown person not in store
        results = [_make_result(["Unknown"])]
        result = _collect_involuntary_persons(results, store, set())
        assert len(result) == 1
        assert result[0].person_id == "Unknown"
        assert result[0].name == "Unknown"

    def test_none_last_interaction_treated_as_oldest(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Alice", {"name": "Alice", "last_interaction": "2025-06-01T10:00:00+00:00"})
        store.update("Bob", {"name": "Bob"})  # no last_interaction
        results = [
            _make_result(["Alice"]),
            _make_result(["Bob"]),
        ]
        result = _collect_involuntary_persons(results, store, set(), max_persons=2)
        assert len(result) == 2
        assert result[0].person_id == "Bob"  # None last_interaction = oldest


class TestFormatActivePersons:
    def test_empty_store(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        result = _format_active_persons(store)
        assert result == ""

    def test_no_last_interaction(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        result = _format_active_persons(store)
        assert result == ""

    def test_single_person(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master", "last_interaction": "2026-01-15T10:00:00+00:00"})
        result = _format_active_persons(store)
        assert "[around me]" in result
        assert "Master" in result
        assert "2026-01-15" in result

    def test_limits_to_max_persons(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        for pid in ["A", "B", "C"]:
            store.update(pid, {"name": pid, "last_interaction": "2025-01-01T10:00:00+00:00"})
        result = _format_active_persons(store, max_persons=2)
        assert result is not None
        assert result.count("  - ") == 2

    def test_sorted_by_recency(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Alice", {"name": "Alice", "last_interaction": "2026-01-15T10:00:00+00:00"})
        store.update("Bob", {"name": "Bob", "last_interaction": "2025-06-01T10:00:00+00:00"})
        result = _format_active_persons(store)
        assert result is not None
        assert result.index("Alice") < result.index("Bob")
