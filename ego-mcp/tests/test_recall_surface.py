"""Handler-level tests for recall person surface behavior.

Covers:
- Alias resolution preventing person fragmentation
- Resonant / involuntary overlap prevention with canonicalized exclusion set
- Proust results excluded from resonant person collection
- Output format (natural prose, not CRM bullet lists)
- shared_with deduplication after canonicalization
- Display name conversion for user-facing output
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from ego_mcp.relationship import RelationshipStore
from ego_mcp.types import Memory, MemorySearchResult


def _make_memory(
    content: str = "test memory",
    involved_person_ids: list[str] | None = None,
    timestamp: str = "2026-01-01T00:00:00+09:00",
    **kwargs: Any,
) -> Memory:
    return Memory(
        id="mem_001",
        content=content,
        timestamp=timestamp,
        involved_person_ids=involved_person_ids or [],
        **kwargs,
    )


def _make_result(
    memory: Memory | None = None,
    involved_person_ids: list[str] | None = None,
    score: float = 0.5,
) -> MemorySearchResult:
    mem = memory or _make_memory(involved_person_ids=involved_person_ids or [])
    return MemorySearchResult(memory=mem, distance=0.1, score=score, decay=0.8)


# ------------------------------------------------------------------
# Alias resolution in _collect_resonant_persons
# ------------------------------------------------------------------


def test_collect_resonant_persons_aliases_are_merged(tmp_path: Path) -> None:
    """Alias resolution should merge 'Master' and 'マスター' into one person."""
    from ego_mcp._server_surface_person import _collect_resonant_persons

    rs = RelationshipStore(tmp_path / "rs_aliases.json")
    rs.update("canonical_master", {"name": "Master"})
    rs.update("canonical_master", {"aliases": ["マスター", "Master"]})

    results = [
        _make_result(involved_person_ids=["マスター"]),
        _make_result(involved_person_ids=["Master"]),
    ]

    persons = _collect_resonant_persons(results, rs)
    assert len(persons) == 1
    assert persons[0].person_id == "canonical_master"


def test_resolve_person_in_remember_canonicalizes_shared_with(tmp_path: Path) -> None:
    """resolve_person should return canonical id when query matches an alias."""
    rs = RelationshipStore(tmp_path / "rs_remember.json")
    rs.update("canonical_master", {"name": "Master"})
    rs.update("canonical_master", {"aliases": ["マスター"]})

    resolved = rs.resolve_person("マスター")
    assert resolved == "canonical_master"


def test_resolve_person_exact_match(tmp_path: Path) -> None:
    """resolve_person should return the person_id when query matches canonical."""
    rs = RelationshipStore(tmp_path / "rs_exact.json")
    rs.update("master_id", {"name": "Master"})

    assert rs.resolve_person("master_id") == "master_id"


def test_resolve_person_alias_match(tmp_path: Path) -> None:
    """resolve_person should return canonical id when query matches an alias."""
    rs = RelationshipStore(tmp_path / "rs_alias.json")
    rs.update("master_id", {"name": "Master"})
    rs.update("master_id", {"aliases": ["マスター", "Master"]})

    assert rs.resolve_person("マスター") == "master_id"
    assert rs.resolve_person("Master") == "master_id"


def test_resolve_person_no_match(tmp_path: Path) -> None:
    """resolve_person should return None when no match is found."""
    rs = RelationshipStore(tmp_path / "rs_nomatch.json")
    rs.update("master_id", {"name": "Master"})

    assert rs.resolve_person("unknown_person") is None


def test_resolve_person_empty_alias(tmp_path: Path) -> None:
    """resolve_person should handle empty aliases list."""
    rs = RelationshipStore(tmp_path / "rs_empty_alias.json")
    rs.update("master_id", {"name": "Master"})
    rs.update("master_id", {"aliases": []})

    assert rs.resolve_person("master_id") == "master_id"
    assert rs.resolve_person("nonexistent") is None


# ------------------------------------------------------------------
# Resonant / involuntary overlap prevention
# ------------------------------------------------------------------


def test_involuntary_excludes_resonant_persons(tmp_path: Path) -> None:
    """Involuntary persons should not include persons already in resonant set."""
    from ego_mcp._memory_queries import _collect_involuntary_persons
    from ego_mcp._server_surface_person import _collect_resonant_persons

    rs = RelationshipStore(tmp_path / "rs_overlap.json")
    rs.update("alice", {"name": "Alice", "last_interaction": "2025-01-01T00:00:00+09:00"})
    rs.update("bob", {"name": "Bob", "last_interaction": "2024-01-01T00:00:00+09:00"})

    # Alice appears in resonant results, Bob does not
    resonant_results = [_make_result(involved_person_ids=["alice"])]
    persons = _collect_resonant_persons(resonant_results, rs)
    resonant_pids = {p.person_id for p in persons}

    dormant = [_make_result(
        memory=_make_memory(
            content="old memory",
            involved_person_ids=["bob"],
            timestamp="2024-06-01T00:00:00+09:00",
        ),
    )]
    involuntary = _collect_involuntary_persons(
        dormant,
        rs,
        excluded_person_ids=resonant_pids,
        max_persons=1,
    )
    involuntary_pids = {p.person_id for p in involuntary}
    assert resonant_pids.isdisjoint(involuntary_pids)


# ------------------------------------------------------------------
# Output format: natural prose, not CRM bullet lists
# ------------------------------------------------------------------


def test_format_active_persons_returns_prose_not_bullet_list(tmp_path: Path) -> None:
    """_format_active_persons should return natural prose, not a bullet list."""
    from ego_mcp._server_surface_person import _format_active_persons

    rs = RelationshipStore(tmp_path / "rs_prose.json")
    rs.update("alice", {"name": "Alice", "last_interaction": "2026-01-01T00:00:00+09:00"})
    rs.update("bob", {"name": "Bob", "last_interaction": "2025-06-01T00:00:00+09:00"})

    result = _format_active_persons(rs, max_persons=2)
    assert result != ""
    assert "[around me]" not in result
    assert "  - " not in result
    assert "surfaced on their own" in result


def test_format_active_persons_empty_when_no_interactions(tmp_path: Path) -> None:
    """_format_active_persons should return empty string when no last_interaction."""
    from ego_mcp._server_surface_person import _format_active_persons

    rs = RelationshipStore(tmp_path / "rs_no_int.json")
    rs.update("alice", {"name": "Alice"})

    result = _format_active_persons(rs, max_persons=2)
    assert result == ""


def test_format_active_persons_single_person(tmp_path: Path) -> None:
    """_format_active_persons should return single-person prose."""
    from ego_mcp._server_surface_person import _format_active_persons

    rs = RelationshipStore(tmp_path / "rs_single.json")
    rs.update("alice", {"name": "Alice", "last_interaction": "2026-01-01T00:00:00+09:00"})

    result = _format_active_persons(rs, max_persons=2)
    assert "Alice" in result
    assert "surfaced on their own" in result


# ------------------------------------------------------------------
# Finding 1: alias resolution in involuntary exclusion set
# ------------------------------------------------------------------


def test_involuntary_excludes_canonicalized_resonant_persons(tmp_path: Path) -> None:
    """Involuntary exclusion set should use canonical IDs, not raw aliases."""
    from ego_mcp._memory_queries import _collect_involuntary_persons

    rs = RelationshipStore(tmp_path / "rs_canon_exclude.json")
    rs.update("canonical_alice", {"name": "Alice", "last_interaction": "2025-01-01T00:00:00+09:00"})
    rs.update("canonical_alice", {"aliases": ["Alice", "アリス"]})
    rs.update("bob", {"name": "Bob", "last_interaction": "2024-01-01T00:00:00+09:00"})

    # Resonant set contains raw alias "Alice" (as would come from involved_person_ids)
    # After canonicalization via resolve_person, "Alice" -> "canonical_alice"
    resonant_pids_raw = {"Alice"}
    canonicalized_resonant: set[str] = set()
    for p in resonant_pids_raw:
        resolved = rs.resolve_person(p)
        if resolved is not None:
            canonicalized_resonant.add(resolved)
        else:
            canonicalized_resonant.add(p)

    dormant = [_make_result(
        memory=_make_memory(
            content="old memory",
            involved_person_ids=["canonical_alice"],
            timestamp="2024-06-01T00:00:00+09:00",
        ),
    )]
    involuntary = _collect_involuntary_persons(
        dormant,
        rs,
        excluded_person_ids=canonicalized_resonant,
        max_persons=1,
    )
    assert len(involuntary) == 0, "canonical_alice should be excluded from involuntary"

    # Bob should still be available
    dormant_bob = [_make_result(
        memory=_make_memory(
            content="old memory about bob",
            involved_person_ids=["bob"],
            timestamp="2024-06-01T00:00:00+09:00",
        ),
    )]
    involuntary_bob = _collect_involuntary_persons(
        dormant_bob,
        rs,
        excluded_person_ids=canonicalized_resonant,
        max_persons=1,
    )
    assert len(involuntary_bob) == 1
    assert involuntary_bob[0].person_id == "bob"


def test_involuntary_excludes_reverse_alias_case(tmp_path: Path) -> None:
    """Involuntary exclusion should work when dormant memory has alias and resonant has canonical."""
    from ego_mcp._memory_queries import _collect_involuntary_persons

    rs = RelationshipStore(tmp_path / "rs_reverse_alias.json")
    rs.update("canonical_alice", {"name": "Alice", "last_interaction": "2025-01-01T00:00:00+09:00"})
    rs.update("canonical_alice", {"aliases": ["Alice", "アリス"]})
    rs.update("bob", {"name": "Bob", "last_interaction": "2024-01-01T00:00:00+09:00"})

    # Resonant set contains canonical id (as would come from resolved involved_person_ids)
    canonicalized_resonant: set[str] = {"canonical_alice"}

    # Dormant memory has raw alias "Alice" (legacy memory before canonicalization)
    dormant = [_make_result(
        memory=_make_memory(
            content="old memory",
            involved_person_ids=["Alice"],
            timestamp="2024-06-01T00:00:00+09:00",
        ),
    )]
    involuntary = _collect_involuntary_persons(
        dormant,
        rs,
        excluded_person_ids=canonicalized_resonant,
        max_persons=1,
    )
    assert len(involuntary) == 0, "Alice (alias in dormant) should be excluded when resonant has canonical_alice"

    # Bob should still be available
    dormant_bob = [_make_result(
        memory=_make_memory(
            content="old memory about bob",
            involved_person_ids=["bob"],
            timestamp="2024-06-01T00:00:00+09:00",
        ),
    )]
    involuntary_bob = _collect_involuntary_persons(
        dormant_bob,
        rs,
        excluded_person_ids=canonicalized_resonant,
        max_persons=1,
    )
    assert len(involuntary_bob) == 1
    assert involuntary_bob[0].person_id == "bob"


# ------------------------------------------------------------------
# Finding 2: Proust results excluded from resonant persons
# ------------------------------------------------------------------


def test_proust_results_excluded_from_resonant_persons() -> None:
    """Proust hit persons should not appear in resonant person collection."""
    from ego_mcp._server_surface_person import _collect_resonant_persons

    rs = RelationshipStore(Path("/tmp/rs_proust_test.json"))
    rs.update("charlie", {"name": "Charlie"})

    # Simulate results where only a Proust hit contains "charlie"
    proust_result = _make_result(
        memory=_make_memory(content="proust memory", involved_person_ids=["charlie"]),
        score=0.9,
    )
    proust_result.is_proust = True

    normal_result = _make_result(
        memory=_make_memory(content="normal memory", involved_person_ids=["alice"]),
        score=0.1,
    )

    # Filter Proust results the same way _handle_recall does
    non_proust = [r for r in [normal_result, proust_result] if not r.is_proust]
    persons = _collect_resonant_persons(non_proust, rs)
    person_ids = {p.person_id for p in persons}
    assert "charlie" not in person_ids
    assert "alice" in person_ids


# ------------------------------------------------------------------
# Handler-level: _handle_recall is_proust path
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_recall_excludes_proust_from_resonant_persons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_handle_recall should not include Proust-only persons in resonant output."""
    import ego_mcp._server_surface_memory as mem_mod

    rs = RelationshipStore(tmp_path / "rs_handler_proust.json")
    rs.update("charlie", {"name": "Charlie"})
    rs.update("alice", {"name": "Alice"})  # ensure alice exists in real store

    proust_result = _make_result(
        memory=_make_memory(content="proust memory", involved_person_ids=["charlie"]),
        score=0.9,
    )
    proust_result.is_proust = True

    normal_result = _make_result(
        memory=_make_memory(content="normal memory", involved_person_ids=["alice"]),
        score=0.1,
    )

    mock_memory = MagicMock()
    mock_memory.collection_count.return_value = 10
    mock_memory.recall = AsyncMock(return_value=[normal_result, proust_result])
    mock_memory._last_recall_metadata = {
        "involuntary_person_ids": [],
    }

    mock_notion = MagicMock()
    mock_notion.search_related.return_value = []
    mock_notion.get_by_id.return_value = None
    mock_notion.get_associated.return_value = []
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: mock_notion)

    mock_rel_store = MagicMock()
    # resolve_person: check real store first, then passthrough
    def fake_resolve(pid: str) -> str | None:
        real = rs.resolve_person(pid)
        return real if real is not None else pid
    mock_rel_store.resolve_person.side_effect = fake_resolve
    # get: check real store first, then return None
    mock_rel_store.get.side_effect = lambda pid: rs.get(pid) if pid in rs._data else None
    monkeypatch.setattr(
        mem_mod,
        "_relationship_store",
        lambda config: mock_rel_store,
    )

    result = await mem_mod._handle_recall(
        cast(Any, type("Config", (), {})),
        mock_memory,
        {"context": "test", "n_results": 3},
    )

    # Charlie (Proust-only person) should NOT appear in resonant prose
    # The resonant prose starts with "So, " and lists person names
    if "So, " in result:
        # Extract the resonant prose line
        for line in result.splitlines():
            if line.strip().startswith("So, ") and "came to mind" in line:
                assert "charlie" not in line.lower(), "Charlie should not appear in resonant prose"
    # Alice (non-Proust person) should appear in resonant prose
    assert "So, Alice" in result or "So, alice" in result, (
        f"Alice should appear in resonant prose. Result:\n{result}"
    )


# ------------------------------------------------------------------
# Finding 3: shared_with dedupe after canonicalization
# ------------------------------------------------------------------


def test_shared_with_deduped_after_canonicalization(tmp_path: Path) -> None:
    """Canonicalized shared_with should be deduplicated (aliases -> same canonical)."""
    rs = RelationshipStore(tmp_path / "rs_dedup.json")
    rs.update("canonical_master", {"name": "Master"})
    rs.update("canonical_master", {"aliases": ["Master", "マスター"]})

    raw = ["Master", "マスター"]
    canonicalized: list[str] = []
    for p in raw:
        resolved = rs.resolve_person(p)
        canonicalized.append(resolved if resolved is not None else p)
    deduped = list(dict.fromkeys(canonicalized))

    assert len(deduped) == 1
    assert deduped[0] == "canonical_master"


def test_shared_with_display_names_used_in_output(tmp_path: Path) -> None:
    """Display names should be used instead of canonical IDs in user-facing output."""
    rs = RelationshipStore(tmp_path / "rs_display.json")
    rs.update("canonical_alice", {"name": "Alice"})
    rs.update("canonical_bob", {"name": "Bob"})

    canonical_ids = ["canonical_alice", "canonical_bob"]
    display_names: list[str] = []
    for pid in canonical_ids:
        rel = rs.get(pid)
        display_names.append(rel.name if rel and rel.name else pid)

    assert display_names == ["Alice", "Bob"]
    assert "canonical_" not in display_names


class TestExplicitFilterInvoluntarySuppression:
    """OQ-3: involuntary person surface suppressed when explicit filter used."""

    def test_involuntary_suppressed_with_emotion_filter(self, tmp_path: Path) -> None:
        """emotion_filter → involuntary persons suppressed, resonant returned."""
        rs = RelationshipStore(tmp_path / "rs_ef.json")
        rs.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        rs.update("Alice", {"name": "Alice", "last_interaction": "2025-06-01T10:00:00+00:00"})

        import unittest.mock as mock

        import ego_mcp._server_surface_memory as mem_mod
        from ego_mcp.config import EgoConfig

        config = EgoConfig(
            embedding_provider="gemini", embedding_model="gemini-embedding-001",
            api_key="test-key", data_dir=tmp_path, companion_name="Master",
            workspace_dir=None, timezone="UTC",
        )

        normal_result = _make_result(
            memory=_make_memory(content="normal memory", involved_person_ids=["Master"]),
            score=0.1,
        )
        mock_memory = MagicMock()
        mock_memory.collection_count.return_value = 10
        mock_memory.recall = AsyncMock(return_value=[normal_result])
        mock_memory._last_recall_metadata = {
            "involuntary_person_ids": ["Alice"],
        }

        mock_notion = MagicMock()
        mock_notion.search_related.return_value = []
        mock_notion.get_by_id.return_value = None
        mock_notion.get_associated.return_value = []

        with mock.patch.object(mem_mod, "get_notion_store", return_value=mock_notion):
            mock_rel_store = MagicMock()
            with mock.patch.object(mem_mod, "_relationship_store", return_value=mock_rel_store):
                def fake_resolve(pid: str) -> str | None:
                    real = rs.resolve_person(pid)
                    return real if real is not None else pid
                mock_rel_store.resolve_person.side_effect = fake_resolve
                mock_rel_store.get.side_effect = lambda pid: rs.get(pid) if pid in rs._data else None

                result = asyncio.run(mem_mod._handle_recall(
                    cast(Any, config),
                    mock_memory,
                    {"context": "test", "n_results": 3, "emotion_filter": "happy"},
                ))

                assert "Master" in result
                assert "surfaced on their own" not in result

    def test_involuntary_suppressed_with_date_range(self, tmp_path: Path) -> None:
        """date_from + date_to → involuntary persons suppressed."""
        rs = RelationshipStore(tmp_path / "rs_dr.json")
        rs.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        rs.update("Alice", {"name": "Alice", "last_interaction": "2025-06-01T10:00:00+00:00"})

        from ego_mcp.config import EgoConfig

        config = EgoConfig(
            embedding_provider="gemini", embedding_model="gemini-embedding-001",
            api_key="test-key", data_dir=tmp_path, companion_name="Master",
            workspace_dir=None, timezone="UTC",
        )

        normal_result = _make_result(
            memory=_make_memory(content="normal memory", involved_person_ids=["Master"]),
            score=0.1,
        )
        mock_memory = MagicMock()
        mock_memory.collection_count.return_value = 10
        mock_memory.recall = AsyncMock(return_value=[normal_result])
        mock_memory._last_recall_metadata = {
            "involuntary_person_ids": ["Alice"],
        }

        mock_notion = MagicMock()
        mock_notion.search_related.return_value = []
        mock_notion.get_by_id.return_value = None
        mock_notion.get_associated.return_value = []

        import unittest.mock as mock

        import ego_mcp._server_surface_memory as mem_mod2

        with mock.patch.object(mem_mod2, "get_notion_store", return_value=mock_notion):
            mock_rel_store = MagicMock()
            with mock.patch.object(mem_mod2, "_relationship_store", return_value=mock_rel_store):
                def fake_resolve(pid: str) -> str | None:
                    real = rs.resolve_person(pid)
                    return real if real is not None else pid
                mock_rel_store.resolve_person.side_effect = fake_resolve
                mock_rel_store.get.side_effect = lambda pid: rs.get(pid) if pid in rs._data else None

                result = asyncio.run(mem_mod2._handle_recall(
                    cast(Any, config),
                    mock_memory,
                    {"context": "test", "n_results": 3, "date_from": "2026-01-01T00:00:00", "date_to": "2026-01-31T23:59:59"},
                ))

                assert "Master" in result
                assert "surfaced on their own" not in result

    def test_resonant_still_returned_with_filter(self, tmp_path: Path) -> None:
        """resonant persons are still returned when explicit filter is used."""
        rs = RelationshipStore(tmp_path / "rs_rs.json")
        rs.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})

        import ego_mcp._server_surface_memory as mem_mod
        from ego_mcp.config import EgoConfig

        config = EgoConfig(
            embedding_provider="gemini", embedding_model="gemini-embedding-001",
            api_key="test-key", data_dir=tmp_path, companion_name="Master",
            workspace_dir=None, timezone="UTC",
        )

        normal_result = _make_result(
            memory=_make_memory(content="normal memory", involved_person_ids=["Master"]),
            score=0.1,
        )
        mock_memory = MagicMock()
        mock_memory.collection_count.return_value = 10
        mock_memory.recall = AsyncMock(return_value=[normal_result])
        mock_memory._last_recall_metadata = {
            "involuntary_person_ids": [],
        }

        mock_notion = MagicMock()
        mock_notion.search_related.return_value = []
        mock_notion.get_by_id.return_value = None
        mock_notion.get_associated.return_value = []

        import unittest.mock as mock

        with mock.patch.object(mem_mod, "get_notion_store", return_value=mock_notion):
            mock_rel_store = MagicMock()
            with mock.patch.object(mem_mod, "_relationship_store", return_value=mock_rel_store):
                def fake_resolve(pid: str) -> str | None:
                    real = rs.resolve_person(pid)
                    return real if real is not None else pid
                mock_rel_store.resolve_person.side_effect = fake_resolve
                mock_rel_store.get.side_effect = lambda pid: rs.get(pid) if pid in rs._data else None

                result = asyncio.run(mem_mod._handle_recall(
                    cast(Any, config),
                    mock_memory,
                    {"context": "test", "n_results": 3, "category_filter": "work"},
                ))

                assert "Master" in result

    def test_involuntary_returned_without_filter(self, tmp_path: Path) -> None:
        """Without explicit filter, involuntary persons are returned."""
        rs = RelationshipStore(tmp_path / "rs_ir.json")
        rs.update("Master", {"name": "Master", "last_interaction": "2026-01-10T10:00:00+00:00"})
        rs.update("Alice", {"name": "Alice", "last_interaction": "2025-06-01T10:00:00+00:00"})

        import ego_mcp._server_surface_memory as mem_mod
        from ego_mcp.config import EgoConfig

        config = EgoConfig(
            embedding_provider="gemini", embedding_model="gemini-embedding-001",
            api_key="test-key", data_dir=tmp_path, companion_name="Master",
            workspace_dir=None, timezone="UTC",
        )

        normal_result = _make_result(
            memory=_make_memory(content="normal memory", involved_person_ids=["Master"]),
            score=0.1,
        )
        mock_memory = MagicMock()
        mock_memory.collection_count.return_value = 10
        mock_memory.recall = AsyncMock(return_value=[normal_result])
        mock_memory._last_recall_metadata = {
            "involuntary_person_ids": ["Alice"],
        }

        mock_notion = MagicMock()
        mock_notion.search_related.return_value = []
        mock_notion.get_by_id.return_value = None
        mock_notion.get_associated.return_value = []

        import unittest.mock as mock

        with mock.patch.object(mem_mod, "get_notion_store", return_value=mock_notion):
            mock_rel_store = MagicMock()
            with mock.patch.object(mem_mod, "_relationship_store", return_value=mock_rel_store):
                def fake_resolve(pid: str) -> str | None:
                    real = rs.resolve_person(pid)
                    return real if real is not None else pid
                mock_rel_store.resolve_person.side_effect = fake_resolve
                mock_rel_store.get.side_effect = lambda pid: rs.get(pid) if pid in rs._data else None

                result = asyncio.run(mem_mod._handle_recall(
                    cast(Any, config),
                    mock_memory,
                    {"context": "test", "n_results": 3},
                ))

                assert "Master" in result
                assert "Alice" in result
                assert "surfaced on their own" in result
