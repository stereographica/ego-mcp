"""Tests for _collect_resonant_persons and related person surface."""

from __future__ import annotations

from pathlib import Path

from ego_mcp._server_surface_person import _collect_resonant_persons
from ego_mcp.relationship import RelationshipStore
from ego_mcp.types import Memory, MemorySearchResult


def _make_result(person_ids: list[str], timestamp: str = "2026-01-15T10:00:00+00:00") -> MemorySearchResult:
    mem = Memory(id=f"mem_{timestamp}", content="test", timestamp=timestamp, involved_person_ids=person_ids)
    return MemorySearchResult(memory=mem)


class TestCollectResonantPersons:
    def test_empty_results(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        result = _collect_resonant_persons([], store)
        assert result == []

    def test_no_involved_person_ids(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        results = [_make_result([])]
        result = _collect_resonant_persons(results, store)
        assert result == []

    def test_single_person(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        results = [_make_result(["Master"])]
        result = _collect_resonant_persons(results, store)
        assert len(result) == 1
        assert result[0].person_id == "Master"
        assert result[0].name == "Master"
        assert result[0].surface_type == "resonant"
        assert result[0].trigger_memory_id is not None

    def test_ranking_by_frequency(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        store.update("Alice", {"name": "Alice"})
        # Master appears in 3 results, Alice in 1
        results = [
            _make_result(["Master"]),
            _make_result(["Master"]),
            _make_result(["Master"]),
            _make_result(["Alice"]),
        ]
        result = _collect_resonant_persons(results, store)
        assert len(result) == 2
        assert result[0].person_id == "Master"  # higher frequency first

    def test_ranking_by_recency(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        store.update("Master", {"name": "Master"})
        store.update("Alice", {"name": "Alice"})
        # Both appear once, but Master has more recent timestamp
        results = [
            _make_result(["Master"], "2026-01-15T10:00:00+00:00"),
            _make_result(["Alice"], "2026-01-10T10:00:00+00:00"),
        ]
        result = _collect_resonant_persons(results, store)
        assert len(result) == 2
        assert result[0].person_id == "Master"  # more recent first

    def test_respects_max_persons(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        for pid in ["A", "B", "C", "D"]:
            store.update(pid, {"name": pid})
        results = [
            _make_result(["A"]),
            _make_result(["B"]),
            _make_result(["C"]),
            _make_result(["D"]),
        ]
        result = _collect_resonant_persons(results, store, max_persons=2)
        assert len(result) == 2

    def test_missing_person_uses_person_id_as_name(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "rels.json")
        # "Unknown" is in involved_person_ids but not in store
        results = [_make_result(["Unknown"])]
        result = _collect_resonant_persons(results, store)
        assert len(result) == 1
        assert result[0].person_id == "Unknown"
        assert result[0].name == "Unknown"  # falls back to person_id
