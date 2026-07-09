"""Tests for the SQLite FTS5 (trigram) lexical index."""

from __future__ import annotations

import sqlite3
import string
from pathlib import Path

import pytest

from ego_mcp._lexical_index import LexicalIndex, build_match_query


class TestBuildMatchQuery:
    def test_english_query_builds_trigrams(self) -> None:
        assert build_match_query("cats") == '"cat" OR "ats"'

    def test_uppercase_is_lowercased(self) -> None:
        assert build_match_query("CATS") == '"cat" OR "ats"'

    def test_multiple_segments_are_combined(self) -> None:
        assert build_match_query("cats dogs") == '"cat" OR "ats" OR "dog" OR "ogs"'

    def test_japanese_query_builds_trigrams_without_segmentation(self) -> None:
        # No whitespace in the source, so the whole string is one segment.
        assert build_match_query("猫が好き") == '"猫が好" OR "が好き"'

    def test_segments_shorter_than_three_chars_are_dropped(self) -> None:
        assert build_match_query("ccc a bb") == '"ccc"'
        assert build_match_query("a bb") == ""

    def test_empty_query_returns_empty_string(self) -> None:
        assert build_match_query("") == ""
        assert build_match_query("   ") == ""

    def test_double_quotes_are_escaped(self) -> None:
        # segment 'a"b' (length 3) -> single trigram 'a"b'
        assert build_match_query('a"b') == '"a""b"'

    def test_duplicate_trigrams_are_deduplicated(self) -> None:
        # "aaaa" -> trigrams "aaa", "aaa" (dup) -> only one kept
        assert build_match_query("aaaa") == '"aaa"'

    def test_caps_at_64_trigrams_via_even_sampling(self) -> None:
        base = string.ascii_lowercase + string.digits  # 36 unique chars
        segment = base + base[::-1]  # 72 chars, 70 unique trigrams
        expr = build_match_query(segment)
        clauses = expr.split(" OR ")

        assert len(clauses) == 64
        assert len(set(clauses)) == 64
        assert all(clause.startswith('"') and clause.endswith('"') for clause in clauses)

    def test_at_or_below_cap_is_not_sampled(self) -> None:
        # "abcdefghij" -> 8 unique trigrams, well under the cap.
        expr = build_match_query("abcdefghij")
        assert len(expr.split(" OR ")) == 8


class TestLexicalIndexBasicOperations:
    def _make(self, tmp_path: Path) -> LexicalIndex:
        index = LexicalIndex(tmp_path / "fts" / "memories.db")
        index.connect()
        return index

    def test_connect_creates_parent_dir_and_marks_available(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "nested" / "fts" / "memories.db"
        index = LexicalIndex(db_path)
        index.connect()

        assert index.available is True
        assert db_path.parent.is_dir()
        index.close()

    def test_add_and_count(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        assert index.count() == 0

        index.add("mem_1", "The sunset was beautiful today")
        assert index.count() == 1

        index.close()

    def test_search_finds_matching_content(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_1", "The sunset was beautiful today")
        index.add("mem_2", "I learned about machine learning")

        results = index.search("sunset beautiful", limit=5)

        assert results == ["mem_1"]
        index.close()

    def test_search_ranks_better_match_first(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_weak", "quokka mentioned once in passing")
        index.add("mem_strong", "quokka quokka quokka festival quokka")

        results = index.search("quokka festival", limit=5)

        assert results[0] == "mem_strong"
        index.close()

    def test_search_respects_limit(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        for i in range(5):
            index.add(f"mem_{i}", "shared keyword content")

        results = index.search("shared keyword", limit=2)

        assert len(results) == 2
        index.close()

    def test_search_with_no_trigrams_returns_empty(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_1", "hello world")

        assert index.search("ab", limit=5) == []
        index.close()

    def test_remove(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_1", "hello world")
        index.add("mem_2", "goodbye world")
        assert index.count() == 2

        index.remove("mem_1")

        assert index.count() == 1
        assert index.search("hello", limit=5) == []
        assert index.search("goodbye", limit=5) == ["mem_2"]
        index.close()

    def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.remove("mem_missing")
        assert index.count() == 0
        index.close()

    def test_rebuild_replaces_all_rows(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_stale_1", "stale content one")
        index.add("mem_stale_2", "stale content two")

        index.rebuild([("mem_1", "alpha content"), ("mem_2", "beta content")])

        assert index.count() == 2
        assert index.search("alpha", limit=5) == ["mem_1"]
        assert index.search("stale", limit=5) == []
        index.close()

    def test_rebuild_with_empty_items_clears_index(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_1", "some content")

        index.rebuild([])

        assert index.count() == 0
        index.close()

    def test_japanese_content_is_searchable(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.add("mem_ja", "今日は猫と散歩した")
        index.add("mem_en", "I went for a walk today")

        results = index.search("猫と散歩", limit=5)

        assert results == ["mem_ja"]
        index.close()

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        index = self._make(tmp_path)
        index.close()
        index.close()  # must not raise


class TestLexicalIndexUnavailable:
    def test_disables_when_fts5_trigram_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _BrokenConn:
            def execute(self, *_args: object, **_kwargs: object) -> None:
                raise sqlite3.OperationalError("no such tokenizer: trigram")

            def close(self) -> None:
                pass

        monkeypatch.setattr(
            "ego_mcp._lexical_index.sqlite3.connect",
            lambda *_a, **_kw: _BrokenConn(),
        )

        index = LexicalIndex(tmp_path / "fts" / "memories.db")
        index.connect()

        assert index.available is False

        # All operations are safe no-ops; nothing raises.
        index.add("mem_1", "content")
        assert index.count() == 0
        assert index.search("content", limit=5) == []
        index.remove("mem_1")
        index.rebuild([("mem_1", "content")])
        index.close()
        index.close()
